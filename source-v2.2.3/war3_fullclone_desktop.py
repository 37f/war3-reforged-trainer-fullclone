"""Additional desktop commands; exposed through the existing serialized RPC."""
from war3_fullclone_application import DEFAULTS


def settings(api):
    return dict(success=True,options=dict(api.app.fc_settings()))


def set_option(api,key,value):
    if key not in DEFAULTS:raise ValueError('未知扩展设置')
    default=DEFAULTS[key]
    if type(default) is bool and type(value) is not bool:raise ValueError('开关参数无效')
    if type(default) is int and (type(value) is not int or value not in range(28)):raise ValueError('玩家或队伍参数无效')
    if type(default) is str and (type(value) is not str or len(value)>128):raise ValueError('扩展参数无效')
    if key=='team' and value not in range(14):raise ValueError('队伍参数无效')
    if key in ('owner_player','target_player') and value not in (*range(24),24,27):raise ValueError('玩家槽位无效')
    if key=='color' and value not in range(24):raise ValueError('颜色参数无效')
    if key=='owner_mode' and value not in ('self','selected','player'):raise ValueError('归属参数无效')
    api.app.fc_settings()[key]=value
    return settings(api)


def owner_status(api):
    t=api.app.elephant_trainer();row=t.fullclone_owner()
    epoch=t._engine_instance_24268().session.epoch
    if row is None:return dict(success=True,message='未选中单位',owner=None)
    p=row['a'];team=row['team'];name=''
    try:name=t.fullclone_player_name(row['a'])
    except Exception:pass  # Optional name cannot hide the proven player/team.
    final=t.fullclone_owner()
    if final is None or any(final[k]!=row[k] for k in ('handle','owner','rawcode')) or t._engine_instance_24268().session.epoch!=epoch:
        return dict(success=True,message='选中单位正在变化，等待下一次刷新',owner=None)
    label=f'玩家 {p+1}'
    if p in (24,27):label+='（中立敌对）' if p==24 else '（中立被动）'
    if name:label+=f'（{name}）'
    elif p not in (24,27):label+='（名称暂无法读取）'
    # A neutral's raw team0 is not ordinary team1; match the directory wording.
    label+='：'+(f'特殊中立槽位（原生队伍原始值 {team}）' if p in (24,27) else
        f'原生队伍 {team+1}' if team>=0 else f'未分配普通队伍（原始值 {team}）')
    saved=t._engine_instance_24268().session.cache.get('fullclone_teams',{}).get(row['owner'])
    if saved and saved['applied'] is not None:
        target=saved['applied'];label+='；当前外交模板：'+(f'队伍 {target+1}' if target<12 else '中立敌对' if target==12 else '中立被动')
    return dict(success=True,message=label,owner=p+1,name=name,team=team,unit=row['rawcode'])


def action(api,name):
    message=api._run_action(lambda:api.app.fc_action(name),'fullclone:'+name)
    if name not in ('join_team','restore_team','restore_all_teams'):api._mark_units_changed()
    return dict(success=True,message=str(message or '操作完成'))
