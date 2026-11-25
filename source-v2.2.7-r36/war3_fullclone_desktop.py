"""Additional desktop commands; exposed through the existing serialized RPC."""
from war3_fullclone_application import DEFAULTS,restore_team_records


def settings(api):
    return dict(success=True,options=dict(api.app.fc_settings()),localAI=api.app.fc_local_ai_status(),
                heroCandidates=api.app.fc_hero_candidates())


def set_option(api,key,value):
    if key not in DEFAULTS:raise ValueError('未知扩展设置')
    default=DEFAULTS[key]
    if type(default) is bool and type(value) is not bool:raise ValueError('开关参数无效')
    if key=='ai_radius':
        from war3_fullclone_ai_protocol import AI_RANGE
        if type(value) is not int or value not in AI_RANGE:raise ValueError('AI 托管目标搜索范围无效')
    elif type(default) is int and (type(value) is not int or value not in range(28)):
        raise ValueError('玩家或队伍参数无效')
    limit=2048 if key.startswith('supply_text_') else 24 if key.startswith('supply_name_') else 128
    if type(default) is str and (type(value) is not str or len(value)>limit):raise ValueError('扩展参数无效')
    if key=='team' and value not in range(14):raise ValueError('队伍参数无效')
    if key in ('owner_player','target_player') and value not in (*range(24),24,27):raise ValueError('玩家槽位无效')
    if key=='color' and value not in range(24):raise ValueError('颜色参数无效')
    if key=='owner_mode' and value not in ('self','selected','player'):raise ValueError('归属参数无效')
    if key=='army_scope' and value not in ('all','heroes','nonheroes'):raise ValueError('全军补满范围无效')
    if key=='item_filter_mode' and value not in ('all','include','exclude'):raise ValueError('物品聚集筛选方式无效')
    if key=='formation' and value not in ('original','square','ring','line','scatter'):raise ValueError('复制阵型无效')
    if key=='freeze_scope' and value not in ('all','heroes','nonheroes'):raise ValueError('冻结范围无效')
    if key=='supply_slot' and value not in ('1','2','3'):raise ValueError('补给包编号无效')
    if key=='supply_target' and value not in ('hero','ground'):raise ValueError('补给投放方式无效')
    if key=='point_spell':
        from war3_fullclone_extra_protocol import SPELLS
        if value not in SPELLS:raise ValueError('固定技能无效')
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
    session=t._engine_instance_24268().session
    if final is None or any(final[k]!=row[k] for k in ('handle','owner','rawcode')) or session.epoch!=epoch:
        return dict(success=True,message='选中单位正在变化，等待下一次刷新',owner=None)
    label=f'玩家 {p+1}'
    if p in (24,27):label+='（中立敌对）' if p==24 else '（中立被动）'
    if name:label+=f'（{name}）'
    elif p not in (24,27):label+='（名称暂无法读取）'
    # A neutral's raw team0 is not ordinary team1; match the directory wording.
    details=f'特殊中立槽位（原生队伍原始值 {team}）' if p in (24,27) else (
        f'原生队伍 {team+1}' if team>=0 else f'未分配普通队伍（原始值 {team}）')
    saved=session.cache.get('fullclone_teams',{}).get(row['owner'])
    if saved and saved['applied'] is not None:
        target=saved['applied'];details+='；当前外交模板：'+(f'队伍 {target+1}' if target<12 else '中立敌对' if target==12 else '中立被动')
    identity=session.identity
    context=f'{identity.pid}:{identity.created}:{epoch}'
    return dict(success=True,message=label+'：'+details,owner=p+1,name=name,team=team,
                unit=row['rawcode'],details=details,context=context)


def control_player(api,player,context):
    from war3_fullclone_protocol import TEAM_PLAYERS

    if type(player) is not int or player not in TEAM_PLAYERS:raise ValueError('玩家槽位无效')
    if type(context) is not str or not context:raise ValueError('尚未确认当前地图玩家')
    def toggle():
        trainer=api.app.elephant_trainer()
        session=trainer._engine_instance_24268().session
        with session.lock:
            identity=session.identity
            epoch=session.epoch
            if identity is None or context!=f'{identity.pid}:{identity.created}:{epoch}':
                raise ValueError('地图或连接已变化，请重新读取玩家信息')
            result=trainer.fullclone_toggle_control(player=player,expected_epoch=epoch)
        if result.get('local'):return '该玩家是自己，已由你控制'
        if not result['changed']:return '尚未确认当前地图玩家'
        return f'已恢复玩家 {player+1} 的控制状态' if result['restored'] else f'已控制玩家 {player+1}（阵营不变）'
    return dict(success=True,message=api._run_action(toggle,'fullclone:control_player'))


def action(api,name):
    if name=='supply_save':
        from war3_fullclone_supplies import save
        return dict(success=True,message=save(api.app.fc_settings()))
    if name=='restore_all_teams':
        result={}
        def restore():
            result.update(restore_team_records(api.app.elephant_trainer()))
            return result['message']
        api._run_action(restore,'fullclone:'+name)
        return dict(success=True,**result)
    message=api._run_action(lambda:api.app.fc_action(name),'fullclone:'+name)
    if name in ('local_ai_start', 'local_ai_stop'):
        return dict(success=True,message=message,localAI=api.app.fc_local_ai_status())
    if name in ('hero_candidate_1', 'hero_candidate_2', 'hero_candidates_clear'):
        return dict(success=True,message=message,heroCandidates=api.app.fc_hero_candidates())
    if name not in ('join_team','restore_team','restore_all_teams'):api._mark_units_changed()
    return dict(success=True,message=str(message or '操作完成'))


def operation_history(api):
    from war3_fullclone_history import snapshot

    try:
        engine=api.app.elephant_trainer()._engine_instance_24268()
        with engine.session.lock, engine.memory_factory(engine.pid) as memory:
            engine.session.prepare(memory)
            return dict(success=True,available=True,entries=snapshot(engine.session.cache))
    except (OSError, RuntimeError, ValueError):
        return dict(success=True,available=False,entries=[])


def undo_operation(api, operation_id):
    from war3_fullclone_history import undo

    result={}
    def apply():
        engine=api.app.elephant_trainer()._engine_instance_24268()
        with engine.session.lock:
            with engine.memory_factory(engine.pid) as memory:
                engine.session.prepare(memory)
            result.update(undo(engine,operation_id))
        if result.get('kind')=='owner' and result['undone']:
            api._mark_units_changed()
        return '撤销完成，请查看逐项结果' if result['undone'] else '当前没有可撤销的目标'
    message=api._run_action(apply,'fullclone:undo_operation')
    return dict(success=True,message=message,**result)
