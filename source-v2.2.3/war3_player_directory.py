"""Read-only player directory, with explicitly separate live/config sources.

No native slots, helper ABI, unit readers or game profile fields are changed.
Scalar offsets are admitted only after recognizing the current getter's exact
success branch. Team queries reuse FullClone action8 without changing it.
"""
from pathlib import Path
import struct
import tempfile
import time

from war3_fullclone_runtime import read_context,player_name
from war3_fullclone_source import current_script,check_source
from war3_player_map_info import parse_player_info

GETTERS={
    'color':('GetPlayerColor','(Hplayer;)Hplayercolor;'),
    'controller':('GetPlayerController','(Hplayer;)Hmapcontrol;'),
    'race':('GetPlayerRace','(Hplayer;)Hrace;'),
    'slot_state':('GetPlayerSlotState','(Hplayer;)Hplayerslotstate;'),
    'start_index':('GetPlayerStartLocation','(Hplayer;)I'),
}
NEUTRALS={24:'中立敌对',25:'中立受害者',26:'中立额外',27:'中立被动'}
RACES={1:'人族',2:'兽族',3:'亡灵',4:'暗夜精灵',5:'恶魔',7:'其他'}
MAP_RACES={0:'可选择/随机',1:'人族',2:'兽族',3:'亡灵',4:'暗夜精灵'}
CONTROLLERS={0:'用户',1:'电脑',2:'可营救',3:'中立',4:'中立电脑',5:'没有'}
MAP_CONTROLLERS={0:'没有',1:'用户',2:'电脑',3:'中立',4:'可营救/保留'}
STATES={0:'空槽',1:'游戏中',2:'已离开'}
SKINS={1:'人族',2:'兽族',4:'暗夜精灵',8:'亡灵',64:'已选种族',128:'被遗忘者'}


def label(values,value):return '未确认' if value is None else values.get(value,f'其他（原始值 {value}）')


def scalar_offset(memory,entry,name_entry,signature):
    """Mirror only `resolve player; if(nonnull) return player->uint32`.

    Matching the full success body rejects virtual/lazy/obfuscated getters;
    never scan beyond the bounded registration body or invoke its resolver.
    """
    if entry.signature!=signature:raise ValueError('读取接口签名不同')
    if name_entry.signature!='(Hplayer;)S':raise ValueError('玩家名称接口签名不同')
    raw=memory.read(entry.handler,64);name_code=memory.read(name_entry.handler,9)
    if raw[:5]!=bytes.fromhex('4883ec28e8') or raw[9:13]!=bytes.fromhex('4885c075') or name_code[:5]!=raw[:5]:
        raise ValueError('读取接口结构尚未核对')
    resolver=entry.handler+9+struct.unpack_from('<i',raw,5)[0]
    if resolver!=name_entry.handler+9+struct.unpack_from('<i',name_code,5)[0]:raise ValueError('玩家解析接口不同')
    branch=14+struct.unpack_from('<b',raw,13)[0]
    if not 14<=branch<=53:raise ValueError('读取接口分支越界')
    body=raw[branch:branch+11]
    if body[:2]!=b'\x8b\x80' or body[6:]!=bytes.fromhex('4883c428c3'):raise ValueError('读取接口不是已核对的直接字段')
    offset=struct.unpack_from('<I',body,2)[0]
    if not 0x20<=offset<=0x10000 or offset%4:raise ValueError('玩家字段偏移无效')
    return offset


def live_players(trainer):
    engine=trainer._engine_instance_24268();issues=[];teams=None
    with engine.session.lock:
        with read_context(trainer) as (_,memory,registry,mode,table):
            before=(engine.session.identity,engine.session.epoch,tuple(registry.players(memory)))
        # action8 is an existing getter-only query. With no selected unit its
        # zero-filled reply is NOT a verified list of teams.
        try:
            result=engine.fullclone(8,value=0,target=1)
            if result['rows'] and result['rows'][0]['a']==0 and len(result['teams'])==28 and all(-1<=v<28 for v in result['teams']):teams=result['teams']
            else:issues.append('实时队伍未读出：现有队伍查询需先选中任意单位；其他玩家信息仍可读取。')
        except Exception as exc:issues.append('实时队伍未确认：'+str(exc).split('; engine24268=',1)[0])
        with read_context(trainer) as (engine,memory,registry,mode,table):
            epoch=engine.session.epoch;identity=engine.session.identity;players=registry.players(memory)
            if before!=(identity,epoch,tuple(players)):raise ValueError('查询期间地图或连接已变化，请重新读取')
            name_entry=table.entries.get('GetPlayerName');offsets={}
            for key,(name,signature) in GETTERS.items():
                try:offsets[key]=scalar_offset(memory,table.entries[name],name_entry,signature)
                except Exception as exc:issues.append(name+'：'+str(exc))
            rows=[]
            for index,address in enumerate(players):
                row=dict(id=index,team=teams[index] if teams else None,name='',name_source='未读出')
                try:
                    row['name']=player_name(trainer,index)
                    if row['name']:row['name_source']='游戏读取值'
                except Exception as exc:issues.append(f'玩家{index+1}名字：'+str(exc))
                for key in GETTERS:
                    row[key]=None
                    if key in offsets:
                        try:
                            value=memory.read_u32(address+offsets[key])
                            row[key]=value-0x100000000 if key=='start_index' and value>=0x80000000 else value
                        except OSError:issues.append(f'玩家{index+1}的{key}本次未读出')
                rows.append(row)
            if players!=registry.players(memory) or engine.session.epoch!=epoch or engine.session.identity!=identity:raise ValueError('玩家读取期间地图或连接已变化，请重新读取')
            token=f'{identity.pid}:{identity.created}:{epoch}'
            return dict(rows=rows,issues=issues,context=token,profile=engine.session.profile.id,stamp=before)


def map_config(trainer):
    """Resolve the same proven source as quests, then read just W3I/WTS."""
    from war3_mpq import Archive
    snapshot,proof=current_script(trainer);source=proof['source']
    def info(archive):return parse_player_info(archive.read('war3map.w3i'),snapshot.strings_data)
    if source['kind']=='file':
        path=Path(source['path'])
        with Archive(path) as archive:
            if path.suffix.casefold()!='.w3n':result=info(archive)
            else:
                raw=archive.read(proof['metadata']['map_path'])
                with tempfile.TemporaryDirectory(prefix='war3-player-config-') as folder:
                    chapter=Path(folder)/'chapter.w3x';chapter.write_bytes(raw)
                    with Archive(chapter) as current:result=info(current)
    else:
        from war3_fullclone_casc import read_build_identity,CascArchive
        root=Path(source['root']);ident=read_build_identity(root)
        with CascArchive(root,ident) as archive:raw=archive.read(source['member'])
        with tempfile.TemporaryDirectory(prefix='war3-player-config-') as folder:
            chapter=Path(folder)/'current.w3x';chapter.write_bytes(raw)
            with Archive(chapter) as current:result=info(current)
    if not check_source(trainer,proof):raise ValueError('地图配置读取期间来源已变化')
    result.update(origin=snapshot.origin,trusted=proof.get('trusted',False))
    return result,proof


def combine(live,config=None,config_error=''):
    cfg={p['id']:p for p in (config or {}).get('players',[])}
    initial=(config or {}).get('groups',[]);rows=[]
    source={p['id']:p for p in live['rows']}
    for index in sorted(set(source)|set(cfg)):
        raw=source.get(index,{});saved=cfg.get(index);name=raw.get('name','');name_source=raw.get('name_source','未读出')
        if not name:
            if index in NEUTRALS:name=NEUTRALS[index];name_source='中立槽位标识'
            elif saved and saved['name']:name=saved['name'];name_source='地图配置名（非实时）'
            else:name=f'玩家 {index+1}';name_source='槽位编号'
        rows.append(dict(raw,id=index,slot=index+1,name=name,name_source=name_source,special=NEUTRALS.get(index),
            race_label=label(RACES,raw.get('race')),controller_label=label(CONTROLLERS,raw.get('controller')),
            state_label=label(STATES,raw.get('slot_state')),groups=[g['name'] for g in initial if index in g['members']],
            config=dict(saved,race_label=label(MAP_RACES,saved['race']),controller_label=label(MAP_CONTROLLERS,saved['controller']),skin_label=label(SKINS,saved['skin'])) if saved else None))
    # Neutral and empty slots are not ordinary team members, even when their
    # getter reports0. Unassigned(-1) must never be displayed as team0.
    runtime=[];normal=[p for p in rows if p['id']<24 and p.get('slot_state')==1]
    for team in sorted({p.get('team') for p in normal if p.get('team') is not None and p['team']>=0}):
        runtime.append(dict(key=f'team:{team}',name=f'原生队伍 {team+1}',members=[p['id'] for p in normal if p.get('team')==team]))
    for key,name,predicate in [('unassigned','未分配普通队伍',lambda p:p.get('team')==-1),('unknown','队伍未确认',lambda p:p.get('team') is None)]:
        members=[p['id'] for p in normal if predicate(p)]
        if members:runtime.append(dict(key=key,name=name,members=members))
    special=[p['id'] for p in rows if p['id'] in NEUTRALS]
    if special:runtime.append(dict(key='neutral',name='特殊中立槽位',members=special))
    inactive=[p['id'] for p in rows if p['id']<24 and p.get('slot_state')!=1]
    if inactive:runtime.append(dict(key='inactive',name='空槽／已离开／状态未确认',members=inactive))
    configured={p for g in initial for p in g['members']}
    initial=list(initial)
    remaining=[p['id'] for p in rows if p['id'] not in configured and p['id']<24]
    if remaining:initial.append(dict(key='config-other',name='未列入地图势力',members=remaining))
    other_special=[p for p in special if p not in configured]
    if other_special:initial.append(dict(key='config-neutral',name='特殊中立槽位',members=other_special))
    issues=list(live['issues'])+list((config or {}).get('issues',[]))
    if config_error:issues.append('地图初始配置未确认：'+config_error)
    if config and not config['trusted']:issues.append('地图配置来自安装包基础文件，本地覆盖优先级未确认；配置仅供参考。')
    return dict(success=True,rows=rows,initial_groups=initial,current_groups=runtime,issues=issues,
        source=(config or {}).get('origin',''),map_name=(config or {}).get('map_name',''),context=live['context'],
        profile=live['profile'],read_at=time.strftime('%H:%M:%S'),read_only=True)


def directory(api,refresh_map=False):
    if type(refresh_map) is not bool:raise ValueError('刷新参数无效')
    trainer=api.app.elephant_trainer();live=live_players(trainer)
    cached=getattr(api,'_player_directory_config',None);config=None;error=''
    try:
        if refresh_map or not cached or not check_source(trainer,cached[1]):
            api._player_directory_config=None
            cached=map_config(trainer);api._player_directory_config=cached
        config=cached[0]
    except Exception as exc:
        api._player_directory_config=None;error=str(exc)
    # A map change during file IO must not combine old live rows and new config.
    with read_context(trainer) as (engine,memory,registry,mode,table):
        if live['stamp']!=(engine.session.identity,engine.session.epoch,tuple(registry.players(memory))):raise ValueError('读取期间地图或连接已变化，请重新读取')
    return combine(live,config,error)
