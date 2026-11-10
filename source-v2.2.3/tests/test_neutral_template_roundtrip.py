"""Exercise neutral template round trips with the real x64 bridge fixture."""
from types import SimpleNamespace as NS
from threading import RLock
import pytest
from test_fullclone_migration import World, dll
from war3_services.fullclone import FullCloneFacade


def fixture(dll):
    w=World();w.selected=[]
    for a in range(1,29):
        for b in range(1,29):
            for flag in range(10):
                friendly=(a==b or a<=24 and b<=24 and (a-1)//2==(b-1)//2 or
                          (a==28 and b<=24 or b==28 and a<=24))
                w.alliances[a,b,flag]=int(friendly and flag<6)
    class Engine:
        session=NS(lock=RLock(),cache={},epoch=3)
        actions=[]
        def fullclone(self,action,**kw):
            expected=kw.pop('expected_epoch',None)
            assert expected in (None,3)
            self.actions.append((action,kw.get('target')))
            return w.run(dll,action,**kw)
    e=Engine()
    class Host(FullCloneFacade):
        def _engine_instance_24268(self):return e
    return w,e,Host()


@pytest.mark.parametrize('player,target',[(24,12),(27,13)])
@pytest.mark.parametrize('direct',[False,True])
def test_neutral_drag_to_ordinary_and_back_restores_original_relations(dll,player,target,direct):
    w,e,h=fixture(dll)
    if not direct:w.selected=[1001];w.units[1001]['owner']=player+1
    selected=list(w.selected);options=dict(player=player) if direct else {}
    original=w.run(dll,19,target=player)['matrix']
    h.fullclone_team(0,**options)
    assert w.run(dll,19,target=player)['matrix']!=original
    # Explicit control changes remain independent of the diplomacy round trip.
    w.alliances[player+1,3,6]=1;w.alliances[3,player+1,7]=1
    control={k:v for k,v in w.alliances.items() if k[2] in (6,7)}
    h.fullclone_team(target,**options)
    after=w.run(dll,19,target=player)['matrix']
    assert all(after[i]==v for i,v in enumerate(original) if i%20 not in (6,7,16,17))
    assert all(w.alliances[k]==v for k,v in control.items())
    assert e.session.cache['fullclone_teams'][player+1]['matrix']==original
    assert set(a for a,p in e.actions)==({19,20} if direct else {8,9}) and w.selected==selected


def test_earlier_other_player_move_cannot_pollute_neutral_first_snapshot(dll):
    w,e,h=fixture(dll);original=w.run(dll,19,target=27)['matrix']
    h.fullclone_team(12,player=0)  # Changes the passive neutral's reverse relation.
    h.fullclone_team(0,player=27)
    assert e.session.cache['fullclone_teams'][28]['matrix'][0]!=original[0]
    h.fullclone_team(13,player=27)
    after=w.run(dll,19,target=27)['matrix']
    assert all(after[i]==v for i,v in enumerate(original) if i%20 not in (6,7,16,17))


@pytest.mark.parametrize('reference,target',[(24,12),(27,13)])
def test_other_player_receives_original_neutral_template_after_neutral_was_moved(dll,reference,target):
    w,e,h=fixture(dll);original=w.run(dll,19,target=reference)['matrix']
    h.fullclone_team(0,player=reference)
    h.fullclone_team(target,player=2)
    after=w.run(dll,19,target=2)['matrix']
    assert all(after[i]==v for i,v in enumerate(original) if i//20!=2 and i%20 not in (6,7,16,17))


def test_neutral_round_trip_and_bulk_restore_keep_the_first_records(dll):
    w,e,h=fixture(dll);original=dict(w.alliances)
    for player,target in [(27,0),(24,1),(27,13),(24,12),(0,13),(1,12),(27,2)]:
        h.fullclone_team(target,player=player)
    h.fullclone_restore_all_teams()
    assert w.alliances==original


@pytest.mark.parametrize('bad',['record','reference'])
def test_uncertain_neutral_baseline_does_not_write(dll,bad):
    w,e,h=fixture(dll);h.fullclone_team(0,player=27)
    if bad=='record':e.session.cache['fullclone_teams'][28]['matrix']=()
    else:
        query=e.fullclone
        def wrong(action,**kw):
            result=query(action,**kw)
            if action==19 and kw.get('target')==27:result['rows'][0]['a']=24
            return result
        e.fullclone=wrong
    e.actions.clear()
    with pytest.raises(ValueError):h.fullclone_team(13,player=0)
    assert not any(action==20 for action,target in e.actions)


@pytest.mark.parametrize('player,team',[(24,0),(27,0),(24,-1),(27,-1),(0,0),(0,-1)])
def test_owner_monitor_distinguishes_neutral_raw_team_from_ordinary_team(player,team):
    from war3_fullclone_desktop import owner_status
    row=dict(handle=1001,owner=player+1,rawcode=0x68666f6f,a=player,team=team)
    trainer=NS(fullclone_owner=lambda:dict(row),fullclone_player_name=lambda p:'',
        _engine_instance_24268=lambda:NS(session=NS(epoch=3,cache={})))
    result=owner_status(NS(app=NS(elephant_trainer=lambda:trainer)))
    if player in (24,27):
        assert f'特殊中立槽位（原生队伍原始值 {team}）' in result['message']
        assert '原生队伍 1' not in result['message']
    else:assert ('原生队伍 1' if team==0 else '未分配普通队伍') in result['message']
