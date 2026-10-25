"""R22 source contracts and bounded exact-profile metadata reads.

No heap scans, target calls, task mutations or script execution. A source
provider must additionally bind metadata to game-owned files and map session.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import PureWindowsPath
import struct
import time

MAX_SCRIPT_BYTES=32*1024*1024
MAX_STRINGS_BYTES=16*1024*1024
MAX_PATH_BYTES=4096
MAX_READ_SECONDS=60


class SourceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MapSourceMetadata:
    session_token:int
    fingerprint:str
    map_path:str
    campaign_path:str
    is_campaign:bool


@dataclass(frozen=True)
class ScriptSnapshot:
    identity:object
    session_token:int
    origin:str
    language:str
    script:bytes
    strings_data:bytes
    script_sha256:str
    strings_sha256:str
    validated_at:float
    provenance:tuple[str,...]
    stamp:tuple


def _exact(read,address,count):
    if not 0x10000<=address<0x7fffffffffff or not 0<count<=MAX_PATH_BYTES:
        raise SourceUnavailable('脚本来源字段范围无效')
    data=read(address,count)
    if len(data)!=count:raise SourceUnavailable('脚本来源字段读取不完整')
    return data


def _q(read,address):return struct.unpack('<Q',_exact(read,address,8))[0]


def _c_string(read,address):
    data=bytearray()
    while len(data)<MAX_PATH_BYTES:
        # Do not cross a page just to read the tail of a short string.
        amount=min(64,MAX_PATH_BYTES-len(data),4096-((address+len(data))&4095))
        part=_exact(read,address+len(data),amount);end=part.find(b'\0')
        if end>=0:
            data.extend(part[:end])
            try:value=data.decode('utf8')
            except UnicodeError as exc:raise SourceUnavailable('脚本来源路径不是有效 UTF-8') from exc
            if any(ord(c)<32 or ord(c)==127 for c in value):raise SourceUnavailable('脚本来源路径含控制字符')
            return value
        data.extend(part)
    raise SourceUnavailable('脚本来源路径超过长度上限或未终止')


def _fnv(data):
    value=14695981039346656037
    for byte in data:value=((value^byte)*1099511628211)&0xffffffffffffffff
    return value


def _valid_map_path(value,campaign):
    path=PureWindowsPath(value)
    return (bool(value) and path.suffix.casefold() in ('.w3x','.w3m') and
        '..' not in path.parts and (not campaign or (not path.drive and not path.root)))


def read_profiled_map_metadata(read,base:int,active_token:int)->MapSourceMetadata:
    """Only validated 2.0.4.23745 fields, with an independently active token.

    The observed GetGameDifficulty getter binds the world/config; the campaign
    predicate used by SetCampaignMenuRace binds current-campaign storage.
    Layout evidence: docs/r22-quest-source-feasibility.md (runtime gate).
    """
    try:
        if type(active_token) is not int or not 0<active_token<2**64:
            raise SourceUnavailable('当前地图会话尚未确认')
        dos=_exact(read,base,64)
        if dos[:2]!=b'MZ':raise SourceUnavailable('当前游戏构建不支持脚本来源读取')
        pe_offset=struct.unpack_from('<I',dos,0x3c)[0]
        if not 0x40<=pe_offset<=0x1000:raise SourceUnavailable('当前游戏 PE 表头无效')
        pe=_exact(read,base+pe_offset,0x108)
        # The observed loader changes this field from disk AMD64 (8664) to
        # 0200 in memory. PE32+, exact code hashes and vtables bind this build.
        if (pe[:4]!=b'PE\0\0' or struct.unpack_from('<H',pe,4)[0] not in (0x8664,0x200) or
            struct.unpack_from('<I',pe,8)[0]!=0x69e54471 or
            struct.unpack_from('<H',pe,24)[0]!=0x20b or struct.unpack_from('<I',pe,80)[0]!=0xdd20000):
            raise SourceUnavailable('当前游戏构建不支持脚本来源读取')
        for rva,count,expected in ((0xc50003,62,0xa13bc516c90ae996),(0x9dde50,39,0x9afa250dca103fd3)):
            if _fnv(_exact(read,base+rva,count))!=expected:
                raise SourceUnavailable('脚本来源代码特征不匹配')
        world=_q(read,base+0x2b59964)^0x363abbfd3defaec9^_q(read,base+0x2bd7bc8)
        if _q(read,world)!=base+0x23d0690:raise SourceUnavailable('脚本来源世界对象类型不匹配')
        config=_q(read,world+0x2670)
        if _q(read,config)!=base+0x23d0508:raise SourceUnavailable('脚本来源配置对象类型不匹配')
        if _q(read,config+0x40)!=base+0x21dea60:raise SourceUnavailable('脚本来源路径容器类型不匹配')
        entry=_q(read,config+0x50)
        if _q(read,entry)!=base+0x21de9b0:raise SourceUnavailable('脚本来源字符串类型不匹配')
        map_path=_c_string(read,_q(read,entry+0x38))
        flag=_exact(read,world+0x304f,1)[0]
        if flag not in (0,1):raise SourceUnavailable('脚本来源战役标志无效')
        campaign_path=_c_string(read,base+0x2bd7a10) if flag==0 else ''
        campaign=bool(campaign_path)
        if not _valid_map_path(map_path,campaign):raise SourceUnavailable('当前地图资源路径无法确认')
        if campaign:
            path=PureWindowsPath(campaign_path)
            if not path.is_absolute() or path.suffix.casefold()!='.w3n' or '..' in path.parts:
                raise SourceUnavailable('当前战役来源路径无法确认')
        values=(active_token,world,config,entry,map_path,campaign_path,campaign)
        fingerprint=hashlib.sha256(repr(values).encode('utf8')).hexdigest()
        return MapSourceMetadata(active_token,fingerprint,map_path,campaign_path,campaign)
    except SourceUnavailable:raise
    except (OSError,ValueError,OverflowError,struct.error) as exc:
        raise SourceUnavailable('无法验证当前地图脚本来源：'+str(exc)) from exc


class CurrentMapScriptClient:
    """The provider proves ownership; this layer enforces immutable boundaries.

    query(snapshot=None,cancelled=...) returns a ScriptSnapshot; passing an
    existing snapshot requests a lightweight ownership/session check (bool).
    """
    def __init__(self,query,identity):self.query,self.identity=query,identity

    def read(self,cancelled=lambda:False)->ScriptSnapshot:
        started=time.monotonic();identity=self.identity()
        if cancelled():raise RuntimeError('当前地图脚本读取已取消')
        value=self.query(snapshot=None,cancelled=cancelled)
        if cancelled():raise RuntimeError('当前地图脚本读取已取消')
        if self.identity()!=identity:raise RuntimeError('游戏连接已变化')
        if time.monotonic()-started>MAX_READ_SECONDS:raise TimeoutError('当前地图脚本读取超过时间上限')
        if not isinstance(value,ScriptSnapshot):raise ValueError('脚本来源返回类型无效')
        if value.identity!=identity:raise RuntimeError('脚本来源不属于当前游戏连接')
        if (type(value.session_token) is not int or not 0<value.session_token<2**64 or not value.origin or
            not isinstance(value.provenance,tuple) or not value.provenance or
            any(not isinstance(x,str) or not x for x in value.provenance)):
            raise ValueError('脚本来源证明不完整')
        if type(value.script) is not bytes or type(value.strings_data) is not bytes:
            raise ValueError('脚本或字符串表返回类型无效')
        if len(value.script)>MAX_SCRIPT_BYTES or len(value.strings_data)>MAX_STRINGS_BYTES:
            raise ValueError('脚本或字符串表超过大小上限')
        if (hashlib.sha256(value.script).hexdigest()!=value.script_sha256 or
            hashlib.sha256(value.strings_data).hexdigest()!=value.strings_sha256):
            raise ValueError('脚本或字符串表哈希不一致')
        if value.language not in ('jass','lua'):raise ValueError('不支持的脚本语言')
        if not math.isfinite(value.validated_at) or not 0<=value.validated_at<=time.monotonic():
            raise ValueError('脚本校验时间无效')
        return value

    def check(self,snapshot:ScriptSnapshot)->bool:
        if self.identity()!=snapshot.identity:return False
        result=self.query(snapshot=snapshot,cancelled=lambda:False)
        return result is True and self.identity()==snapshot.identity
