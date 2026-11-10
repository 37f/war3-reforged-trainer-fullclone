"""R31 acceptance contracts, including executable C, without touching the game."""
from pathlib import Path
from types import SimpleNamespace
import ctypes as c
import json
import os
import struct
import subprocess
import shutil
import threading

import pytest
import war3_fullclone_protocol as fc
from war3_selection_protocol import SIGNATURES as SELECTION
from war3_services.fullclone import FullCloneFacade


@pytest.fixture(scope='session')
def dll(tmp_path_factory):
    compiler=Path(os.environ.get('FULLCLONE_CLANG') or shutil.which('clang') or '')
    if not compiler.is_file():pytest.skip('Set FULLCLONE_CLANG to a Windows x64 clang compiler')
    root=Path(__file__).resolve().parents[1];output=tmp_path_factory.mktemp('fc-native')/'fixture.dll'
    r=subprocess.run([str(compiler),'-shared','-O1','-fms-extensions','-fseh-exceptions',
        '-fno-stack-protector','-fno-builtin','-nostdlib','-D__C_specific_handler=BridgeSpecificHandler',
        str(root/'tests/fullclone_fixture.c'),'-o',str(output),'-Wl,--entry,DllMain','-lkernel32','-luser32'],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    image=c.WinDLL(str(output));image.FCFixtureRun.argtypes=[c.c_void_p,c.c_uint32];image.FCFixtureRun.restype=c.c_uint64
    return image


U=c.c_uint64;I=c.c_int32;B=c.c_uint8;V=None;F=c.POINTER(c.c_float)


class World:
    def __init__(self):
        self.units={1001:dict(owner=1,rawcode=0x4870616c,level=5,strength=10,agility=11,intelligence=12,xp=True,hp=12.,maxhp=500.,mp=0.,maxmp=200.),
            1002:dict(owner=2,rawcode=0x68666f6f,level=0,hp=20.,maxhp=420.,mp=0.,maxmp=0.),
            1003:dict(owner=2,rawcode=0x4f626c61,level=9,strength=20,agility=21,intelligence=22,xp=False,hp=500.,maxhp=500.,mp=100.,maxmp=300.)}
        self.selected=[1001,1002,1003];self.group=[];self.calls=[];self.alliances={};self.callbacks=[]
        self.entries={}
        def bind(name,result,args,fn):
            cb=c.CFUNCTYPE(result,*args)(fn);self.callbacks.append(cb)
            sig=dict(SELECTION+fc.SIGNATURES)[name]
            self.entries[name]=SimpleNamespace(name=name,signature=sig,handler=c.cast(cb,c.c_void_p).value)
        self.bind=bind
        bind('GetLocalPlayer',U,(),lambda:1)
        bind('CreateGroup',U,(),lambda:123)
        bind('GroupEnumUnitsSelected',V,(U,U,U),lambda *a:self.group.extend(self.selected))
        bind('FirstOfGroup',U,(U,),lambda g:self.group[0] if self.group else 0)
        bind('GroupRemoveUnit',B,(U,U),lambda g,u:(self.group.remove(u),1)[1])
        bind('DestroyGroup',V,(U,),lambda g:self.calls.append(('destroy',g)))
        bind('GetUnitTypeId',c.c_uint32,(U,),lambda u:self.units.get(u,{}).get('rawcode',0))
        bind('GetHeroLevel',I,(U,),lambda u:self.units[u]['level'])
        bind('GetOwningPlayer',U,(U,),lambda u:self.units[u]['owner'])
        bind('GetPlayerId',I,(U,),lambda p:p-1)
        bind('Player',U,(I,),lambda p:p+1)
        bind('GetPlayerTeam',I,(U,),lambda p:(p-1)//2 if p<25 else -1)
        bind('GetPlayerSlotState',U,(U,),lambda p:1 if p<=24 else 0)
        bind('ConvertPlayerSlotState',U,(I,),lambda i:i)
        bind('SetUnitOwner',V,(U,U,I),lambda u,p,b:self.units[u].update(owner=p))
        bind('ConvertUnitState',U,(I,),lambda i:i)
        def get(u,k):return struct.unpack('<I',struct.pack('<f',self.units[u][('hp','maxhp','mp','maxmp')[k]]))[0]
        bind('GetUnitState',c.c_uint32,(U,U),get)
        bind('SetUnitState',V,(U,U,F),lambda u,k,p:self.units[u].update({('hp','maxhp','mp','maxmp')[k]:p[0]}))
        bind('SetHeroLevel',V,(U,I,I),lambda u,n,b:self.units[u].update(level=n))
        bind('SuspendHeroXP',V,(U,I),lambda u,b:self.units[u].update(xp=bool(b)))
        bind('IsSuspendedXP',B,(U,),lambda u:self.units[u].get('xp',False))
        bind('UnitStripHeroLevel',B,(U,I),lambda u,n:1)
        for attr,key in [('Str','strength'),('Agi','agility'),('Int','intelligence')]:
            bind('GetHero'+attr,I,(U,I),lambda u,b,key=key:self.units[u][key])
            bind('SetHero'+attr,V,(U,I,I),lambda u,n,b,key=key:self.units[u].update({key:n}))
        bind('ConvertAllianceType',U,(I,),lambda i:i)
        bind('GetPlayerAlliance',B,(U,U,U),lambda a,b,k:self.alliances.get((a,b,k),0))
        bind('SetPlayerAlliance',V,(U,U,U,I),lambda a,b,k,v:self.alliances.__setitem__((a,b,k),v))
        bind('SetUnitPathing',V,(U,I),lambda u,b:self.calls.append(('pathing',u,b)))
    def run(self,dll,action,**options):
        p=fc.build_work(self.entries,0x20000,action,**options);buf=c.create_string_buffer(p,len(p))
        count=dll.FCFixtureRun(buf,1)
        return fc.decode_work(buf.raw,count)


def test_native_increment_preserves_different_levels_and_xp_state(dll):
    w=World();r=w.run(dll,6)
    assert r['changed']==2
    assert [w.units[u]['level'] for u in w.selected]==[6,0,10]
    assert w.units[1001]['xp'] is True and w.units[1003]['xp'] is False


@pytest.mark.parametrize('applied',[False,True])
def test_hero_native_fault_requires_actual_target_and_restores_xp(dll,applied):
    w=World();w.selected=[1001];level=c.c_int32(5)
    getter=c.CFUNCTYPE(I,U)(lambda u:level.value);w.callbacks.append(getter)
    w.entries['GetHeroLevel'].handler=c.cast(getter,c.c_void_p).value
    w.entries['SetHeroLevel'].handler=c.cast(dll.FCFixtureFaultLevel,c.c_void_p).value
    dll.FCFixtureFaultLevelConfig.argtypes=[c.POINTER(I),c.c_uint32]
    dll.FCFixtureFaultLevelConfig(c.byref(level),int(applied))
    import faulthandler
    enabled=faulthandler.is_enabled();faulthandler.disable()
    try:
        if applied:assert w.run(dll,6)['changed']==1
        else:
            with pytest.raises(RuntimeError):w.run(dll,6)
    finally:
        if enabled:faulthandler.enable()
    assert w.units[1001]['xp'] is True


def test_native_attributes_add_permanent_two_and_skip_nonhero(dll):
    w=World();r=w.run(dll,7,value=-1)
    assert r['changed']==2
    assert [w.units[1001][k] for k in ('strength','agility','intelligence')]==[12,13,14]
    assert [w.units[1003][k] for k in ('strength','agility','intelligence')]==[22,23,24]


def test_native_fill_life_and_mana_zero_mana_is_not_error(dll):
    w=World();r=w.run(dll,2)
    assert r['changed']==3
    for u in w.units.values():assert u['hp']==u['maxhp'] and u['mp']==u['maxmp']


@pytest.mark.parametrize('player',[0,12,23,24,27])
def test_native_owner_choices_include_both_neutral_slots(dll,player):
    w=World();r=w.run(dll,1,value=player)
    assert r['changed']==3
    assert {u['owner'] for u in w.units.values()}=={player+1}


def test_native_team_snapshot_captures_all_both_way_flags(dll):
    w=World();w.alliances[(1,25,6)]=1
    r=w.run(dll,8)
    assert len(r['matrix'])==560 and r['matrix'][24*20+6]==1
    desired=list(r['matrix']);desired[27*20+10]=1
    changed=w.run(dll,9,matrix=desired,expected_owner=1)
    assert changed['changed']==1 and w.alliances[(28,1,0)]==1


def test_native_control_only_changes_shared_control_flags(dll):
    w=World();w.selected=[1002]
    before=w.run(dll,10,value=-1);assert before['changed']==0
    after=w.run(dll,10,value=3,expected_owner=2)
    assert after['changed']==1 and w.units[1002]['owner']==2
    assert set(w.alliances)=={(2,1,6),(2,1,7)}
    w.run(dll,10,value=0,expected_owner=2)
    assert not any(w.alliances.values())


@pytest.mark.parametrize('player',[0,1,23,24,27])
def test_explicit_player_diplomacy_without_selection_keeps_control_and_units(dll,player):
    w=World();w.selected=[];calls=[]
    w.alliances[(player+1,1,6)]=1;w.alliances[(1,player+1,7)]=1
    units={k:dict(v) for k,v in w.units.items()}
    def setter(a,b,k,v):calls.append((a,b,k,v));w.alliances[(a,b,k)]=v
    w.bind('SetPlayerAlliance',V,(U,U,U,I),setter)
    before=w.run(dll,19,target=player)
    assert before['rows'][0]['a']==player and before['rows'][0]['b']==0 and before['rows'][0]['handle']==0
    desired=list(before['matrix']);peer=2 if player==0 else 0;desired[peer*20]=1;desired[peer*20+10]=1
    after=w.run(dll,20,target=player,matrix=desired,expected_owner=player+1)
    assert after['changed']==1 and after['matrix']==tuple(desired)
    assert calls and all(k not in (6,7) for a,b,k,v in calls)
    assert w.units==units and w.selected==[] and before['teams']==after['teams']


def test_explicit_player_write_rejects_control_change_or_stale_owner_before_setter(dll):
    w=World();w.selected=[];calls=[]
    w.bind('SetPlayerAlliance',V,(U,U,U,I),lambda *args:calls.append(args))
    before=w.run(dll,19,target=1);desired=list(before['matrix']);desired[6]=1
    with pytest.raises(RuntimeError):w.run(dll,20,target=1,matrix=desired,expected_owner=2)
    with pytest.raises(RuntimeError):w.run(dll,20,target=1,matrix=before['matrix'],expected_owner=3)
    assert calls==[]


def test_drag_facade_apply_and_restore_share_first_snapshot_without_selection(dll):
    w=World();w.selected=[];cache={};actions=[]
    class Engine:
        session=SimpleNamespace(lock=threading.RLock(),cache=cache,epoch=3)
        def fullclone(self,action,**options):
            epoch=options.pop('expected_epoch',None)
            assert epoch in (None,3)
            actions.append(action);return w.run(dll,action,**options)
    engine=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return engine
    h=Host();original=w.run(dll,19,target=0)['matrix']
    assert h.fullclone_team(1,player=0,expected_epoch=3)['changed']==1
    assert cache['fullclone_teams'][1]['matrix']==original and cache['fullclone_teams'][1]['player']==0
    assert cache['fullclone_teams'][1]['applied']==1
    w.alliances[(1,2,6)]=1  # Explicit control change after the team operation.
    h.fullclone_team(2,player=0);h.fullclone_team(restore=True,player=0)
    restored=w.run(dll,19,target=0)['matrix']
    for k,value in enumerate(original):
        if k%20 not in (6,7,16,17):assert restored[k]==value
    assert w.alliances[(1,2,6)]==1 and cache['fullclone_teams'][1]['applied'] is None
    assert set(actions)=={19,20} and w.selected==[]


@pytest.mark.parametrize('applied,fault',[(True,0xc0000005),(False,0xc0000005),(True,0xe0310002)])
def test_alliance_fault_requires_known_fault_and_independent_requested_readback(dll,applied,fault):
    w=World();w.selected=[1001];cell=c.c_uint32(0)
    w.bind('GetPlayerAlliance',B,(U,U,U),lambda a,b,k:cell.value if (a,b,k)==(1,2,0) else 0)
    w.entries['SetPlayerAlliance'].handler=c.cast(dll.FCFixtureFaultAlliance,c.c_void_p).value
    dll.FCFixtureFaultAllianceConfig.argtypes=[c.POINTER(c.c_uint32),c.c_uint32,c.c_uint32]
    dll.FCFixtureFaultAllianceConfig(c.byref(cell),int(applied),fault)
    desired=[0]*560;desired[20]=1
    import faulthandler
    enabled=faulthandler.is_enabled();faulthandler.disable()
    try:
        if applied and fault==0xc0000005:
            r=w.run(dll,9,matrix=desired,expected_owner=1)
            assert r['changed']==1 and r['verified_faults']==1 and r['last_fault']==fault
        else:
            with pytest.raises(RuntimeError):w.run(dll,9,matrix=desired,expected_owner=1)
    finally:
        if enabled:faulthandler.enable()
    assert cell.value==int(applied)


def test_alliance_unchanged_flags_are_not_written(dll):
    w=World();calls=[]
    w.bind('SetPlayerAlliance',V,(U,U,U,I),lambda *args:calls.append(args))
    r=w.run(dll,9,matrix=[0]*560,expected_owner=1)
    assert r['changed']==1
    assert calls==[]


def test_alliance_later_write_invalidating_earlier_flag_is_not_success(dll):
    w=World();w.selected=[1001]
    def setter(a,b,k,v):
        w.alliances[(a,b,k)]=v
        if (a,b,k)==(1,2,1):w.alliances[(1,2,0)]=0
    w.bind('SetPlayerAlliance',V,(U,U,U,I),setter)
    desired=[0]*560;desired[20]=desired[21]=1
    with pytest.raises(RuntimeError):w.run(dll,9,matrix=desired,expected_owner=1)


def test_removed_victory_operation_is_rejected_before_dispatch():
    w=World()
    with pytest.raises(ValueError):fc.build_work(w.entries,0x20000,13)
    assert 'RemovePlayer' not in fc.INDEX and 'ConvertPlayerGameResult' not in fc.INDEX
    assert fc.INDEX['PanCameraToTimed']==36 and fc.INDEX['CreateBlightedGoldmine']==46


def test_native_bridge_rejects_retired_victory_operation(dll):
    w=World();payload=bytearray(fc.build_work(w.entries,0x20000,0))
    struct.pack_into('<I',payload,1000,13)
    buf=c.create_string_buffer(bytes(payload),len(payload));dll.FCFixtureRun(buf,1)
    with pytest.raises(RuntimeError):fc.decode_work(buf.raw)
    assert w.calls==[]


def test_no_selection_is_a_successful_empty_query(dll):
    w=World();w.selected=[]
    assert w.run(dll,0)['count']==0
    assert w.run(dll,7,value=-1)['changed']==0


def replacement_world(fail_item=0):
    w=World();w.selected=[1001];w.units[1001].update(mp=100.,items=[7001,7002],experience=345,gold=1600)
    bits=lambda value:struct.unpack('<I',struct.pack('<f',value))[0]
    for name,value in [('GetUnitX',10.),('GetUnitY',20.),('GetUnitFacing',45.)]:
        w.bind(name,c.c_uint32,(U,),lambda u,value=value:bits(value))
    def create(owner,code,x,y,f):
        w.calls.append(('create',owner,code,x[0],y[0],f[0]))
        w.units[2001]=dict(owner=owner,rawcode=code,level=int(code>>24<ord('a')),hp=1000.,maxhp=1000.,mp=400.,maxmp=400.,items=[],experience=0,gold=0)
        return 2001
    w.bind('CreateUnit',U,(U,c.c_uint32,F,F,F),create)
    def mine(owner,x,y,f):
        w.calls.append(('blighted',));return create(owner,0x75676f6c,x,y,f)
    w.bind('CreateBlightedGoldmine',U,(U,F,F,F),mine)
    w.bind('RemoveUnit',V,(U,),lambda u:(w.calls.append(('remove',u)),w.units.pop(u,None)))
    w.bind('ConvertUnitType',U,(I,),lambda i:i)
    w.bind('IsUnitType',B,(U,U),lambda u,t:w.units[u]['level']>0)
    w.bind('GetHeroXP',I,(U,),lambda u:w.units[u].get('experience',0))
    w.bind('SetHeroXP',V,(U,I,I),lambda u,n,b:w.units[u].update(experience=n))
    w.bind('GetResourceAmount',I,(U,),lambda u:w.units[u].get('gold',0))
    w.bind('SetResourceAmount',V,(U,I),lambda u,n:w.units[u].update(gold=n))
    w.bind('UnitItemInSlot',U,(U,I),lambda u,i:(w.units[u].get('items',[])+[0]*6)[i])
    def remove(u,item):
        inv=w.units[u].get('items',[])
        if item in inv:inv[inv.index(item)]=0
    def add(u,item):
        if u==2001 and item==fail_item:return 0
        inv=w.units[u].setdefault('items',[])
        if item in inv:return 1
        if 0 in inv:inv[inv.index(0)]=item
        else:inv.append(item)
        return 1
    w.bind('UnitRemoveItem',V,(U,U),remove)
    w.bind('UnitAddItem',B,(U,U),add)
    w.bind('IsUnitHidden',B,(U,),lambda u:w.units[u].get('hidden',False))
    w.bind('ShowUnit',V,(U,I),lambda u,b:w.units[u].update(hidden=not b))
    w.bind('KillUnit',V,(U,),lambda u:w.calls.append(('kill',u)))
    return w


def test_replacement_keeps_owner_position_life_ratios_gold_and_original_hero_items(dll):
    w=replacement_world();r=w.run(dll,12,rawcode=0x4f626c61)
    assert r['changed']==1 and 1001 not in w.units
    v=w.units[2001]
    assert (v['owner'],v['hp'],v['mp'],v['gold'],v['experience'])==(1,24.,200.,1600,345)
    assert v['items']==[7001,7002] and r['rows'][0]['b']==2
    assert ('create',1,0x4f626c61,10.,20.,45.) in w.calls


def test_replacement_failed_inventory_transfer_returns_items_and_keeps_old_unit(dll):
    w=replacement_world(fail_item=7002)
    with pytest.raises(RuntimeError):w.run(dll,12,rawcode=0x4f626c61)
    assert 1001 in w.units and 2001 not in w.units
    assert w.units[1001]['items']==[7001,7002] and w.units[1001]['hidden'] is False


@pytest.mark.parametrize('hidden',[False,True])
def test_replacement_uses_blighted_mine_constructor_and_previous_hidden_cleanup(dll,hidden):
    w=replacement_world();w.units[1001]['hidden']=hidden
    w.run(dll,12,rawcode=0x75676f6c)
    assert ('blighted',) in w.calls and w.units[2001]['gold']==1600
    assert (('kill',1001) in w.calls)==hidden


def test_campaign_source_and_recheck_use_named_path_and_pid(monkeypatch):
    import war3_fullclone_source as source
    import war3_fullclone_files as files
    from war3_fullclone_quests import ScriptSnapshot
    f=files.GameSourceFile('C:/Campaigns/current.w3x',(1,2),345,10,100)
    calls=[]
    def inspect(path,pid):
        calls.append((path,pid));assert path==f.path and pid==4321;return f
    meta=dict(map_path='current.w3x',epoch=3)
    monkeypatch.setattr(source,'metadata',lambda t:meta)
    monkeypatch.setattr(files,'enumerate_game_files',lambda pid:(f,))
    monkeypatch.setattr(files,'inspect_windows_source_file',inspect)
    monkeypatch.setattr(source,'_source',lambda path,chapter:(ScriptSnapshot(script=b'globals\nendglobals'),[]))
    trainer=SimpleNamespace(pid=4321,_engine_instance_24268=lambda:SimpleNamespace(pid=4321))
    _,proof=source.current_script(trainer)
    assert proof['trusted'] and source.check_source(trainer,proof)
    assert calls==[(f.path,4321),(f.path,4321)]


def test_option_validation_and_default_disabled_settings():
    from war3_fullclone_desktop import set_option
    from war3_fullclone_application import DEFAULTS
    state=dict(DEFAULTS);api=SimpleNamespace(app=SimpleNamespace(fc_settings=lambda:state))
    assert state['owner_enabled'] is False and state['replace_id']=='zhyd'
    for key,value in [('team',14),('target_player',25),('owner_enabled','yes'),('owner_mode','unknown')]:
        with pytest.raises(ValueError):set_option(api,key,value)


def test_first_team_snapshot_survives_many_switches_and_restore():
    original=tuple((i//3)%2 for i in range(560));current=list(original)
    row=dict(owner=2,a=1,team=-1);cache={};writes=[]
    class Engine:
        session=SimpleNamespace(lock=threading.RLock(),cache=cache)
        def fullclone(self,action,**options):
            if action==8:
                selected=dict(row)
                if options.get('target')==1:selected.update(a=options['value'],owner=options['value']+1)
                return dict(rows=[selected],matrix=tuple(current),teams=tuple(range(24))+(-1,)*4)
            assert action==9;writes.append(options['matrix']);current[:]=options['matrix'];return dict(changed=1)
    engine=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return engine
    h=Host()
    for team in (0,5,12,3,13):h.fullclone_team(team)
    assert cache['fullclone_teams'][2]['matrix']==original
    assert cache['fullclone_teams'][2]['player']==1
    h.fullclone_team(restore=True)
    assert tuple(current)==original and writes[-1]==original


def test_team_join_keeps_live_control_and_skips_reference_control():
    current=[0]*560
    current[3*20+6]=1          # peer 3 already shares the player's control
    current[5*20+10+7]=1       # peer 5 already has advanced control
    reference=[1]*560          # the reference player grants everything
    row=dict(owner=2,a=1,team=-1);cache={};writes=[]
    class Engine:
        session=SimpleNamespace(lock=threading.RLock(),cache=cache)
        def fullclone(self,action,**options):
            matrix=reference if options.get('value')==0 else current
            if action==8:return dict(rows=[dict(row)],matrix=tuple(matrix),teams=(0,)+(-1,)*27)
            assert action==9;writes.append(options['matrix']);current[:]=options['matrix'];return dict(changed=1)
    engine=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return engine
    Host().fullclone_team(0);m=writes[-1]
    assert (m[3*20+6],m[3*20+7])==(1,0) and m[3*20+0]==1
    assert (m[5*20+10+6],m[5*20+10+7])==(0,1) and m[5*20+10+0]==1
    assert (m[7*20+6],m[7*20+7],m[7*20+10+6],m[7*20+10+7])==(0,0,0,0)


def test_team_restore_keeps_control_toggled_after_join():
    original=tuple((i//3)%2 for i in range(560));current=list(original)
    row=dict(owner=2,a=1,team=-1);cache={};writes=[]
    class Engine:
        session=SimpleNamespace(lock=threading.RLock(),cache=cache)
        def fullclone(self,action,**options):
            if action==8:return dict(rows=[dict(row)],matrix=tuple(current),teams=tuple(range(24))+(-1,)*4)
            assert action==9;writes.append(options['matrix']);current[:]=options['matrix'];return dict(changed=1)
    engine=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return engine
    h=Host();h.fullclone_team(0)
    current[4*20+6]=1;current[6*20+10+7]=1   # toggled after the join
    h.fullclone_team(restore=True);m=writes[-1]
    assert cache['fullclone_teams'][2]['matrix']==original
    for i in range(560):
        if i//20==1:assert m[i]==original[i]
        elif i%20 in (6,7,16,17):assert m[i]==current[i]
        else:assert m[i]==original[i]


def test_unassigned_team_template_keeps_control_flags():
    current=[0]*560;current[2*20+3]=1;current[2*20+7]=1;current[9*20+10+6]=1
    row=dict(owner=2,a=1,team=-1);cache={};writes=[]
    class Engine:
        session=SimpleNamespace(lock=threading.RLock(),cache=cache)
        def fullclone(self,action,**options):
            if action==8:return dict(rows=[dict(row)],matrix=tuple(current),teams=(-1,)*28)
            assert action==9;writes.append(options['matrix']);current[:]=options['matrix'];return dict(changed=1)
    engine=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return engine
    Host().fullclone_team(0);m=writes[-1]
    assert (m[2*20+3],m[2*20+7],m[2*20+6])==(0,1,0)
    assert (m[9*20+10+6],m[9*20+10+7])==(1,0)


def test_partial_control_failure_keeps_original_for_next_restore():
    cache={};requests=[]
    class Engine:
        session=SimpleNamespace(lock=threading.RLock(),cache=cache)
        def fullclone(self,action,**options):
            if options.get('value')==-1:return dict(rows=[dict(owner=25,b=0,c=1)])
            requests.append(options['value'])
            if len(requests)==1:raise RuntimeError('setter failed after one flag changed')
            return dict(changed=1)
    engine=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return engine
    h=Host()
    with pytest.raises(RuntimeError):h.fullclone_toggle_control()
    assert cache['fullclone_control'][25]==2
    assert h.fullclone_toggle_control()['restored'] is True
    assert requests==[3,2]


def test_new_chords_fire_once_and_stop_without_late_parent_actions():
    import time
    from war3_fullclone_hotkeys import manager_type,specs
    keys={};events=[]
    class Base:
        @property
        def fallback_names(self):return ()
        def start(self,items,fn):self.stop();self.emit=fn;return {}
        def stop(self):pass
    api=SimpleNamespace(GetAsyncKeyState=lambda k:0x8000 if keys.get(k) else 0)
    Manager=manager_type(Base,api,lambda spec:bool(keys.get(spec.virtual_key)))
    manager=Manager();manager.start(specs(()),events.append)
    keys.update({ord('I'):True,ord('U'):True});time.sleep(.08)
    assert events==['give_owner']
    time.sleep(.04);assert len(events)==1
    keys.clear();time.sleep(.04)
    keys.update({ord('I'):True});manager.emit('take_control');manager.stop();keys.clear();time.sleep(.05)
    assert events==['give_owner']


def test_existing_process_and_unit_reader_functions_are_identical_to_supplied_source():
    import ast
    root=Path(__file__).resolve().parents[1];upstream=root.parent/'upstream/War3ReforgedTrainer-v2.2.3-source'
    if not upstream.exists():pytest.skip('Upstream preservation tree is outside standalone source bundle')
    for path in ['war3_object_registry.py','war3_engine_transport.py','war3_game_session.py','war3_services/facade_selection.py','war3_services/facade_fields.py','war3_services/facade_abilities.py','war3_services/units.py','war3_services/items.py']:
        assert (root/path).read_bytes()==(upstream/path).read_bytes(),path
    def functions(p):
        tree=ast.parse(p.read_text('utf8'));return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
    assert functions(root/'war3_backend.py')==functions(upstream/'war3_backend.py')


@pytest.mark.parametrize('owned,visible,preview,expected',[(False,True,False,1),(True,True,False,0),(False,False,False,0),(False,True,True,1)])
def test_real_item_core_moves_original_only_and_filters_inventory(dll,owned,visible,preview,expected):
    import war3_fullclone_items_protocol as items
    from war3_game_profile import default_profile
    layout=default_profile().section('registry');tag=layout['item_tag']
    root=c.create_string_buffer(128);slots=c.create_string_buffer(32);owner=c.create_string_buffer(256);obj=c.create_string_buffer(256);base=c.create_string_buffer(8)
    addr=lambda x:c.addressof(x)
    full=(55<<32)|1;raw=0x70686561
    struct.pack_into('<Q',base,0,addr(root));struct.pack_into('<Q',root,24,addr(slots));struct.pack_into('<I',root,48,2)
    struct.pack_into('<IQ',slots,16,0xfffffffe,0) # overwrite below for real slot alignment
    struct.pack_into('<I',slots,16,0xfffffffe);struct.pack_into('<Q',slots,24,addr(owner))
    struct.pack_into('<Q',owner,24,tag);struct.pack_into('<Q',owner,32,full);struct.pack_into('<Q',owner,144,addr(obj))
    struct.pack_into('<Q',obj,24,full);struct.pack_into('<I',obj,112,raw)
    callbacks=[];entries={};position=[2.,3.];moves=[]
    def callback(result,args,fn):
        cb=c.CFUNCTYPE(result,*args)(fn);callbacks.append(cb);return c.cast(cb,c.c_void_p).value
    converter=callback(U,(U,B),lambda a,b:0x100001)
    values={
        'GetItemTypeId':(c.c_uint32,(U,),lambda h:raw),
        'IsItemOwned':(B,(U,),lambda h:owned),
        'IsItemVisible':(B,(U,),lambda h:visible),
        'GetWidgetLife':(c.c_uint32,(U,),lambda h:struct.unpack('<I',struct.pack('<f',100.))[0]),
        'SetItemPosition':(V,(U,F,F),lambda h,x,y:(position.__setitem__(0,x[0]),position.__setitem__(1,y[0]),moves.append(h))),
        'GetItemX':(c.c_uint32,(U,),lambda h:struct.unpack('<I',struct.pack('<f',position[0]))[0]),
        'GetItemY':(c.c_uint32,(U,),lambda h:struct.unpack('<I',struct.pack('<f',position[1]))[0]),
        'GetItemCharges':(I,(U,),lambda h:7),
    }
    for name,sig in items.SIGNATURES:entries[name]=SimpleNamespace(name=name,signature=sig,handler=callback(*values[name]))
    request=items.build_work(entries,0x20000,base=addr(base),converter=converter,item_tag=tag,
        items=[dict(full=full,address=addr(obj),rawcode=raw)],x=400.,y=-800.,preview=preview)
    dll.FCFixtureRegistryRootZero();buf=c.create_string_buffer(request,len(request));dll.FCFixtureRun(buf,2)
    result=items.decode_work(buf.raw)
    assert result['changed']==expected
    assert len(moves)==(expected if not preview else 0)
    assert struct.unpack_from('<Q',obj,24)[0]==full and struct.unpack_from('<I',obj,112)[0]==raw
    assert position==([400.,-800.] if moves else [2.,3.])


@pytest.mark.parametrize('completed,failed,discovered,valid',[(0,0,0,True),(1,0,1,True),(0,1,1,True),(1,1,1,False)])
def test_quest_core_flags_are_read_only_and_ambiguous_flags_are_rejected(dll,completed,failed,discovered,valid):
    import war3_fullclone_status_protocol as status
    vm=c.create_string_buffer(0x4900);host=c.create_string_buffer(8);symbols=c.create_string_buffer(8);node=c.create_string_buffer(64)
    struct.pack_into('<Q',vm,0x4868,c.addressof(host));struct.pack_into('<Q',vm,0x4878,c.addressof(symbols))
    struct.pack_into('<2IQ',node,0x30,7,7,0x100001)
    original=node.raw;callbacks=[];entries={}
    for (name,sig),flag in zip(status.SIGNATURES,(completed,failed,discovered)):
        cb=c.CFUNCTYPE(B,U)(lambda h,flag=flag:flag);callbacks.append(cb)
        entries[name]=SimpleNamespace(name=name,signature=sig,handler=c.cast(cb,c.c_void_p).value)
    p=status.build_work(entries,0x20000,vm=c.addressof(vm),symbols=c.addressof(symbols),host=c.addressof(host),rows=[(c.addressof(node),0x100001)])
    buf=c.create_string_buffer(p,len(p));dll.FCFixtureRun(buf,3);r=status.decode_work(buf.raw)
    assert bool(r[0]['error']) is not valid
    assert node.raw==original


def test_quest_text_keeps_original_description_and_positions_are_separate():
    from test_quest_analysis import analyze
    from war3_fullclone_quests import render
    report=analyze('''globals
quest q=null
rect area=null
trigger t=null
endglobals
function Done takes nothing returns nothing
call QuestSetCompleted(q,true)
endfunction
function main takes nothing returns nothing
set area=Rect(0,0,200,400)
set q=CreateQuest()
call QuestSetTitle(q,"任务标题")
call QuestSetDescription(q,"地图作者的原任务说明")
set t=CreateTrigger()
call TriggerRegisterEnterRectSimple(t,area)
call TriggerAddAction(t,function Done)
endfunction''')
    rows,locations,outcomes=render(report)
    assert '地图作者的原任务说明' in rows[0]['text']
    assert 'X=' not in rows[0]['text']
    assert any(p.locatable for p in locations)

def test_join_team_pins_native_teams_before_write():
    current=[0]*560
    original_teams=(2,0)+(-1,)*26
    later_teams=(5,0)+(-1,)*26
    row=dict(owner=2,a=1,team=2);cache={};queries=[]
    class Engine:
        session=SimpleNamespace(lock=threading.RLock(),cache=cache)
        def fullclone(self,action,**options):
            if action==8:
                queries.append('query')
                teams=later_teams if len(queries)>1 else original_teams
                return dict(rows=[dict(row)],matrix=tuple(current),teams=teams)
            assert action==9;return dict(changed=1)
    engine=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return engine
    Host().fullclone_team(0)
    assert cache['native_teams_snapshot']==original_teams
    Host().fullclone_team(5)
    assert cache['native_teams_snapshot']==original_teams

