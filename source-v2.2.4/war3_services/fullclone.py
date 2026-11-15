"""R31 FullClone service, using the author's 3.0 session/transport unchanged."""
import struct

from war3_selection_protocol import SIGNATURES as SELECTION
from war3_fullclone_protocol import ACTIONS, SIGNATURES, build_work, decode_work


class FullCloneService:
    def fullclone_clone_state(self,expected_sources,player,*,spawn_x_bits,spawn_y_bits):
        from war3_fullclone_clone_protocol import SIGNATURES as OWNER,build_work as build,decode_work as decode
        from war3_clone_state_protocol import SIGNATURES as STATE
        from war3_clone_protocol import SIGNATURES as CLONE,CLONE_KEEP,CLONE_COPY_ABILITIES,CLONE_COPY_ITEMS,CLONE_USE_SPAWN,CLONE_ALLOW_PARTIAL_ABILITIES
        names=tuple(dict.fromkeys(n for n,_ in SELECTION+CLONE+STATE+OWNER))
        def builder(entries,tls):
            with self.memory_factory(self.pid) as memory:
                registry,_,_=self.session.prepare(memory)
                for _,ref in expected_sources:self.session.resolve(memory,registry,ref)
                return build(entries,tls,player=player,base=registry.base,
                    unit_resolver=registry.base+self.session.profile.section('addresses')['unit_resolver'],
                    image_size=self.session.profile.section('fingerprint')['image_size'],
                    expected_sources=expected_sources,layout=self.session.profile.adapter.talents.clone_layout(),
                    flags=CLONE_KEEP|CLONE_COPY_ABILITIES|CLONE_COPY_ITEMS|CLONE_USE_SPAWN|CLONE_ALLOW_PARTIAL_ABILITIES,
                    spawn_x_bits=spawn_x_bits,spawn_y_bits=spawn_y_bits)
        return self._execute('fullclone_clone',names,builder,
            lambda payload,count:decode(payload,count,expected_sources=expected_sources),dict(player=player))

    def fullclone(self,action,**options):
        expected_epoch=options.pop('expected_epoch',None)
        names=tuple(dict.fromkeys([n for n,_ in SELECTION]+list(ACTIONS[action])))
        with self.session.lock:
            def builder(entries,tls):
                if expected_epoch is not None and self.session.epoch!=expected_epoch:raise ValueError('地图会话已变化，未执行扩展操作')
                if action in (16,17,18):
                    with self.memory_factory(self.pid) as memory:
                        registry,_,_=self.session.prepare(memory)
                        options['resolver']=registry.base+self.session.profile.section('addresses')['unit_resolver']
                return build_work(entries,tls,action,**options)
            return self._execute('fullclone',names,
                builder,decode_work,
                dict(action=action,**options))


def team_matrix(snapshot,target):
    """Diplomacy only, matching R30; native team indexes are not guessed."""
    owner=snapshot['rows'][0]['a'];original=snapshot['matrix'];teams=snapshot['teams']
    if target not in range(14):raise ValueError('请选择队伍1至12或两个中立模板')
    if target<12:
        members=[p for p,t in enumerate(teams[:24]) if t==target and p!=owner]
        reference=members[0] if members else -1
    else:reference=24 if target==12 else 27
    return reference


# ALLIANCE_SHARED_CONTROL and ALLIANCE_SHARED_ADVANCED_CONTROL. A team template
# is diplomacy only; control stays with the explicit toggle (action 10).
CONTROL_FLAGS=(6,7)


def keep_control(before,desired,owner_id):
    """Keep the live shared-control bits while a team template changes diplomacy.

    Copying the reference player's row copied flags 6/7 too, so joining a team
    silently gave the new allies control of the player's units (and the player
    control of theirs). The template now only writes the other flags; both the
    join and the restore path leave control exactly as it was before the call.
    """
    matrix=list(desired)
    for p in range(28):
        if p==owner_id:continue
        for a in CONTROL_FLAGS:
            matrix[p*20+a]=before['matrix'][p*20+a]
            matrix[p*20+10+a]=before['matrix'][p*20+10+a]
    return tuple(matrix)


def neutral_template_matrix(snapshot,saved,reference):
    """Undo this trainer's writes in the reference row, newest first.

    A moved neutral cannot be its own pristine template. Its first snapshot
    can also contain earlier moves by other players; rewind those bilateral
    pairs too. This uses current-map evidence, not hard-coded friendly flags.
    """
    if not snapshot['rows'] or snapshot['rows'][0]['a']!=reference:raise ValueError('中立模板参考玩家身份未确认')
    matrix=list(snapshot['matrix'])
    if len(matrix)!=560:raise ValueError('中立模板关系不完整')
    for record in reversed(tuple(saved.values())):
        player=record.get('player');original=record.get('matrix',())
        if type(player) is not int or not 0<=player<28 or len(original)!=560 or any(v not in (0,1) for v in original):
            raise ValueError('原队伍记录不完整，未套用中立模板')
        if player==reference:matrix=list(original)
        else:
            # The other player's snapshot stores the same pair in reverse.
            for flag in range(10):
                matrix[player*20+flag]=original[reference*20+10+flag]
                matrix[player*20+10+flag]=original[reference*20+flag]
    return tuple(matrix)



NATIVE_TEAMS_SNAPSHOT='native_teams_snapshot'


def diplomacy_template_label(value):
    """Same wording as the elephant owner-status line."""
    if value is None:return '未套用外交模板'
    if type(value) is not int:return '未确认'
    if 0<=value<12:return f'队伍 {value+1}'
    if value==12:return '中立敌对'
    if value==13:return '中立被动'
    return '未确认'


def applied_diplomacy_templates(cache,addresses=()):
    """Map player slot -> join-team template. Keys in the cache are owner handles."""
    applied={}
    saved=(cache or {}).get('fullclone_teams') or {}
    addr=list(addresses or ())
    for key,rec in saved.items():
        if type(rec) is not dict:continue
        target=rec.get('applied')
        if type(target) is not int or not 0<=target<=13:continue
        player=rec.get('player')
        if type(player) is not int or not 0<=player<28:
            try:player=addr.index(key)
            except ValueError:continue
        applied[player]=target
    return applied


def remember_native_teams(cache,teams):
    """Keep the first verified GetPlayerTeam list for this map session.

    Join-team writes diplomacy only, but a later getter can still report a
    different index for the selected player. The directory groups by this
    snapshot so the player stays in the original native-team list.
    """
    if teams is None:return
    values=tuple(teams)
    if len(values)!=28:return
    if any(type(v) is not int or not -1<=v<28 for v in values):return
    cache.setdefault(NATIVE_TEAMS_SNAPSHOT,values)


def pinned_native_teams(cache,teams=None):
    remember_native_teams(cache,teams)
    return cache.get(NATIVE_TEAMS_SNAPSHOT)


class FullCloneFacade:
    def fullclone_infernal(self):
        import threading,time
        engine=self._engine_instance_24268()
        with engine.session.lock:
            x,y=self.query_mouse_world_position()
            state=engine.fullclone(16,x=x,y=y)
            row=state['rows'][0];epoch=engine.session.epoch
        # Allow creation/ability registration to finish between game callbacks.
        time.sleep(.15)
        def release():
            with engine.session.lock:
                if engine.session.closed or engine.session.epoch!=epoch:return
                engine.fullclone(18,target=row['handle'],expected_owner=row['created'])
        try:
            with engine.session.lock:
                if engine.session.epoch!=epoch:raise ValueError('施法期间地图已变化')
                engine.fullclone(17,x=x,y=y,target=row['handle'],expected_owner=row['created'])
        except Exception:
            release();raise
        def cleanup():
            time.sleep(4)
            try:release()
            except Exception as exc:engine.session.cache['fullclone_infernal_cleanup_error']=str(exc)
        threading.Thread(target=cleanup,daemon=True,name='fullclone-infernal-cleanup').start()
        return '已在鼠标位置施放地狱火（AUin，归自己）'

    def fullclone_player_name(self,index):
        from war3_fullclone_runtime import player_name
        return player_name(self,index)

    def fullclone_gather_items(self,preview=False):
        from war3_fullclone_runtime import gather
        return gather(self,preview)

    def fullclone_action(self,action,**options):
        return self._engine_instance_24268().fullclone(action,**options)

    def fullclone_owner(self):
        result=self.fullclone_action(0)
        if not result['rows']:return None
        return result['rows'][0]

    def fullclone_toggle_control(self):
        engine=self._engine_instance_24268()
        with engine.session.lock:
            before=engine.fullclone(10,value=-1)
            if not before['rows']:return dict(changed=0,restored=False)
            row=before['rows'][0];owner=row['owner']
            saved=engine.session.cache.setdefault('fullclone_control',{})
            if owner in saved:
                value=saved[owner];restored=True
            else:
                value=3;restored=False
                # Record before either setter: a partial native failure must
                # still leave the exact original control bits recoverable.
                saved[owner]=row['b']|(row['c']<<1)
            result=engine.fullclone(10,value=value,expected_owner=owner)
            if restored:saved.pop(owner,None)
            elif not result['changed']:saved.pop(owner,None)
            return dict(result,restored=restored)

    def fullclone_team(self,target=None,restore=False,*,player=None,expected_epoch=None):
        engine=self._engine_instance_24268()
        with engine.session.lock:
            direct=player is not None
            if direct and (type(player) is not int or player not in (*range(24),24,27)):raise ValueError('不支持修改该玩家的外交模板')
            if expected_epoch is not None and engine.session.epoch!=expected_epoch:raise ValueError('地图已变化，未修改外交模板')
            before=engine.fullclone(19,target=player,expected_epoch=expected_epoch) if direct else engine.fullclone(8)
            if not before['rows']:return dict(changed=0)
            row=before['rows'][0];owner=row['owner'];owner_id=row['a']
            # Pin the pre-write teams so a later directory read cannot regroup.
            remember_native_teams(engine.session.cache,before.get('teams'))
            saved=engine.session.cache.setdefault('fullclone_teams',{})
            if restore:
                if owner not in saved:raise ValueError('当前地图尚未记录该玩家的原队伍')
                desired=saved[owner]['matrix']
            else:
                reference=team_matrix(before,target)
                # Capture a template using the actual reference player. The query
                # stays bound to the selected owner until the final write.
                peers=(engine.fullclone(19,target=reference,expected_epoch=expected_epoch) if direct else self.fullclone_alliances(reference)) if reference>=0 else None
                if target in (12,13):
                    peers=dict(peers,matrix=neutral_template_matrix(peers,saved,reference))
                desired=list(before['matrix'])
                for p in range(28):
                    if p==owner_id:continue
                    if reference<0:
                        allied=p<24 and before['teams'][p]==target
                        for a in range(10):
                            v=int(allied) if a in (0,1,2,3,4,5) else 0
                            desired[p*20+a]=v;desired[p*20+10+a]=v
                    else:
                        for a in range(10):
                            desired[p*20+a]=peers['matrix'][p*20+a]
                            desired[p*20+10+a]=peers['matrix'][p*20+10+a]
                desired=tuple(desired)
            # Control is not part of the template: keep the live bits in both paths.
            desired=keep_control(before,desired,owner_id)
            # Save before the first write so a partial failure can still be restored.
            saved.setdefault(owner,dict(matrix=before['matrix'],team=row['team'],applied=None,player=owner_id));saved[owner]['player']=owner_id
            result=engine.fullclone(20,target=player,matrix=desired,expected_owner=owner,expected_epoch=expected_epoch) if direct else engine.fullclone(9,matrix=desired,expected_owner=owner)
            saved[owner]['applied']=None if restore else target
            return dict(result,restored=restore,target_team=target)

    def fullclone_restore_all_teams(self):
        """Replay first snapshots newest-first so the earliest pair wins last.

        A later player's first snapshot can already contain an earlier move.
        Include individually restored records too; never replace the originals.
        """
        engine=self._engine_instance_24268()
        with engine.session.lock:
            epoch=engine.session.epoch
            records=list(engine.session.cache.get('fullclone_teams',{}).items())
            if not records:return dict(changed=0,total=0)
            # Validate every identity/snapshot before the first alliance setter.
            for owner,record in records:
                player=record.get('player');matrix=record.get('matrix',())
                if type(player) is not int or player not in (*range(24),24,27):raise ValueError('原队伍记录的玩家无效，未执行批量恢复')
                if len(matrix)!=560 or any(v not in (0,1) for v in matrix):raise ValueError('原队伍记录不完整，未执行批量恢复')
                before=engine.fullclone(19,target=player,expected_epoch=epoch)
                if not before['rows'] or before['rows'][0]['owner']!=owner:raise ValueError('玩家或地图已变化，未执行批量恢复')
            changed=0
            for owner,record in reversed(records):
                try:
                    result=self.fullclone_team(restore=True,player=record['player'],expected_epoch=epoch)
                    if not result.get('changed'):raise ValueError('未确认该玩家恢复成功')
                    changed+=1
                except Exception as exc:
                    raise ValueError(f'已恢复 {changed}/{len(records)} 个玩家，批量恢复已停止；原记录保留：{exc}') from exc
            return dict(changed=changed,total=len(records))

    def fullclone_alliances(self,player):
        # action 8's explicit player target is a query only; no unit selection change.
        return self._engine_instance_24268().fullclone(8,value=player,target=1)

    def fullclone_clone(self,count=1,*,owner_mode='author',player=0):
        if type(count) is not int or not 1<=count<=100:raise ValueError('复制数量必须为1至100')
        if owner_mode not in ('author','self','selected','player'):raise ValueError('复制归属无效')
        engine=self._engine_instance_24268()
        with engine.session.lock:
            # Let the author's current transaction capture full identity, levels,
            # abilities, items, expanded bag, equipment and talents.
            sources=self._capture_clone_sources_24268()
            owner=self.fullclone_owner()
            if not owner:raise ValueError('请先选择单位')
            destination=owner['a'] if owner_mode=='selected' else player
            position=self.query_mouse_world_position()
            created=[];issues=[]
            for _ in range(count):
                if owner_mode=='player':
                    result=engine.fullclone_clone_state(sources,destination,
                        spawn_x_bits=self._float_bits(position[0]),spawn_y_bits=self._float_bits(position[1]))
                else:
                    result=self.clone_batch_24268(keep=True,preserve_owner=owner_mode in ('author','selected'),
                        copy_abilities=True,copy_items=True,spawn=True,
                        spawn_x_bits=self._float_bits(position[0]),spawn_y_bits=self._float_bits(position[1]),expected_sources=sources)
                handles=tuple(int(r['clone']) for r in result['rows'])
                created.extend(handles);issues.extend(result.get('ability_issues',()))
            return dict(count=len(created),handles=created,ability_issues=issues)
