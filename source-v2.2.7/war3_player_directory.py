"""Player directory and explicit drag action, with separate live/config sources.

No native slots, helper ABI, unit readers or game profile fields are changed.
Scalar offsets are admitted only after recognizing the current getter's exact
success branch. Independent action19 queries players without unit selection;
the original selected-owner action8 remains unchanged.
"""
from pathlib import Path
import re
import struct
import tempfile
import time

from war3_fullclone_runtime import read_context,player_name
from war3_fullclone_source import current_script,check_source
from war3_fullclone_quests import _merge_strings,game_text_locale
from war3_player_map_info import parse_player_info
from war3_fullclone_protocol import DiplomacySlotUnavailable
from war3_services.fullclone import applied_diplomacy_templates,diplomacy_template_label,pinned_native_teams

GETTERS={
    'color':('GetPlayerColor','(Hplayer;)Hplayercolor;'),
    'controller':('GetPlayerController','(Hplayer;)Hmapcontrol;'),
    'race':('GetPlayerRace','(Hplayer;)Hrace;'),
    'slot_state':('GetPlayerSlotState','(Hplayer;)Hplayerslotstate;'),
    'start_index':('GetPlayerStartLocation','(Hplayer;)I'),
}
NEUTRALS={24:'中立敌对',25:'中立受害者',26:'中立额外',27:'中立被动'}
NEUTRAL_BASE={24:'neutral hostile',25:'neutral victim',26:'neutral extra',27:'neutral passive'}
RACES={1:'人族',2:'兽族',3:'亡灵',4:'暗夜精灵',5:'恶魔',7:'其他'}
MAP_RACES={0:'可选择/随机',1:'人族',2:'兽族',3:'亡灵',4:'暗夜精灵'}
CONTROLLERS={0:'用户',1:'电脑',2:'可营救',3:'中立',4:'中立电脑',5:'没有'}
MAP_CONTROLLERS={0:'没有',1:'用户',2:'电脑',3:'中立',4:'可营救/保留'}
STATES={0:'空槽',1:'游戏中',2:'已离开'}
SKINS={1:'人族',2:'兽族',4:'暗夜精灵',8:'亡灵',64:'已选种族',128:'被遗忘者'}


def label(values,value):return '未确认' if value is None else values.get(value,f'其他（原始值 {value}）')


def force_suffix(members,forces,active):
    """Name a native team after the map force that staffs only that team.

    A force that also holds active players of another native team cannot name
    either team, so the title keeps the bare team number instead of guessing.
    """
    team=set(members)
    names={name for name,people in forces if name and team<=people and not (people&active)-team}
    return f'（{names.pop()}）' if len(names)==1 else ''


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
    engine=trainer._engine_instance_24268();issues=[];teams=None;verified_players=None
    with engine.session.lock:
        with read_context(trainer) as (_,memory,registry,mode,table):
            before=(engine.session.identity,engine.session.epoch,tuple(registry.players(memory)))
        # Independent player query: unlike selected-owner action8 this does not
        # require a selected unit. Empty/zero replies remain unconfirmed.
        try:
            result=engine.fullclone(19,target=0)
            if result['rows'] and result['rows'][0]['a']==0 and len(result['teams'])==28 and all(-1<=v<28 for v in result['teams']):
                teams=pinned_native_teams(engine.session.cache,result['teams'])
                verified_players=result['rows'][0].get('c')
            else:issues.append('实时队伍未读出：指定玩家查询没有返回已确认的队伍列表；其他玩家信息仍可读取。')
        except Exception as exc:issues.append('实时队伍未确认：'+str(exc).split('; engine24268=',1)[0])
        with read_context(trainer) as (engine,memory,registry,mode,table):
            epoch=engine.session.epoch;identity=engine.session.identity;players=registry.players(memory)
            if before!=(identity,epoch,tuple(players)):raise ValueError('查询期间地图或连接已变化，请重新读取')
            name_entry=table.entries.get('GetPlayerName');offsets={}
            for key,(name,signature) in GETTERS.items():
                try:offsets[key]=scalar_offset(memory,table.entries[name],name_entry,signature)
                except Exception as exc:issues.append(name+'：'+str(exc))
            applied=applied_diplomacy_templates(engine.session.cache,players)
            local_id=None
            try:local_id=players.index(registry.local_player_for_mode(memory,mode.value))
            except Exception as exc:issues.append('本地玩家未确认：'+str(exc))
            rows=[]
            for index,address in enumerate(players):
                row=dict(id=index,team=teams[index] if teams else None,diplomacy=applied.get(index),is_local=index==local_id,name='',name_source='未读出')
                if verified_players is not None:
                    row['diplomacy_available']=bool(verified_players&(1<<index))
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
    def info(archive,campaign_base=b''):
        base=_merge_strings(campaign_base,archive.read('war3map.wts',optional=True) or b'')
        return parse_player_info(archive.read('war3map.w3i'),snapshot.strings_data,base_wts=base)
    if source['kind']=='file':
        path=Path(source['path'])
        with Archive(path) as archive:
            if path.suffix.casefold()!='.w3n':result=info(archive)
            else:
                raw=archive.read(proof['metadata']['map_path'])
                with tempfile.TemporaryDirectory(prefix='war3-player-config-') as folder:
                    chapter=Path(folder)/'chapter.w3x';chapter.write_bytes(raw)
                    campaign_base=archive.read('war3campaign.wts',optional=True) or b''
                    with Archive(chapter) as current:result=info(current,campaign_base)
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


def usable_name(name):
    return bool(name and name.strip()) and not re.fullmatch(r'(?:TRIGSTR|STR)_\d+(?:（文字表缺失）)?',name.strip(),re.I)


def localized_aliases(config):
    if not config or not config.get('trusted'):return {}
    return {p['id']:(p['base_name'],p['name']) for p in config['players']
            if usable_name(p.get('base_name')) and usable_name(p.get('name')) and p['base_name']!=p['name']}


def display_name(index,raw,saved,alias,previous):
    name=raw.get('name','')
    generic=name.strip().casefold() in (f'player {index+1}',f'玩家 {index+1}',f'玩家{index+1}')
    # The same slot's base and localized entries are paired by string ID.
    # A human nickname or a different runtime name remains the live value.
    localized=alias if raw.get('controller')!=0 and not raw.get('is_local') else None
    if usable_name(name) and not generic:
        if name.strip().casefold()==NEUTRAL_BASE.get(index):return NEUTRALS[index],'中立槽位标识'
        if localized and name.strip().casefold()==localized[0].strip().casefold():return localized[1],'地图本地化名'
        return name,raw.get('name_source','游戏读取值')
    if index in NEUTRALS:return NEUTRALS[index],'中立槽位标识'
    if previous:
        last,source,state=previous
        if source in ('游戏读取值','上次游戏读取值') and raw.get('slot_state') in (None,state):
            if localized and last.strip().casefold()==localized[0].strip().casefold():return localized[1],'地图本地化名'
            return last,'上次游戏读取值'
    if saved and usable_name(saved.get('name')):return saved['name'],'地图配置名（非实时）'
    if alias:return alias[1],'地图本地化名'
    if not saved and previous and previous[1]=='地图配置名（非实时）':return previous[0],previous[1]
    return f'玩家 {index+1}','槽位编号'


def combine(live,config=None,config_error='',*,aliases=None,previous_names=None):
    cfg={p['id']:p for p in (config or {}).get('players',[])}
    if aliases is None:aliases=localized_aliases(config)
    previous_names=previous_names or {}
    initial=(config or {}).get('groups',[]);rows=[]
    source={p['id']:p for p in live['rows']}
    for index in sorted(set(source)|set(cfg)):
        raw=source.get(index,{});saved=cfg.get(index)
        name,name_source=display_name(index,raw,saved,aliases.get(index),previous_names.get(index))
        diplomacy=raw.get('diplomacy')
        if type(diplomacy) is not int or not 0<=diplomacy<=13:diplomacy=None
        rows.append(dict(raw,id=index,slot=index+1,name=name,name_source=name_source,special=NEUTRALS.get(index),
            race_label=label(RACES,raw.get('race')),controller_label=label(CONTROLLERS,raw.get('controller')),
            state_label=label(STATES,raw.get('slot_state')),groups=[g['name'] for g in initial if index in g['members']],
            diplomacy=diplomacy,diplomacy_label=diplomacy_template_label(diplomacy),
            config=dict(saved,race_label=label(MAP_RACES,saved['race']),controller_label=label(MAP_CONTROLLERS,saved['controller']),skin_label=label(SKINS,saved['skin'])) if saved else None))
    # Neutral and empty slots are not ordinary team members, even when their
    # getter reports0. Unassigned(-1) must never be displayed as team0.
    runtime=[];normal=[p for p in rows if p['id']<24 and (p.get('slot_state')==1 or p.get('is_local'))]
    active={p['id'] for p in normal};forces=[(g['name'],set(g['members'])) for g in initial if g.get('members')]
    for team in sorted({p.get('team') for p in normal if p.get('team') is not None and p['team']>=0}):
        members=[p['id'] for p in normal if p.get('team')==team]
        runtime.append(dict(key=f'team:{team}',name=f'原生队伍 {team+1}{force_suffix(members,forces,active)}',members=members))
    for key,name,predicate in [('unassigned','未分配普通队伍',lambda p:p.get('team')==-1),('unknown','队伍未确认',lambda p:p.get('team') is None)]:
        members=[p['id'] for p in normal if predicate(p)]
        if members:runtime.append(dict(key=key,name=name,members=members))
    special=[p['id'] for p in rows if p['id'] in NEUTRALS]
    if special:runtime.append(dict(key='neutral',name='特殊中立槽位',members=special))
    inactive=[p['id'] for p in rows if p['id']<24 and p.get('slot_state')!=1 and not p.get('is_local')]
    if inactive:runtime.append(dict(key='inactive',name='空槽／已离开／状态未确认',members=inactive))
    configured={p for g in initial for p in g['members']}
    initial=list(initial)
    remaining=[p['id'] for p in rows if p['id'] not in configured and p['id']<24]
    if remaining:initial.append(dict(key='config-other',name='未列入地图势力',members=remaining))
    other_special=[p for p in special if p not in configured]
    if other_special:initial.append(dict(key='config-neutral',name='特殊中立槽位',members=other_special))
    # R31.12: unchanged players stay in their original team. Team names are
    # bound to the original membership, never renamed after a player is moved.
    titles={}
    for target in range(12):
        members=[p['id'] for p in normal if p.get('team')==target]
        suffix=force_suffix(members,forces,active) if members else ''
        titles[target]=f'{suffix[1:-1] if suffix else "未读取队伍名"}（队伍 {target+1}）'
    titles.update({12:'中立敌对',13:'中立被动'})
    members={};unknown=[]
    for p in rows:
        if p['id'] not in active and p['id'] not in (24,27) and not (p['id'] in inactive and p['diplomacy'] is not None):
            continue
        target=p['diplomacy']
        if target is None:
            original=p.get('team')
            target=12 if p['id']==24 else 13 if p['id']==27 else original if type(original) is int and 0<=original<12 else None
        if type(target) is int and 0<=target<14:
            members.setdefault(target,[]).append(p['id']);p['diplomacy_label']=titles[target]
        else:unknown.append(p)
    # Retain empty original teams as drop destinations after all their players
    # leave; an absent/ambiguous team number is never guessed from force order.
    known={p['team'] for p in normal if type(p.get('team')) is int and 0<=p['team']<12}
    templates=[dict(key=f'diplomacy:{target}',name=titles[target],members=members.get(target,[]),template=target)
        for target in sorted(known|set(members)|{12,13})]
    for g in initial:
        people=[p for p in unknown if p['id'] in g['members']]
        if people:
            name=f'{g["name"]}（队伍未确认）'
            templates.append(dict(key='diplomacy-origin:'+g['key'],name=name,members=[p['id'] for p in people]))
            for p in people:p['diplomacy_label']=name
            unknown=[p for p in unknown if p not in people]
    if unknown:templates.append(dict(key='diplomacy-unknown',name='队伍未确认',members=[p['id'] for p in unknown]))
    for p in unknown:p['diplomacy_label']='队伍未确认'
    other_neutral=[p for p in special if p not in (24,27)]
    if other_neutral:templates.append(dict(key='neutral',name='其他特殊中立槽位',members=other_neutral))
    inactive_origins=[p['id'] for p in rows if p['id'] in inactive and p['diplomacy'] is None]
    if inactive:templates.append(dict(key='inactive',name='空槽／已离开／状态未确认',members=inactive_origins))
    for p in rows:
        if p['id'] in inactive_origins:p['diplomacy_label']='空槽／已离开／状态未确认'
        elif p['id'] in other_neutral:p['diplomacy_label']=p['special']
    issues=list(live['issues'])+list((config or {}).get('issues',[]))
    if config_error:issues.append('地图初始配置未确认：'+config_error)
    if config and not config['trusted']:issues.append('地图配置来自安装包基础文件，本地覆盖优先级未确认；配置仅供参考。')
    return dict(success=True,rows=rows,initial_groups=initial,current_groups=runtime,diplomacy_groups=templates,issues=issues,
        source=(config or {}).get('origin',''),map_name=(config or {}).get('map_name',''),context=live['context'],
        profile=live['profile'],read_at=time.strftime('%H:%M:%S'),read_only=True)


def directory(api,refresh_map=False):
    if type(refresh_map) is not bool:raise ValueError('刷新参数无效')
    trainer=api.app.elephant_trainer();live=live_players(trainer);locale=game_text_locale()
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
        stamp=(live['stamp'],locale)
        names=getattr(api,'_player_directory_names',None)
        old_aliases,previous_names=names[1:] if names and names[0]==stamp else ({},{})
        aliases=localized_aliases(config) if config is not None else old_aliases
        result=combine(live,config,error,aliases=aliases,previous_names=previous_names)
        api._player_directory_names=(stamp,aliases,{
            p['id']:(p['name'],p['name_source'],p.get('slot_state')) for p in result['rows']})
        return result


def page_context(api):
    """Validate a remembered page without enumerating players or reading files."""
    with read_context(api.app.elephant_trainer()) as (engine,memory,registry,mode,table):
        identity=engine.session.identity
        return dict(success=True,context=f'{identity.pid}:{identity.created}:{engine.session.epoch}')


def move_player(api,player,target,context):
    """Drag applies the existing diplomacy semantics to an explicit player.

    A page from a previous process/map is rejected inside the serialized action;
    no unit selection, ownership, original-team pin or control record changes.
    """
    if type(player) is not int or player not in (*range(24),24,27):raise ValueError('不支持拖动该玩家')
    if type(target) is not int or target not in range(14):raise ValueError('目标外交模板无效')
    if type(context) is not str or not context:raise ValueError('请先读取当前地图玩家')
    applied=False
    def apply():
        nonlocal applied
        trainer=api.app.elephant_trainer();engine=trainer._engine_instance_24268()
        with engine.session.lock:
            identity=engine.session.identity;epoch=engine.session.epoch
            if identity is None or context!=f'{identity.pid}:{identity.created}:{epoch}':
                raise ValueError('地图或连接已变化，请重新读取玩家后再拖放')
            # fullclone_team revalidates the session and expected epoch in the
            # engine before its first query and before the write.
            try:
                result=trainer.fullclone_team(target,player=player,expected_epoch=epoch)
            except Exception as exc:
                unavailable=exc if isinstance(exc,DiplomacySlotUnavailable) else exc.__cause__
                if not isinstance(unavailable,DiplomacySlotUnavailable):raise
                return str(unavailable)
            if not result.get('changed'):raise ValueError('未确认外交模板修改成功，请重新读取')
            applied=True
            return f'玩家 {player+1} 已套用{diplomacy_template_label(target)}外交模板（控制权限保持不变）'
    message=api._run_action(apply,'fullclone:move_player_team')
    return dict(success=True,applied=applied,message=message,player=player,target=target,context=context)
