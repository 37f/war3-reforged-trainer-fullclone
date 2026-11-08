"""Read-only W3I player/force prefix; independent of game memory readers.

Layout references (schema only, implementation is local):
War3Net.Build.Core/Serialization/Binary/Info/{MapInfo,PlayerData,ForceData}.cs
HiveWE src/base/map_info.ixx (format39 HUD skin and water fields).
"""
import math
import re
import struct

from war3_object_tables import Reader,DefinitionError
from war3_map_objects import decode_text
from war3_custom_objects import parse_wts

VERSIONS=(18,23,24,25,26,27,28,31,32,33,39)


def parse_player_info(raw,wts=b''):
    if not raw or len(raw)>8*1024*1024:raise DefinitionError('玩家配置文件缺失或超过读取上限')
    r=Reader(raw);version=r.integer()
    if version not in VERSIONS:raise DefinitionError(f'玩家配置格式 {version} 尚未适配')
    r.take(8)
    game=tuple(r.integer() for _ in range(4)) if version>=27 else ()
    names=[r.string() for _ in range(4)]
    r.take(32+16+8);flags=r.integer();r.take(1)
    if version>=23:
        r.take(4)
        if version>=39:r.take(4)
        for _ in range(4):r.string()
        r.take(4)
        for _ in range(4):r.string()
        r.take(20)
        if version>=39:r.take(24)
        if version>=25:r.take(4)
        r.string();r.take(1+4)
        if version>=28:r.take(4)
        if version>=31:r.take(8)
        if version>=32:r.take(8)
        if version>=33:r.take(4)
        if version>=39:r.take(40)
    else:
        r.take(4)
        for _ in range(3):r.string()
        r.take(4)
        for _ in range(3):r.string()
    strings=parse_wts(wts) if wts else {}
    missing=[]
    def text(value):
        value=decode_text(value);match=re.fullmatch(r'TRIGSTR_(\d+)',value,re.I)
        if match:
            key=int(match[1])
            if key not in strings:missing.append(value);return value+'（文字表缺失）'
            value=strings[key]
        return re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',value).replace('|n','\n')
    players=[];seen=set()
    for _ in range(r.count(32)):
        slot,control,race=r.integer(),r.integer(),r.integer()
        if not 0<=slot<32 or slot in seen:raise DefinitionError('玩家配置槽位重复或越界')
        seen.add(slot)
        skin=r.integer() if version>=39 else None
        fixed=r.integer();name=text(r.string());x,y=struct.unpack('<2f',r.take(8))
        if not all(math.isfinite(v) and abs(v)<=1e6 for v in (x,y)):raise DefinitionError('玩家初始位置无效')
        low,high=struct.unpack('<2I',r.take(8))
        enemy_low,enemy_high=struct.unpack('<2I',r.take(8)) if version>=31 else (None,None)
        players.append(dict(id=slot,name=name,controller=control,race=race,skin=skin,
            fixed_start=bool(fixed&1),flags=fixed,x=x,y=y,ally_low=low,ally_high=high,
            enemy_low=enemy_low,enemy_high=enemy_high))
    groups=[]
    for i in range(r.count(32)):
        group_flags,mask=struct.unpack('<2I',r.take(8));name=text(r.string())
        # First-force masks often include all unused bits. Only declared
        # player records are evidence of editor membership.
        members=sorted(p for p in seen if mask&(1<<p))
        groups.append(dict(key=f'force:{i}',name=name or f'地图势力 {i+1}',members=members,flags=group_flags,mask=mask))
    return dict(format=version,game_version=game,map_name=text(names[0]),flags=flags,
        players=players,groups=groups,parsed_prefix_bytes=r.at,
        issues=['未找到配置文字：'+v for v in dict.fromkeys(missing)])
