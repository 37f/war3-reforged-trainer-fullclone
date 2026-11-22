"""R35 native transactions in an owned inert fixture, never the game."""
import ctypes as c,faulthandler,struct,threading
from types import SimpleNamespace as NS
import pytest
from test_fullclone_migration import World,dll,U,I,B,V,F
import war3_fullclone_extra_protocol as p
from war3_fullclone_extras import formation_points,clone_formation,toggle_frozen,restore_all_frozen
from war3_fullclone_supplies import parse,save,load

bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]

def world():
    w=World();w.selected=[1002];w.objects={};w.items={};w.bags={};w.abilities={};w.nextitem=5000
    def bind(name,result,args,fn):
        cb=c.CFUNCTYPE(result,*args)(fn);w.callbacks.append(cb)
        w.entries[name]=NS(name=name,signature=dict(p.SIGNATURES)[name],handler=c.cast(cb,c.c_void_p).value)
    w.extra_bind=bind
    def resolve(u):
        if u not in w.units:return 0
        if u not in w.objects:
            w.objects[u]=c.create_string_buffer(512);struct.pack_into('<Q',w.objects[u],24,u+1000000)
        return c.addressof(w.objects[u])
    w.resolver=c.CFUNCTYPE(U,U)(resolve)
    bind('GroupEnumUnitsOfPlayer',V,(U,U,U),lambda g,owner,f:w.group.extend(u for u,v in w.units.items() if v['owner']==owner))
    bind('GetWidgetLife',c.c_uint32,(U,),lambda u:bits(w.units[u]['hp']))
    bind('ConvertUnitType',U,(I,),lambda v:v)
    bind('IsUnitType',B,(U,U),lambda u,t:w.units[u]['level']>0 if t==0 else w.units[u].get('building',False))
    bind('IsUnitHidden',B,(U,),lambda u:w.units[u].get('hidden',False))
    bind('IsUnitPaused',B,(U,),lambda u:w.units[u].get('paused',False))
    bind('PauseUnit',V,(U,I),lambda u,v:w.units[u].update(paused=bool(v)))
    def create(code,x,y):
        w.nextitem+=1;w.items[w.nextitem]=dict(rawcode=code,charges=7,x=x[0],y=y[0]);return w.nextitem
    bind('CreateItem',U,(c.c_uint32,F,F),create)
    bind('GetItemTypeId',c.c_uint32,(U,),lambda u:w.items.get(u,{}).get('rawcode',0))
    bind('SetItemCharges',V,(U,I),lambda u,n:w.items[u].update(charges=n))
    bind('GetItemCharges',I,(U,),lambda u:w.items[u]['charges'])
    bind('UnitInventorySize',I,(U,),lambda u:6)
    bind('UnitItemInSlot',U,(U,I),lambda u,k:(w.bags.get(u,[])+[0]*6)[k])
    bind('UnitAddItem',B,(U,U),lambda u,i:(w.bags.setdefault(u,[]).append(i),1)[1])
    bind('GetUnitX',c.c_uint32,(U,),lambda u:bits(100.))
    bind('GetUnitY',c.c_uint32,(U,),lambda u:bits(200.))
    bind('GetItemX',c.c_uint32,(U,),lambda i:bits(w.items[i]['x']))
    bind('GetItemY',c.c_uint32,(U,),lambda i:bits(w.items[i]['y']))
    def create_unit(owner,code,x,y,f):
        w.units[1100]=dict(w.units[1002],owner=owner,rawcode=code);return 1100
    bind('CreateUnit',U,(U,c.c_uint32,F,F,F),create_unit)
    bind('RemoveUnit',V,(U,),lambda u:(w.calls.append(('remove',u)),w.units.pop(u,None)))
    bind('UnitAddAbility',B,(U,c.c_uint32),lambda u,code:(w.abilities.__setitem__((u,code),1),1)[1])
    bind('GetUnitAbilityLevel',I,(U,c.c_uint32),lambda u,code:w.abilities.get((u,code),0))
    bind('BlzSetUnitMaxMana',V,(U,I),lambda u,n:w.units[u].update(maxmp=n))
    bind('SetUnitVertexColor',V,(U,I,I,I,I),lambda *args:w.calls.append(('color',args)))
    bind('SetUnitPathing',V,(U,I),lambda *args:w.calls.append(('pathing',args)))
    bind('SetUnitUseFood',V,(U,I),lambda *args:w.calls.append(('food',args)))
    bind('IssuePointOrderById',B,(U,c.c_uint32,F,F),lambda u,order,x,y:(w.calls.append(('cast',u,order,x[0],y[0])),1)[1])
    return w

def run(w,dll,action,**opts):
    opts.pop('expected_epoch',None)
    raw=p.build_work(w.entries,0x20000,action,resolver=c.cast(w.resolver,c.c_void_p).value,**opts)
    buf=c.create_string_buffer(raw,len(raw));n=dll.FCFixtureRun(buf,5)
    return p.decode_work(buf.raw,n)

def host(w,dll):
    engine=NS(session=NS(epoch=1,closed=False,lock=threading.RLock(),cache={}))
    engine.fullclone_extra=lambda action,**kw:run(w,dll,action,**kw)
    return NS(_engine_instance_24268=lambda:engine,fullclone_owner=lambda:dict(owner=w.units[w.selected[0]]['owner']) if w.selected else None),engine

@pytest.mark.parametrize('scope,building,expected',[(0,0,[1003]),(0,1,[1002,1003]),(1,1,[1003]),(2,1,[1002])])
def test_freeze_snapshot_scope_buildings_and_player(dll,scope,building,expected):
    w=world();w.units[1002]['building']=True
    r=run(w,dll,1,scope=scope,flag=building)
    assert [v['unit'] for v in r['rows']]==expected and r['owner']==2 and r['player']==1
    assert w.calls.count(('destroy',123))==2 and not any(v.get('paused') for v in w.units.values())

def test_freeze_restore_preserves_map_paused_and_original_snapshot(dll):
    w=world();w.units[1003]['paused']=True;t,e=host(w,dll)
    assert toggle_frozen(t)['changed']==1
    assert w.units[1002]['paused'] and w.units[1003]['paused']
    assert toggle_frozen(t,scope='heroes',buildings=True)['restored']
    assert not w.units[1002]['paused'] and w.units[1003]['paused'] and not e.session.cache['fullclone_frozen']

@pytest.mark.parametrize('change',['owner','full','dead'])
def test_restore_skips_reused_dead_or_transferred_identity(dll,change):
    w=world();t,e=host(w,dll);toggle_frozen(t)
    if change=='owner':w.units[1002]['owner']=1
    elif change=='dead':w.units[1002]['hp']=0
    else:struct.pack_into('<Q',w.objects[1002],24,999999)
    w.selected=[];r=restore_all_frozen(t)
    assert r['skipped']==1 and w.units[1002]['paused'] and not w.units[1003]['paused']

def test_freeze_fault_keeps_before_record_for_recovery(dll):
    w=world();w.units[1003]['paused']=True;t,e=host(w,dll);state=c.c_uint32(0)
    w.extra_bind('IsUnitPaused',B,(U,),lambda u:state.value if u==1002 else 1)
    dll.FCFixturePauseState.argtypes=[c.POINTER(c.c_uint32)];dll.FCFixturePauseState(c.byref(state))
    w.entries['PauseUnit'].handler=c.cast(dll.FCFixturePauseFault,c.c_void_p).value
    enabled=faulthandler.is_enabled();faulthandler.disable()
    try:
        with pytest.raises(RuntimeError,match='记录保留'):toggle_frozen(t)
    finally:
        if enabled:faulthandler.enable()
    assert state.value==1 and e.session.cache['fullclone_frozen'][2]['pending']
    w.extra_bind('PauseUnit',V,(U,I),lambda u,v:setattr(state,'value',v))
    assert toggle_frozen(t)['changed']==1 and state.value==0

def test_old_epoch_restore_does_not_write(dll):
    w=world();t,e=host(w,dll);toggle_frozen(t);e.session.epoch+=1
    with pytest.raises(ValueError,match='地图'):restore_all_frozen(t)
    assert w.units[1002]['paused']

def test_dead_hidden_units_not_in_snapshot(dll):
    w=world();w.units[1002]['hidden']=True;w.units[1003]['hp']=0
    assert run(w,dll,1)['rows']==[]

def test_supplies_hero_preserve_existing_and_explicit_charges(dll):
    w=world();w.selected=[1003];w.bags[1003]=[99]
    r=run(w,dll,3,rows=parse('phea 2 1\npman 1'))
    assert r['changed']==3 and w.bags[1003][0]==99
    assert [i['charges'] for i in w.items.values()]==[1,1,7]

@pytest.mark.parametrize('bad',['slots','nonhero','multi','dead'])
def test_supply_preflight_blocks_writes(dll,bad):
    w=world();w.selected=[1003]
    if bad=='slots':w.bags[1003]=[99]*6
    elif bad=='nonhero':w.selected=[1002]
    elif bad=='multi':w.selected=[1001,1003]
    else:w.units[1003]['hp']=0
    with pytest.raises(RuntimeError):run(w,dll,3,rows=parse('phea 1'))
    assert not w.items

def test_ground_supplies_need_no_selection(dll):
    w=world();w.selected=[];r=run(w,dll,3,flag=1,rows=parse('phea 3 0'),x=123.,y=-456.)
    assert r['changed']==3 and not w.bags
    assert all((i['x'],i['y'],i['charges'])==(123.,-456.,0) for i in w.items.values())

def test_supply_partial_failure_not_repeated(dll):
    w=world();old=w.entries['CreateItem'];calls=[]
    def create(code,x,y):
        calls.append(code)
        if len(calls)>1:return 0
        w.items[5001]=dict(rawcode=code,charges=1,x=x[0],y=y[0]);return 5001
    w.extra_bind('CreateItem',U,(c.c_uint32,F,F),create)
    with pytest.raises(RuntimeError,match='已完成1项'):run(w,dll,3,flag=1,rows=parse('phea 3'))
    assert len(calls)==2 and len(w.items)==1

@pytest.mark.parametrize('code,order',[('AHbz',852089),('AHfs',852488),('ANrf',852238)])
def test_fixed_point_spells_create_order_cleanup_and_identity(dll,code,order):
    w=world();raw=int.from_bytes(code.encode(),'big');r=run(w,dll,4,rawcode=raw,x=10,y=20)
    assert r['target']==1100 and r['owner']==1 and ('food',(1100,0)) in w.calls
    kw=dict(rawcode=raw,target=r['target'],owner=r['owner'],expected_full=r['full'],x=10,y=20)
    run(w,dll,5,**kw);assert ('cast',1100,order,10.,20.) in w.calls
    run(w,dll,6,**kw);assert 1100 not in w.units

def test_point_setup_failure_cleans_owned_carrier(dll):
    w=world();w.extra_bind('UnitAddAbility',B,(U,c.c_uint32),lambda *a:0)
    with pytest.raises(RuntimeError):run(w,dll,4,rawcode=int.from_bytes(b'AHbz','big'))
    assert ('remove',1100) in w.calls

def test_point_cleanup_rejects_reused_handle(dll):
    w=world();raw=int.from_bytes(b'AHbz','big');r=run(w,dll,4,rawcode=raw)
    struct.pack_into('<Q',w.objects[1100],24,r['full']+1)
    with pytest.raises(RuntimeError):run(w,dll,6,rawcode=raw,target=r['target'],expected_full=r['full'],owner=r['owner'])
    assert 1100 in w.units

@pytest.mark.parametrize('kind',['square','ring','line','scatter'])
def test_formation_spacing_and_centred_single(kind):
    pts=formation_points(kind,25,128,100,200)
    assert len(set(pts))==25
    assert min(mathdist(a,b) for i,a in enumerate(pts) for b in pts[i+1:])>=70
    assert formation_points(kind,1,128,100,200)==[(100.,200.)]

def mathdist(a,b):return ((a[0]-b[0])**2+(a[1]-b[1])**2)**.5

@pytest.mark.parametrize('text',['','phea 0','phea 33','phea 1 -2','abc 1','中文 1','phea 32\npman 1','phea 1 1000000001'])
def test_invalid_supply_text(text):
    with pytest.raises(ValueError):parse(text)

def test_three_pack_save_reload_and_invalid_save_preserves_file(tmp_path,monkeypatch):
    from war3_fullclone_application import DEFAULTS
    from war3_fullclone_supplies import path
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));o=dict(DEFAULTS,supply_text_1='phea 2 1',supply_text_2='stwp 1')
    save(o);before=path().read_bytes();assert load()['supply_text_1']=='phea 2 1'
    o['supply_text_3']='invalid'
    with pytest.raises(ValueError):save(o)
    assert path().read_bytes()==before and not list(path().parent.glob('*.tmp'))

@pytest.mark.parametrize('mode',['author','self','selected','player'])
def test_formation_reuses_original_clone_and_ownership(mode):
    calls=[];engine=NS(session=NS(lock=threading.RLock()))
    def clone(*args,**kw):calls.append((args,kw));return dict(rows=[dict(clone=len(calls)+100)],ability_issues=[])
    engine.fullclone_clone_state=clone
    t=NS(_engine_instance_24268=lambda:engine,_capture_clone_sources_24268=lambda:('binding',),
        query_mouse_world_position=lambda:(0.,0.),fullclone_owner=lambda:dict(a=2),_float_bits=bits,clone_batch_24268=clone)
    assert clone_formation(t,3,'line','128',owner_mode=mode,player=27)['count']==3
    assert [struct.unpack('<f',struct.pack('<I',kw['spawn_x_bits']))[0] for _,kw in calls]==[-128.,0.,128.]
    if mode=='player':assert all(args==(('binding',),27) for args,kw in calls)
    else:assert all(kw['preserve_owner']==(mode in ('author','selected')) and kw['expected_sources']==('binding',) for _,kw in calls)

def test_formation_multi_selection_and_bad_gap_are_preflight_errors():
    engine=NS(session=NS(lock=threading.RLock()))
    t=NS(_engine_instance_24268=lambda:engine,_capture_clone_sources_24268=lambda:('a','b'))
    with pytest.raises(ValueError,match='源单位'):clone_formation(t,3,'ring','128')
    with pytest.raises(ValueError):formation_points('ring',3,float('nan'),0,0)

@pytest.mark.parametrize('owner',[25,28])
def test_freeze_neutrals_and_restore_preserve_ownership(dll,owner):
    w=world();w.units[1002]['owner']=owner;t,e=host(w,dll)
    assert toggle_frozen(t)['changed']==1 and w.units[1002]['owner']==owner
    assert toggle_frozen(t)['changed']==1 and not w.units[1002]['paused'] and not w.alliances

def test_cap_is_read_only_and_precedes_freeze_writes(dll):
    w=world()
    for u in range(2000,6097):w.units[u]=dict(w.units[1002])
    with pytest.raises(RuntimeError,match='保护上限'):run(w,dll,1)
    assert not any(v.get('paused') for v in w.units.values()) and w.calls.count(('destroy',123))==2

def test_point_setup_setter_fault_still_cleans_carrier(dll):
    w=world();w.entries['SetUnitState'].handler=c.cast(dll.FCFixtureFaultState,c.c_void_p).value
    enabled=faulthandler.is_enabled();faulthandler.disable()
    try:
        with pytest.raises(RuntimeError):run(w,dll,4,rawcode=int.from_bytes(b'AHbz','big'))
    finally:
        if enabled:faulthandler.enable()
    assert ('remove',1100) in w.calls
