"""R31 UI commands. Settings are separate from all original reader parameters."""
DEFAULTS=dict(owner_enabled=False,owner_mode='self',owner_player=0,target_player=1,
    team=0,replace_id='zhyd',color=0,hero_custom=False,attributes_custom=False,
    mine_amount='100000',army_scope='all',item_filter_mode='all',item_filter_ids='',
    formation='original',formation_gap='128',freeze_scope='all',freeze_buildings=False,
    supply_slot='1',supply_target='hero',supply_name_1='恢复用品',supply_name_2='回城用品',supply_name_3='测试装备',
    supply_text_1='',supply_text_2='',supply_text_3='',point_spell='AUin')


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
    def fc_settings(self):
        state=self.view.value('state')
        if 'fullclone_options' not in state:
            from war3_fullclone_supplies import load
            state['fullclone_options']=dict(DEFAULTS,**load())
        return state['fullclone_options']

    def fc_action(self,action):
        t=self.elephant_trainer();o=self.fc_settings()
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
            r=t.fullclone_toggle_control();return '已恢复选中玩家的控制状态' if r['restored'] else '已控制选中玩家（阵营不变）'
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
