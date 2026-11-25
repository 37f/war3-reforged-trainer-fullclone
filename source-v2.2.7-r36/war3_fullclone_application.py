"""R31 UI commands. Settings are separate from all original reader parameters."""
from random import getrandbits
from time import monotonic

DEFAULTS=dict(owner_enabled=False,owner_mode='self',owner_player=0,target_player=1,
    team=0,replace_id='zhyd',color=0,hero_custom=False,attributes_custom=False,
    mine_amount='100000',army_scope='all',item_filter_mode='all',item_filter_ids='',
    formation='original',formation_gap='128',freeze_scope='all',freeze_buildings=False,
    supply_slot='1',supply_target='hero',supply_name_1='恢复用品',supply_name_2='回城用品',supply_name_3='测试装备',
    supply_text_1='',supply_text_2='',supply_text_3='',point_spell='AUin',
    ai_radius=900,ai_combat=True,ai_harvest=False,ai_build=False,ai_spells=False,
    ai_research=False,ai_creeps=False,ai_train=False,ai_team=False,
    ai_pickup=False,ai_destructibles=False,ai_neutral_creatures=False,ai_neutral_buildings=False)


def restore_team_records(trainer):
    result=trainer.fullclone_restore_all_teams()
    skipped=result.get('skipped',())
    if skipped:
        slots='、'.join(str(p+1) for p in skipped)
        message=f'已恢复 {result["changed"]}/{result["total"]} 个玩家。玩家 {slots} 槽位身份未确认，已保留其原记录'
    elif result['total']:
        message=f'已恢复 {result["changed"]} 个玩家真正原队伍（共享控制权限保持不变）'
    else:
        message='本次地图没有可恢复的原队伍记录'
    return dict(result,message=message)


class FullCloneApplication:
    def fc_hero_candidates(self):
        from war3_services.hero_skill_swap import list_candidates

        trainer = self.view.value('state').get('trainer')
        engine = getattr(trainer, '_engine24268', None)
        if engine is None or (trainer.pid, trainer.hwnd) != (engine.pid, engine.hwnd):
            return [None, None]
        return list_candidates(engine.session)

    def fc_local_ai_status(self):
        state = self.view.value('state')
        control = state.get('fullclone_local_ai')
        result = dict(active='fullclone_local_ai' in state,
                      stopped=state.get('fullclone_local_ai_interrupted', False),
                      detail=state.get('fullclone_local_ai_detail', ''),
                      progress=control['progress'] if control else None)
        if control and control.get('stock_openings') is not None:
            result['stockOpenings'] = control['stock_openings']
        if control and control.get('stock_waves') is not None:
            result['stockWaves'] = control['stock_waves']
        return result

    def fc_local_ai_features(self):
        options = self.fc_settings()
        return sum(bit for bit, key in ((1, 'ai_combat'), (2, 'ai_harvest'),
                                        (4, 'ai_build'), (8, 'ai_spells'),
                                        (16, 'ai_research'), (32, 'ai_creeps'),
                                        (64, 'ai_train'), (128, 'ai_team'), (256, 'ai_pickup'),
                                        (512, 'ai_destructibles'), (1024, 'ai_neutral_creatures'),
                                        (2048, 'ai_neutral_buildings')) if options[key])

    def fc_local_ai(self, enabled):
        state = self.view.value('state')
        state.pop('fullclone_local_ai_interrupted', None)
        state.pop('fullclone_local_ai_detail', None)
        if not enabled:
            state.pop('fullclone_local_ai', None)
            return '已停止本方 AI 托管'
        if 'fullclone_local_ai' not in state:
            if not self.fc_local_ai_features():
                raise ValueError('请至少开启一项 AI 托管功能')
            trainer = self.trainer()
            engine = trainer._engine_instance_24268()
            with engine.session.lock:
                ready = engine.fullclone_local_ai()
                control = dict(trainer=trainer, engine=engine, epoch=engine.session.epoch,
                               owner=ready['owner'], cursor=0,
                               build_cooldowns=engine.session.cache.setdefault('fullclone_ai_build_cooldowns', {}),
                               build_state=engine.session.cache.setdefault('fullclone_ai_build_sites', {}).setdefault(ready['owner'], {}),
                               next_research=engine.session.cache.get('fullclone_ai_next_research', 0),
                               train_cooldowns=engine.session.cache.setdefault('fullclone_ai_train_cooldowns', {}),
                               hero_seed=engine.session.cache.setdefault('fullclone_ai_hero_seed', getrandbits(32)),
                               progress=None)
            state['fullclone_local_ai'] = control
            self.view.value('root').after(1500, self.fc_local_ai_tick, control)
        return '已开启本方 AI 托管'

    def fc_local_ai_tick(self, control):
        # The desktop timer runs under the same operation lock as button actions.
        # The record identity invalidates any callback queued before a stop/restart.
        state = self.view.value('state')
        if state.get('closing') or state.get('fullclone_local_ai') is not control:
            return
        trainer, engine = control['trainer'], control['engine']
        try:
            if (state.get('trainer') is not trainer or
                    (trainer.pid, trainer.hwnd) != (engine.pid, engine.hwnd)):
                raise RuntimeError('本地游戏连接已变化')
            features = self.fc_local_ai_features()
            if not features:
                state.pop('fullclone_local_ai', None)
                return
            self.fc_local_ai_orders(control, features, self.fc_settings()['ai_radius'])
        except Exception as exc:
            state.pop('fullclone_local_ai', None)
            state['fullclone_local_ai_interrupted'] = True
            state['fullclone_local_ai_detail'] = str(exc)
            return
        self.view.value('root').after(1500, self.fc_local_ai_tick, control)

    def fc_local_ai_orders(self, control, features, radius):
        from war3_fullclone_ai_protocol import (BUILD_SUPPLY, DESTRUCTIBLES, RESEARCH_BUILDING, TACTICS,
                                               TRAIN_BUILDING, TRAIN_FOOD, TRAIN_RESOURCES, TRAIN_REJECTED)

        engine = control['engine']
        now = monotonic()
        build_cooldowns = control['build_cooldowns']
        build_state = control['build_state']
        pending = build_state.get('pending') if features & 4 else None
        allow_build = bool(features & 4) and pending is None
        blocked_builds = sum(kind for kind, until in build_cooldowns.items() if now < until) if allow_build else 0
        train_cooldowns = control['train_cooldowns']
        allow_train = bool(features & 64) and pending is None
        blocked_train = sum(kind for kind, until in train_cooldowns.items() if now < until) if allow_train else 0
        stock_options = {}
        if allow_train and control.get('hero_seed'):
            stock_options['hero_seed'] = control['hero_seed']
        if pending:
            stock_options['pending_site'] = pending['site']
        elif allow_build and 'avoid' in build_state:
            stock_options['avoid_site'] = build_state['avoid']
        if features & 68 == 68 or features & TACTICS:
            from war3_fullclone_ai_stock import stock_rules_for_session
            openings, waves = stock_rules_for_session(control['trainer'], engine.session)
            if openings and features & 68 == 68:
                stock_options['openings'] = openings
            if waves and features & TACTICS:
                stock_options['wave_troops'] = waves
        destructible_note = ''
        if features & DESTRUCTIBLES:
            from war3_fullclone_ai_destructibles import selectable_types_for_session
            types = selectable_types_for_session(control['trainer'], engine.session)
            if types is None:
                destructible_note = '无法确认当前地图的可选中属性，已跳过攻击可破坏物。'
            stock_options['selectable_destructibles'] = types or ()
        result = engine.fullclone_local_ai(
            owner=control['owner'], cursor=control['cursor'], expected_epoch=control['epoch'],
            radius=radius, features=features,
            allow_build=allow_build, blocked_builds=blocked_builds,
            allow_research=bool(features & 16) and pending is None and now >= control['next_research'],
            allow_train=allow_train, blocked_train=blocked_train, **stock_options)
        control['cursor'] = result['cursor']
        counts = ('mined', 'wood', 'built', 'spells', 'researched', 'creeps', 'trained', 'upgraded')
        progress = dict(control['progress'] or dict.fromkeys(counts, 0))
        for name in counts:
            progress[name] += result[name]
        build_note = ''
        if pending and result['build_started']:
            kind = pending['kind']
            if kind == BUILD_SUPPLY:
                build_cooldowns[kind] = now + 60
            build_state.pop('pending')
            build_state.pop('avoid', None)
            progress['buildStarted'] = progress.get('buildStarted', 0) + 1
            build_note = '已确认建筑开工'
        elif pending and now >= pending['deadline']:
            build_state['avoid'] = build_state.pop('pending')['site']
            progress['buildTimeouts'] = progress.get('buildTimeouts', 0) + 1
            build_note = '未确认开工，下次尝试其他落点'
        elif pending:
            build_note = '已派工，等待确认开工'
        elif result['built']:
            kind = result['built_kind']
            build_state['pending'] = dict(site=result['ordered_site'], kind=kind, deadline=now + 25)
            build_note = '已派工，等待确认开工'
        if result['researched']:
            control['next_research'] = engine.session.cache['fullclone_ai_next_research'] = monotonic() + 12
        if result['train_kind']:
            train_cooldowns[result['train_kind']] = monotonic() + result['train_wait']
        if result.get('revive_queued'):
            progress['revives'] = progress.get('revives', 0) + 1
        progress['harvestNote'], progress['buildNote'] = self.fc_local_ai_notes(
            result['status'], features, result['mined'] or result['wood'], result['built'], blocked_builds)
        if build_note:
            progress['buildNote'] = build_note
        progress['destructibleNote'] = destructible_note
        progress['researchNote'] = ''
        if features & 16:
            if monotonic() < control['next_research']:
                progress['researchNote'] = '已提交科技研究，等待下次排队'
            elif not result['status'] & RESEARCH_BUILDING:
                progress['researchNote'] = '本轮没有找到支持研究的原版建筑'
            else:
                progress['researchNote'] = '本轮暂无可排队科技，请检查建筑、前置和资源'
        control['stock_openings'] = (sum(plan is not None for plan in stock_options.get('openings', ()))
                                     if features & 68 == 68 else None)
        control['stock_waves'] = sum(map(bool, stock_options.get('wave_troops', ()))) if features & TACTICS else None
        if features & TACTICS:
            progress['tactics'] = progress.get('tactics', 0) + result['tactics_issued']
            progress['tacticsReady'] = result['tactics_ready']
            progress['tacticsNote'] = (
                '本轮未下达编队指令', '基地附近发现敌军，优先回防',
                '部队向英雄集结', '编队向可见野怪推进', '编队向敌军或电脑出生点推进',
            )[result['tactics_mode']]
        progress['trainNote'] = ''
        if features & 64:
            status = result['status']
            if pending and not result['build_started']:
                progress['trainNote'] = '等待开工，暂留建造所需资源'
            elif result.get('revive_queued'):
                progress['trainNote'] = '游戏已接受英雄复活指令'
            elif 'revive_queued' in result:
                progress['trainNote'] = '阵亡英雄等待祭坛复活'
            elif result['upgraded']:
                progress['trainNote'] = '游戏已接受主基地升级指令'
            elif result['trained']:
                progress['trainNote'] = '游戏已接受训练指令'
            elif blocked_train:
                progress['trainNote'] = '等待生产建筑继续工作'
            elif not status & TRAIN_BUILDING:
                progress['trainNote'] = '当前没有可用的原版训练建筑'
            elif status & TRAIN_FOOD:
                progress['trainNote'] = '人口空间不足，等待补充人口建筑'
            elif status & TRAIN_RESOURCES:
                progress['trainNote'] = '训练所需的金币或木材不足'
            elif status & TRAIN_REJECTED:
                progress['trainNote'] = '游戏未接受训练指令，请检查地图限制或前置条件'
            else:
                progress['trainNote'] = '训练建筑正在工作，或已补足当前需要的工人'
        control['progress'] = progress

    @staticmethod
    def fc_local_ai_notes(status, features, gathered, built, blocked_builds):
        from war3_fullclone_ai_protocol import WORKER, AVAILABLE, BUILD_INTENT, RESOURCES, HALL, SITE, MINE, BUILDER

        harvest = build = ''
        if features & 2:
            if gathered:
                harvest = '本轮已派出采集指令'
            elif not status & WORKER:
                harvest = '本轮未读到受支持的工人'
            elif not status & AVAILABLE:
                harvest = '本轮没有空闲的采集工人'
            elif not status & MINE:
                harvest = '本轮未找到可采集的可见金矿，也未派出伐木指令'
            else:
                harvest = '本轮已有采集目标，暂无新指令'
        if features & 4:
            if built:
                build = '游戏已接受建造指令'
            elif not status & WORKER:
                build = '本轮未读到受支持的建造工人'
            elif not status & BUILDER:
                build = '本轮没有可调度的建造工人'
            elif not status & BUILD_INTENT:
                build = '等待已派工的建筑' if blocked_builds else '本轮暂无需要建造的建筑'
            elif not status & RESOURCES:
                build = '金币或木材不足'
            elif not status & HALL:
                build = '工人附近没有自己的标准主基地'
            elif not status & SITE:
                build = '本轮未找到可用的建造位置'
            else:
                build = '游戏未接受本轮建造指令'
        return harvest, build

    def fc_settings(self):
        state=self.view.value('state')
        if 'fullclone_options' not in state:
            from war3_fullclone_supplies import load
            state['fullclone_options']=dict(DEFAULTS,**load())
        return state['fullclone_options']

    def fc_action(self,action):
        if action in ('local_ai_start', 'local_ai_stop'):
            return self.fc_local_ai(action == 'local_ai_start')
        t=self.elephant_trainer();o=self.fc_settings()
        if action in ('hero_candidate_1', 'hero_candidate_2', 'hero_candidates_clear'):
            from war3_services.hero_skill_swap import capture_candidate, clear_candidates
            if action == 'hero_candidates_clear':
                clear_candidates(t)
                return '已清空候选英雄'
            capture_candidate(t, int(action[-1]) - 1)
            return '已加入候选英雄'
        use_candidates = action.startswith('swap_candidate_hero_skill_')
        skill_action = action.replace('swap_candidate_hero_skill_', 'swap_hero_skill_', 1) if use_candidates else action
        if skill_action in ('swap_hero_skill_1','swap_hero_skill_2','swap_hero_skill_3','swap_hero_skill_4','swap_hero_skill_all'):
            from war3_services.hero_skill_swap import exchange_hero_skills
            slot=None if skill_action=='swap_hero_skill_all' else int(skill_action[-1])-1
            changed=exchange_hero_skills(t,slot,candidates_only=True) if use_candidates else exchange_hero_skills(t,slot)
            return f'已交换双方共 {changed} 个英雄技能槽' if changed else '双方对应的英雄技能和等级相同'
        if action=='restore_hero_skills':
            from war3_services.hero_skill_swap import restore_hero_skills
            r=restore_hero_skills(t)
            if not r['restored'] and not r['pending']:
                return '当前地图没有可还原的英雄技能'
            result=f'已还原 {r["restored"]} 名英雄；还有 {r["pending"]} 名待还原'
            return result+('。'+'；'.join(r['issues']) if r['issues'] else '')
        if action=='freeze_owner':
            from war3_fullclone_extras import toggle_frozen
            r=toggle_frozen(t,o['freeze_scope'],o['freeze_buildings'])
            return f'已{"恢复" if r["restored"] else "冻结"}{r["changed"]}个单位；跳过变化或失效身份{r["skipped"]}个'
        elif action=='restore_all_frozen':
            from war3_fullclone_extras import restore_all_frozen
            r=restore_all_frozen(t);return f'已恢复{r["changed"]}个单位；跳过变化或失效身份{r["skipped"]}个'
        elif action=='supply_deliver':
            from war3_fullclone_supplies import deliver
            r=deliver(t,o['supply_text_'+o['supply_slot']],o['supply_target'])
            return f'已投放补给物品{r["changed"]}个'
        elif action=='point_spell':
            from war3_fullclone_extras import point_spell
            return point_spell(t,o['point_spell'])
        elif action=='give_owner':
            r=t.fullclone_give_owner(o['target_player'])
            if not r['selected']:return '请先在游戏里选中单位'
            return f'已转交 {r["changed"]} 个单位；跳过或未确认 {r["skipped"]} 个'
        elif action in ('restore_selected_owners','restore_all_owners'):
            all_units=action=='restore_all_owners'
            r=t.fullclone_restore_owners(all_units=all_units)
            if not r['changed'] and not r['skipped']:
                return '本次地图没有可恢复的单位归属记录' if all_units else '选中单位没有可恢复的原玩家记录'
            return f'已确认 {r["changed"]} 个单位归还原玩家；跳过或未确认 {r["skipped"]} 个'
        elif action=='toggle_owner_control':
            r=t.fullclone_toggle_control()
            if r.get('local'):return '该玩家是自己，已由你控制'
            if not r['changed']:return '请先在游戏里选中单位'
            return '已恢复选中玩家的控制状态' if r['restored'] else '已控制选中玩家（阵营不变）'
        elif action=='join_team':r=t.fullclone_team(o['team'])
        elif action=='restore_team':r=t.fullclone_team(restore=True)
        elif action=='restore_all_teams':
            return restore_team_records(t)['message']
        elif action=='replace_unit':r=t.fullclone_action(12,rawcode=self.fc_rawcode(o['replace_id']))
        elif action=='fill_life_mana':r=t.fullclone_action(2)
        elif action=='fill_owner_life_mana':
            mode={'all':0,'heroes':1,'nonheroes':2}.get(o['army_scope'])
            if mode is None:raise ValueError('全军补满范围无效')
            r=t.fullclone_fill_owner(mode)
            if r['player']<0:return '请先在游戏里选中目标玩家的一个单位'
            label={24:'中立敌对（玩家25）',27:'中立被动（玩家28）'}.get(r['player'],f'玩家 {r["player"]+1}')
            if not r['eligible']:return f'{label}没有符合范围的存活、未隐藏单位'
            if not r['changed']:return f'{label}符合范围的 {r["eligible"]} 个单位生命魔法已经全满'
            return f'已为{label}补满 {r["changed"]} 个单位的生命魔法（符合范围共 {r["eligible"]} 个）'
        elif action=='revive_owner_heroes':
            x,y=t.query_mouse_world_position();r=t.fullclone_action(5,x=x,y=y)
        elif action=='unit_color':r=t.fullclone_action(3,value=o['color'])
        elif action=='player_color':r=t.fullclone_action(4,value=o['color'])
        elif action=='gold_mine':
            r=t.gold_mines('selected',o['mine_amount'])
            return '已设置选中金矿黄金' if r.get('changed') else ''
        elif action=='infernal':
            return self.fc_infernal()
        elif action=='gather_ground_items':
            mode=o['item_filter_mode']
            r=t.fullclone_gather_items() if mode=='all' else t.fullclone_gather_items(filter_mode=mode,filter_ids=o['item_filter_ids'])
            suffix={'include':'（仅指定物品ID）','exclude':'（已排除指定物品ID）'}.get(mode,'')
            return f'已聚集 {r["changed"]} 个地面物品'+suffix
        elif action=='clone':return self.fc_clone()
        elif action=='mass_clone':return self.elephant_mass_clone()
        else:raise ValueError('未知扩展功能')
        return f'已处理 {r.get("changed",0)} 个目标'

    @staticmethod
    def fc_rawcode(text):
        import re
        if not isinstance(text,str) or not re.fullmatch(r'[!-~]{4}',text):raise ValueError('单位ID请输入区分大小写的四个字符')
        return int.from_bytes(text.encode('ascii'),'big')

    def fc_owner_options(self):
        o=self.fc_settings()
        return dict(owner_mode=o['owner_mode'] if o['owner_enabled'] else 'author',player=o['owner_player'])

    def fc_clone(self,count=1,to_self=False):
        options=self.fc_owner_options()
        if to_self:options['owner_mode']='self'
        r=self.elephant_trainer().fullclone_clone(count,**options)
        warning=f'；有 {len(r["ability_issues"])} 项技能未完整复制' if r['ability_issues'] else ''
        return f'已复制 {r["count"]} 个单位'+warning

    def elephant_create_unit(self,copy_selected,preserve_owner=False):
        if copy_selected:
            return self.fc_clone(to_self=not preserve_owner)
        if self.fc_settings()['owner_enabled']:
            return self.fc_spawn(self.view.value('elephant_unit_rawcode').get())
        return super().elephant_create_unit(copy_selected,preserve_owner)

    def elephant_mass_clone(self):
        o=self.fc_settings()
        if o['formation']!='original':
            from war3_fullclone_extras import clone_formation
            r=clone_formation(self.elephant_trainer(),int(self.view.value('elephant_mass_clone_count').get()),o['formation'],o['formation_gap'],**self.fc_owner_options())
            return f'已按阵型复制{r["count"]}个单位；技能未完整复制{len(r["ability_issues"])}项'
        return self.fc_clone(int(self.view.value('elephant_mass_clone_count').get()))

    def fc_spawn(self,code):
        t=self.elephant_trainer();o=self.fc_settings();mode=o['owner_mode']
        owner=-1 if mode=='self' else o['owner_player']
        if mode=='selected':
            r=t.fullclone_owner()
            if r is None:raise ValueError('请先选择一个目标玩家的单位')
            owner=r['a']
        x,y=t.query_mouse_world_position()
        t.fullclone_action(11,value=owner,rawcode=self.fc_rawcode(code.strip()),x=x,y=y)
        return '已为所选归属创建单位'

    def elephant_create_reinforcement(self):
        if self.fc_settings()['owner_enabled']:
            return self.fc_spawn(self.view.value('elephant_reinforcement_rawcode').get())
        return super().elephant_create_reinforcement()

    def fc_hero_level(self):
        if self.fc_settings()['hero_custom']:return super().elephant_set_hero_level()
        r=self.elephant_trainer().fullclone_action(6)
        return f'已将 {r["changed"]} 个英雄的等级增加1级' if r['changed'] else ''

    def fc_attributes(self):
        if self.fc_settings()['attributes_custom']:return super().elephant_set_hero_attributes()
        r=self.elephant_trainer().fullclone_action(7,value=-1)
        return f'已将 {r["changed"]} 个英雄的力量、敏捷、智力增加2点' if r['changed'] else ''

    def fc_pathing(self):
        t=self.elephant_trainer();engine=t._engine_instance_24268()
        with engine.session.lock:
            owner=t.fullclone_action(0)
            cache=engine.session.cache.setdefault('fullclone_pathing',{})
            rows=owner['rows'];disabled=bool(rows) and all(r['handle'] in cache for r in rows)
            result=engine.fullclone(14,value=int(disabled))
            for row in rows:
                if disabled:cache.pop(row['handle'],None)
                else:cache[row['handle']]=True
            return '已开启选中单位碰撞' if disabled else '已关闭选中单位碰撞'

    def fc_infernal(self):
        return self.elephant_trainer().fullclone_infernal()

    def hotkey_actions(self):
        result=super().hotkey_actions()
        from war3_fullclone_hotkeys import specs
        for s in specs(())[0:]:result[s.name]=lambda action=s.name:self.fc_action(action)
        result.update(hero_level=self.fc_hero_level,hero_attributes=self.fc_attributes,
            ignore_collision=self.fc_pathing,
            clone_unit=lambda:self.fc_clone(),clone_to_self=lambda:self.fc_clone(to_self=True))
        return result
