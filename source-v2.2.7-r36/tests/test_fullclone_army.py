"""Execute the R34 C transaction against an owned, inert fixture world."""
import ctypes as c
import faulthandler
import struct
from types import SimpleNamespace
import pytest
from test_fullclone_migration import World,dll,U,I,B,V,F
import war3_fullclone_army_protocol as army


def world():
    w=World();w.selected=[1002]
    w.bind('GroupEnumUnitsOfPlayer',V,(U,U,U),lambda g,p,f:w.group.extend(u for u,v in w.units.items() if v['owner']==p))
    w.bind('GetWidgetLife',c.c_uint32,(U,),lambda u:struct.unpack('<I',struct.pack('<f',w.units[u]['hp']))[0])
    w.bind('IsUnitType',B,(U,U),lambda u,t:w.units[u]['level']>0)
    w.bind('ConvertUnitType',U,(I,),lambda i:i)
    w.bind('IsUnitHidden',B,(U,),lambda u:w.units[u].get('hidden',False))
    return w


def run(w,dll,mode=0):
    p=army.build_work(w.entries,0x20000,mode=mode);buf=c.create_string_buffer(p,len(p))
    result=dll.FCFixtureRun(buf,4)
    return army.decode_work(buf.raw,result)


def test_owner_is_selected_player_and_zero_mana_needs_no_magic_write(dll):
    w=world();other=dict(w.units[1001]);result=run(w,dll)
    assert result['player']==1 and result['owner']==2 and result['changed']==result['eligible']==2
    assert w.units[1001]==other
    assert w.units[1002]['hp']==420 and w.units[1002]['mp']==0
    assert w.units[1003]['mp']==300 and w.calls.count(('destroy',123))==2


@pytest.mark.parametrize('mode,target,untouched',[(1,1003,1002),(2,1002,1003)])
def test_hero_and_nonhero_filters_only_change_the_requested_owner_units(dll,mode,target,untouched):
    w=world();before=dict(w.units[untouched]);result=run(w,dll,mode)
    assert result['changed']==result['eligible']==1
    assert w.units[untouched]==before and w.units[target]['hp']==w.units[target]['maxhp']


@pytest.mark.parametrize('owner',[1,25,28])
def test_local_and_neutral_owners_are_identified_without_diplomacy_changes(dll,owner):
    w=world();w.units[1002]['owner']=owner;result=run(w,dll)
    assert result['owner']==owner and result['player']==owner-1
    assert not w.alliances and all(v['owner']==(owner if u==1002 else 1 if u==1001 else 2) for u,v in w.units.items())


def test_dead_and_hidden_units_are_skipped_without_resurrection(dll):
    w=world();w.units[1003]['hp']=0.;w.units[1002]['hidden']=True
    before={u:dict(v) for u,v in w.units.items()};result=run(w,dll)
    assert result['changed']==result['eligible']==0
    assert result['skipped_dead']==result['skipped_hidden']==1 and w.units==before


def test_army_can_contain_more_than_the_selection_limit(dll):
    w=world()
    for u in range(2000,2040):w.units[u]=dict(w.units[1002],hp=1.)
    result=run(w,dll)
    assert result['changed']==result['eligible']==42 and result['visited']==42


def test_already_full_units_do_not_call_setters(dll):
    w=world()
    for v in w.units.values():v.update(hp=v['maxhp'],mp=v['maxmp'])
    def setter(*args):pytest.fail('No setter should run for a full unit')
    w.bind('SetUnitState',V,(U,U,F),setter)
    result=run(w,dll)
    assert result['changed']==result['attempted']==0 and result['eligible']==2


def test_no_selection_is_a_clean_noop(dll):
    w=world();w.selected=[];result=run(w,dll)
    assert result['player']==-1 and result['owner']==result['changed']==result['visited']==0


def test_bad_maximum_is_rejected_before_any_setter(dll):
    w=world();w.units[1002]['maxhp']=float('nan')
    with pytest.raises(RuntimeError,match='已尝试 0'):run(w,dll)
    assert w.units[1002]['hp']==20 and w.calls.count(('destroy',123))==2


def test_setter_ownership_change_aborts_before_mana_and_cleans_the_group(dll):
    w=world();writes=[]
    def setter(u,state,value):
        writes.append((u,state));w.units[u]['hp']=value[0];w.units[u]['owner']=1
    w.bind('SetUnitState',V,(U,U,F),setter)
    with pytest.raises(RuntimeError,match='已尝试 1.*已补满 0'):run(w,dll)
    assert writes==[(1002,0)] and w.units[1003]['mp']==100
    assert w.calls.count(('destroy',123))==2


def test_readback_failure_is_not_replayed(dll):
    w=world();writes=[];w.bind('SetUnitState',V,(U,U,F),lambda *a:writes.append(a[0]))
    with pytest.raises(RuntimeError,match='不自动重放'):run(w,dll)
    assert writes==[1002] and w.calls.count(('destroy',123))==2


def test_native_setter_fault_reports_partial_attempt_and_destroys_group(dll):
    w=world();w.entries['SetUnitState'].handler=c.cast(dll.FCFixtureFaultState,c.c_void_p).value
    enabled=faulthandler.is_enabled();faulthandler.disable()
    try:
        with pytest.raises(RuntimeError,match='已尝试 1'):run(w,dll)
    finally:
        if enabled:faulthandler.enable()
    assert w.calls.count(('destroy',123))==2


@pytest.mark.parametrize('mode',[True,-1,3,'all'])
def test_invalid_modes_never_build_a_request(mode):
    with pytest.raises(ValueError,match='范围'):army.build_work({},0x20000,mode=mode)


def test_pointer_signature_and_initial_result_validation():
    w=world();p=army.build_work(w.entries,0x20000)
    bad=bytearray(p);struct.pack_into('<I',bad,588,1)
    with pytest.raises(ValueError,match='初始化'):army.validate_work(bad)
    old=w.entries['GetUnitState'];w.entries['GetUnitState']=SimpleNamespace(name=old.name,signature='wrong',handler=old.handler)
    with pytest.raises(ValueError,match='签名'):army.build_work(w.entries,0x20000)
