"""Bulk restore uses the real bridge fixture without attaching to the game."""
from types import SimpleNamespace as NS
from threading import RLock
import pytest
import ctypes as c
from test_fullclone_migration import World, dll, U, I, V
from war3_services.fullclone import FullCloneFacade


def host(world,dll):
    class Engine:
        session=NS(lock=RLock(),cache={},epoch=3)
        actions=[]
        def fullclone(self,action,**kw):
            expected=kw.pop('expected_epoch',None)
            if expected not in (None,self.session.epoch):raise ValueError('地图已变化')
            self.actions.append((action,kw.get('target')))
            return world.run(dll,action,**kw)
    engine=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return engine
    return Host(),engine


def test_restore_empty_has_no_game_calls(dll):
    h,e=host(World(),dll)
    assert h.fullclone_restore_all_teams()==dict(changed=0,total=0)
    assert e.actions==[]


@pytest.mark.parametrize('restore_first',[False,True])
def test_reverse_first_snapshot_order_restores_overlapping_pairs_and_keeps_control(dll,restore_first):
    w=World();w.selected=[]
    for a in range(1,29):
        for b in range(1,29):
            for k in range(10):w.alliances[a,b,k]=int(a==b or (k<6 and a<=24 and b<=24 and (a-1)//2==(b-1)//2))
    original=dict(w.alliances);h,e=host(w,dll)
    h.fullclone_team(1,player=0)
    h.fullclone_team(2,player=1)  # B's first snapshot already contains A's change.
    assert e.session.cache['fullclone_teams'][2]['matrix'][0]!=original[2,1,0]
    if restore_first:h.fullclone_team(restore=True,player=0)
    saved={p:dict(r) for p,r in e.session.cache['fullclone_teams'].items()}
    w.alliances[1,2,6]=w.alliances[2,1,7]=1
    e.actions.clear()
    assert h.fullclone_restore_all_teams()==dict(changed=2,total=2,restored=(0,1),skipped=())
    assert e.actions==[(21,None)]
    assert w.alliances[1,2,6]==w.alliances[2,1,7]==1
    assert all(w.alliances[key]==v for key,v in original.items() if key[2] not in (6,7))
    for p,r in e.session.cache['fullclone_teams'].items():
        assert r['matrix']==saved[p]['matrix'] and r['applied'] is None
    assert w.selected==[]


@pytest.mark.parametrize('kind',['matrix','player','duplicate'])
def test_invalid_record_preflight_prevents_all_setters(dll,kind):
    w=World();h,e=host(w,dll)
    h.fullclone_team(1,player=0);h.fullclone_team(2,player=1)
    records=e.session.cache['fullclone_teams']
    if kind=='matrix':records[2]['matrix']=(0,)
    elif kind=='player':records[2]['player']=25
    else:records[2]['player']=0
    writes=[];w.bind('SetPlayerAlliance',V,(U,U,U,I),lambda *args:writes.append(args))
    with pytest.raises(ValueError):h.fullclone_restore_all_teams()
    assert writes==[]


def test_rescuable_slot_with_same_owner_is_restored_without_playing_slot_guard(dll):
    w=World();h,e=host(w,dll)
    h.fullclone_team(2,player=1)
    w.bind('GetPlayerSlotState',U,(U,),lambda p:0 if p==2 else 1)
    e.actions.clear()
    assert h.fullclone_restore_all_teams()==dict(changed=1,total=1,restored=(1,),skipped=())
    assert e.actions==[(21,None)]


def test_five_records_one_stale_identity_restores_other_four(dll):
    w=World();h,e=host(w,dll)
    for player in (0,2,3,4,1):h.fullclone_team(3,player=player)
    records=e.session.cache['fullclone_teams']
    records[999]=records.pop(2)
    related={key:value for key,value in w.alliances.items() if 2 in key[:2]}
    e.actions.clear()
    assert h.fullclone_restore_all_teams()==dict(changed=4,total=5,restored=(0,2,3,4),skipped=(1,))
    assert e.actions==[(21,None)]
    assert related=={key:value for key,value in w.alliances.items() if 2 in key[:2]}
    assert records[999]['applied']==3 and all(records[p]['applied'] is None for p in (1,3,4,5))


def test_all_records_fit_and_restore_both_neutral_slots(dll):
    w=World();h,e=host(w,dll)
    for p in (*range(24),24,27):h.fullclone_team(1,player=p)
    e.actions.clear()
    assert h.fullclone_restore_all_teams()==dict(changed=26,total=26,restored=(*range(24),24,27),skipped=())
    assert e.actions==[(21,None)]
    assert not any(w.alliances.values())


def test_failed_readback_keeps_every_first_record(dll):
    w=World();h,e=host(w,dll)
    h.fullclone_team(1,player=0);h.fullclone_team(2,player=1)
    w.alliances[1,3,0]=1
    w.bind('SetPlayerAlliance',V,(U,U,U,I),lambda *args:None)
    originals={p:dict(r) for p,r in e.session.cache['fullclone_teams'].items()}
    with pytest.raises(RuntimeError,match='error=1006'):h.fullclone_restore_all_teams()
    assert e.session.cache['fullclone_teams']==originals


def test_map_epoch_change_before_callback_never_writes(dll):
    w=World();h,e=host(w,dll);h.fullclone_team(1,player=0)
    original=e.fullclone;e.actions.clear()
    def change(action,**kw):
        e.session.epoch+=1
        return original(action,**kw)
    e.fullclone=change
    with pytest.raises(ValueError,match='地图已变化'):h.fullclone_restore_all_teams()
    assert not e.actions


def test_missing_neutral_identity_has_specific_error(dll):
    w=World();w.bind('Player',U,(I,),lambda p:1 if p==24 else p+1)
    assert not w.run(dll,19,target=0)['rows'][0]['c']&(1<<24)
    with pytest.raises(ValueError,match='无法确认玩家 25 的槽位'):
        w.run(dll,19,target=24)


def test_original_unavailable_peer_is_not_rewritten_after_it_appears(dll):
    w=World();h,e=host(w,dll)
    w.bind('Player',U,(I,),lambda p:0 if p==2 else p+1)
    h.fullclone_team(3,player=0)
    w.bind('Player',U,(I,),lambda p:p+1)
    w.alliances[1,3,0]=1
    w.alliances[3,1,0]=1
    assert h.fullclone_restore_all_teams()['restored']==(0,)
    assert w.alliances[1,3,0]==w.alliances[3,1,0]==1
