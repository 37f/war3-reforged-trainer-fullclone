"""R31 UI commands. Settings are separate from all original reader parameters."""
DEFAULTS=dict(owner_enabled=False,owner_mode='self',owner_player=0,target_player=1,
    team=0,replace_id='zhyd',color=0,hero_custom=False,attributes_custom=False,
    mine_amount='100000')


class FullCloneApplication:
    def fc_settings(self):
        state=self.view.value('state')
        return state.setdefault('fullclone_options',dict(DEFAULTS))

    def fc_action(self,action):
        t=self.elephant_trainer();o=self.fc_settings()
        if action=='give_owner':r=t.fullclone_action(1,value=o['target_player'])
        elif action=='toggle_owner_control':
            r=t.fullclone_toggle_control();return '已恢复选中玩家的控制状态' if r['restored'] else '已控制选中玩家（阵营不变）'
        elif action=='join_team':r=t.fullclone_team(o['team'])
        elif action=='restore_team':r=t.fullclone_team(restore=True)
        elif action=='restore_all_teams':
            r=t.fullclone_restore_all_teams()
            return f'已恢复 {r["changed"]} 个玩家真正原队伍（共享控制权限保持不变）' if r['total'] else '本次地图没有可恢复的原队伍记录'
        elif action=='replace_unit':r=t.fullclone_action(12,rawcode=self.fc_rawcode(o['replace_id']))
        elif action=='fill_life_mana':r=t.fullclone_action(2)
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
            r=t.fullclone_gather_items();return f'已聚集 {r["changed"]} 个地面物品'
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
