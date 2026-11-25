"""Single-operation undo uses the existing native fixture and map session records."""
from contextlib import nullcontext
from types import SimpleNamespace as NS

import pytest

from test_fullclone_migration import World, dll, ownership, V, U, I
from test_fullclone_restore_all import host
from war3_fullclone_desktop import operation_history, undo_operation
from war3_fullclone_history import HISTORY_LIMIT, snapshot, undo


def test_unit_transfers_undo_one_at_a_time_without_selection(ownership):
    world, trainer, engine, _ = ownership
    world.selected = [1001]
    trainer.fullclone_give_owner(1)  # Player 1 -> 2 -> 3.
    trainer.fullclone_give_owner(2)
    world.selected = []
    newest, first = snapshot(engine.session.cache)
    assert newest['targets'] == [dict(unit='Hpal', source=1, destination=2, status='pending')]
    assert first['targets'][0]['status'] == 'newer'
    assert undo(engine, first['id'])['undone'] == 0
    assert world.units[1001]['owner'] == 3
    assert undo(engine, newest['id'])['undone'] == 1
    assert world.units[1001]['owner'] == 2
    assert undo(engine, newest['id'])['undone'] == 0
    assert trainer.fullclone_restore_owners(all_units=True) == dict(changed=1, skipped=0)
    assert world.units[1001]['owner'] == 1
    assert snapshot(engine.session.cache)[-1]['targets'][0]['status'] == 'superseded'


def test_unit_return_to_original_then_undo_recovers_the_first_record(ownership):
    world, trainer, engine, _ = ownership
    world.selected = [1001]
    trainer.fullclone_give_owner(1)
    trainer.fullclone_give_owner(0)
    newest, first = snapshot(engine.session.cache)
    assert engine.session.cache['fullclone_original_owners'] == {}
    assert undo(engine, newest['id'])['undone'] == 1
    assert world.units[1001]['owner'] == 2
    assert undo(engine, first['id'])['undone'] == 1
    assert world.units[1001]['owner'] == 1
    assert engine.session.cache['fullclone_original_owners'] == {}


def test_unit_undo_only_updates_still_matching_targets(ownership):
    world, trainer, engine, identity = ownership
    trainer.fullclone_give_owner(2)
    entry, = snapshot(engine.session.cache)
    identity(1001, 0x500000000 + 1001)
    world.units[1002]['owner'] = 6
    result = undo(engine, entry['id'])
    assert result['undone'] == 1
    assert [item['status'] for item in result['entries'][0]['targets']] == ['unit_changed','owner_changed','undone']
    assert [world.units[unit]['owner'] for unit in (1001,1002,1003)] == [3,6,2]


def test_unit_unconfirmed_undo_retains_known_owners_for_original_recovery(ownership):
    world, trainer, engine, _ = ownership
    world.selected = [1001]
    trainer.fullclone_give_owner(1)
    trainer.fullclone_give_owner(2)
    entry, _ = snapshot(engine.session.cache)
    world.bind('SetUnitOwner', V, (U,U,I), lambda *args: None)
    result = undo(engine, entry['id'])
    assert result['undone'] == 0 and result['entries'][0]['targets'][0]['status'] == 'unconfirmed'
    assert result['entries'][1]['targets'][0]['status'] == 'superseded'
    record, = engine.session.cache['fullclone_original_owners'].values()
    assert record['owner'] == 1 and record['last_owner'] == 3 and record['prior_owner'] == 2


def _team_session(dll):
    world = World()
    world.selected = []
    for a in range(1,29):
        for b in range(1,29):
            for flag in range(10):
                world.alliances[a,b,flag] = int(a == b or (flag < 6 and (a-1)//2 == (b-1)//2))
    trainer, engine = host(world,dll)
    engine.session.identity = NS(pid=123, created=456)
    return world, trainer, engine


def test_diplomacy_undo_restores_prior_template_and_keeps_live_control(dll):
    world, trainer, engine = _team_session(dll)
    initial = world.run(dll,19,target=0)['matrix']
    trainer.fullclone_team(1,player=0)
    first_matrix = world.run(dll,19,target=0)['matrix']
    trainer.fullclone_team(2,player=0)
    newest, first = snapshot(engine.session.cache)
    world.alliances[1,2,6] = 1
    world.alliances[2,1,7] = 1
    assert first['targets'][0]['status'] == 'newer'
    result = undo(engine,newest['id'])
    assert result['team'] == dict(player=0,template=1,context='123:456:3')
    assert world.selected == []
    live = world.run(dll,19,target=0)['matrix']
    assert all(live[i] == first_matrix[i] for i in range(560) if i % 10 not in (6,7))
    assert world.alliances[1,2,6] == world.alliances[2,1,7] == 1
    trainer.fullclone_restore_all_teams()
    live = world.run(dll,19,target=0)['matrix']
    assert all(live[i] == initial[i] for i in range(560) if i % 10 not in (6,7))
    assert snapshot(engine.session.cache)[-1]['targets'][0]['status'] == 'superseded'


def test_diplomacy_refuses_external_change_before_setting_flags(dll):
    world, trainer, engine = _team_session(dll)
    trainer.fullclone_team(1,player=0)
    entry, = snapshot(engine.session.cache)
    idx = next(iter(engine.session.cache['fullclone_operation_history'][0]['targets'][0]['changes']))
    peer, flag = divmod(idx,20)
    key = (1,peer+1,flag) if flag < 10 else (peer+1,1,flag-10)
    world.alliances[key] ^= 1
    engine.actions.clear()
    result = undo(engine,entry['id'])
    assert result['undone'] == 0 and result['entries'][0]['targets'][0]['status'] == 'relations_changed'
    assert engine.actions == [(19,0)]


def test_history_is_bounded_and_new_map_rejects_old_id(ownership):
    world, trainer, engine, _ = ownership
    world.selected = [1001]
    trainer.fullclone_give_owner(1)
    first, = snapshot(engine.session.cache)
    for i in range(HISTORY_LIMIT):
        trainer.fullclone_give_owner(2 if i % 2 == 0 else 1)
    entries = snapshot(engine.session.cache)
    assert len(entries) == HISTORY_LIMIT and all(row['id'] != first['id'] for row in entries)
    engine.pid = 123
    engine.memory_factory = lambda pid: nullcontext(None)
    engine.session.prepare = lambda memory: None
    api = NS(app=NS(elephant_trainer=lambda: trainer),
             _run_action=lambda fn, name: fn(), _mark_units_changed=lambda: None)
    assert operation_history(api)['entries'] == entries
    def switch_map(memory):
        engine.session.epoch += 1
        engine.session.cache.clear()
    engine.session.prepare = switch_map
    previous_owner = world.units[1001]['owner']
    with pytest.raises(ValueError,match='记录已过期'):
        undo_operation(api,entries[0]['id'])
    assert world.units[1001]['owner'] == previous_owner
    assert operation_history(api) == dict(success=True,available=True,entries=[])
