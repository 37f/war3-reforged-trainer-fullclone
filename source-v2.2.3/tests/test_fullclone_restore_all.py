"""Bulk restore replays real facade/native fixtures, without any running game."""
from types import SimpleNamespace as NS
from threading import RLock
import pytest
from test_fullclone_migration import World, dll
from war3_services.fullclone import FullCloneFacade


def host(world,dll):
    class Engine:
        session=NS(lock=RLock(),cache={},epoch=3)
        actions=[]
        fail_player=None
        def fullclone(self,action,**kw):
            expected=kw.pop('expected_epoch',None)
            if expected not in (None,self.session.epoch):raise ValueError('地图已变化')
            self.actions.append((action,kw.get('target')))
            if action==20 and kw.get('target')==self.fail_player:raise ValueError('模拟写入失败')
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
    assert h.fullclone_restore_all_teams()==dict(changed=2,total=2)
    assert [p for a,p in e.actions if a==20]==[1,0]
    assert w.alliances[1,2,6]==w.alliances[2,1,7]==1
    assert all(w.alliances[key]==v for key,v in original.items() if key[2] not in (6,7))
    for p,r in e.session.cache['fullclone_teams'].items():
        assert r['matrix']==saved[p]['matrix'] and r['applied'] is None
    assert w.selected==[]


@pytest.mark.parametrize('kind',['matrix','player','identity'])
def test_invalid_record_preflight_prevents_all_setters(dll,kind):
    h,e=host(World(),dll)
    h.fullclone_team(1,player=0);h.fullclone_team(2,player=1)
    records=e.session.cache['fullclone_teams']
    if kind=='matrix':records[2]['matrix']=(0,)
    elif kind=='player':records[2]['player']=25
    else:records[999]=records.pop(2)
    e.actions.clear()
    with pytest.raises(ValueError):h.fullclone_restore_all_teams()
    assert not any(a==20 for a,p in e.actions)


def test_partial_failure_stops_once_and_preserves_first_snapshots(dll):
    h,e=host(World(),dll)
    for player in (0,1,2):h.fullclone_team(2,player=player)
    originals={p:r['matrix'] for p,r in e.session.cache['fullclone_teams'].items()}
    e.actions.clear();e.fail_player=1
    with pytest.raises(ValueError,match='已恢复 1/3'):h.fullclone_restore_all_teams()
    assert [p for a,p in e.actions if a==20]==[2,1]
    assert originals=={p:r['matrix'] for p,r in e.session.cache['fullclone_teams'].items()}


def test_map_epoch_change_during_preflight_never_writes(dll):
    h,e=host(World(),dll);h.fullclone_team(1,player=0);h.fullclone_team(2,player=1)
    original=e.fullclone;e.actions.clear()
    def change(action,**kw):
        result=original(action,**kw)
        e.session.epoch+=1
        return result
    e.fullclone=change
    with pytest.raises(ValueError,match='地图已变化'):h.fullclone_restore_all_teams()
    assert not any(a==20 for a,p in e.actions)


def test_empty_apply_result_is_reported_as_partial_failure(dll):
    h,e=host(World(),dll);h.fullclone_team(1,player=0)
    h.fullclone_team=lambda **kw:dict(changed=0)
    with pytest.raises(ValueError,match='已恢复 0/1'):h.fullclone_restore_all_teams()
