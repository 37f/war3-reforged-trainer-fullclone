"""Exercise paired exchanges and guarded restoration without a game process."""
from dataclasses import dataclass

import pytest

from war3_services.hero_skill_swap import Hero, _exchange, _restore


def code(value):
    return int.from_bytes(value.encode('ascii'), 'big')


@dataclass(frozen=True)
class Ref:
    rawcode: int


class Game:
    count = 5

    def __init__(self):
        self.a = Hero(Ref(code('Hpal')), 1)
        self.b = Hero(Ref(code('Hamg')), 2)
        self.selection_set = (self.a, self.b)
        self.records = {}
        self.configs = {
            self.a: [(code(id_), code(id_)) for id_ in ('AHhb','AHds','AHad','AHre','ZZa1')],
            self.b: [(code(id_), code(id_)) for id_ in ('AHbz','AHwe','AHab','AHmt')] + [(0, 0)],
        }
        self.levels = {
            self.a: {code('AHhb'): 3, code('AHad'): 1, code('ZZa1'): 2},
            self.b: {code('AHbz'): 1, code('AHmt'): 1},
        }
        self.dormant = set()
        self.fail = set()
        self.writes = []

    def selection(self, expected=None):
        if expected and len(self.selection_set) != expected:
            raise ValueError('exactly two')
        return self.selection_set

    def config(self, hero):
        return tuple(self.configs[hero])

    def observations(self, heroes, codes):
        return {hero: {code_: (self.levels[hero].get(code_, 0),
                                bool(self.levels[hero].get(code_, 0) or (hero, code_) in self.dormant))
                       for code_ in codes}
                for hero in heroes}

    def set_level(self, hero, code_, prior, target):
        self.writes.append((hero, code_, prior, target))
        assert self.levels[hero].get(code_, 0) == prior
        if target:
            self.levels[hero][code_] = target
        else:
            self.levels[hero].pop(code_, None)
        if (hero, code_, target) in self.fail:
            self.fail.remove((hero, code_, target))
            raise RuntimeError('simulated failure after mutation')

    def write_config(self, hero, source, desired, slots, *, recovery=False):
        for i in slots:
            assert self.configs[hero][i] in (source[i], desired[i]) if recovery else self.configs[hero][i] == source[i]
            self.configs[hero][i] = desired[i]


def test_matching_slot_exchanges_ids_and_donor_levels():
    game = Game()
    first, second = game.config(game.a), game.config(game.b)
    assert _exchange(game, 0) == 2
    assert game.config(game.a) == second[:1] + first[1:]
    assert game.config(game.b) == first[:1] + second[1:]
    assert game.levels[game.a] == {code('AHbz'):1, code('AHad'):1, code('ZZa1'):2}
    assert game.levels[game.b] == {code('AHhb'):3, code('AHmt'):1}


def test_all_swaps_fifth_slot_and_keeps_unlearned_skills_unlearned():
    game = Game()
    first, second = game.config(game.a), game.config(game.b)
    levels = tuple(game.levels[hero].copy() for hero in game.selection_set)
    assert _exchange(game, None) == 10
    assert game.config(game.a) == second and game.config(game.b) == first
    assert game.levels[game.a] == levels[1] and game.levels[game.b] == levels[0]
    assert _restore(game) == dict(restored=2, pending=0, issues=[])
    assert game.config(game.a) == first and game.config(game.b) == second
    assert tuple(game.levels[hero] for hero in game.selection_set) == levels


def test_restore_selected_heroes_only_keeps_first_rank_and_other_slots():
    game = Game()
    original = game.config(game.a)
    assert _exchange(game, 0) == 2
    game.levels[game.a][code('AHbz')] = 2
    assert _exchange(game, 0) == 2
    game.levels[game.a][code('AHad')] = 2
    game.selection_set = (game.a,)
    assert _restore(game) == dict(restored=1, pending=1, issues=[])
    assert game.config(game.a) == original
    assert game.levels[game.a][code('AHhb')] == 3 and game.levels[game.a][code('AHad')] == 2
    game.selection_set = (game.b,)
    assert _restore(game) == dict(restored=1, pending=0, issues=[])


def test_unsafe_duplicate_and_dormant_ability_reject_before_any_write():
    game = Game()
    game.configs[game.a][1] = (code('AHbz'), code('AHbz'))
    with pytest.raises(ValueError, match='重复技能'):
        _exchange(game, 0)
    assert not game.writes and not game.records
    game = Game()
    game.dormant.add((game.a, code('AHbz')))
    with pytest.raises(ValueError, match='未确认的实例'):
        _exchange(game, 0)
    assert not game.writes and not game.records


def test_failure_after_second_hero_write_restores_both_sides():
    game = Game()
    original = {hero:(game.config(hero),game.levels[hero].copy()) for hero in game.selection_set}
    game.fail.add((game.b, code('AHhb'), 3))
    with pytest.raises(RuntimeError, match='已回滚'):
        _exchange(game, 0)
    assert {hero:(game.config(hero),game.levels[hero]) for hero in game.selection_set} == original
    assert not game.records


def test_recovery_record_survives_an_unconfirmed_rollback():
    game = Game()
    game.fail.update({(game.b, code('AHhb'), 3), (game.b, code('AHhb'), 0)})
    with pytest.raises(RuntimeError, match='已保留还原记录'):
        _exchange(game, 0)
    assert set(game.records) == {game.b.ref}
    assert _restore(game) == dict(restored=1, pending=0, issues=[])
    assert game.levels[game.b] == {code('AHbz'):1, code('AHmt'):1}


def test_restore_leaves_externally_edited_slots_and_reports_pending():
    game = Game()
    _exchange(game, 0)
    game.configs[game.b][0] = (code('ZZa2'), code('ZZa2'))
    result = _restore(game)
    assert result['restored'] == 1 and result['pending'] == 1
    assert '技能栏已被其他操作更改' in result['issues'][0]
    assert game.config(game.b)[0][0] == code('ZZa2')


def test_restore_flags_an_unconfirmed_orphan_after_incomplete_rollback():
    game = Game()
    game.fail.update({(game.b, code('AHhb'), 3), (game.b, code('AHhb'), 0)})
    with pytest.raises(RuntimeError, match='已保留还原记录'):
        _exchange(game, 0)
    game.levels[game.b][code('AHhb')] = 3
    result = _restore(game)
    assert result['restored'] == 0 and result['pending'] == 1
    assert '存留技能' in result['issues'][0]
    assert game.levels[game.b][code('AHhb')] == 3


def test_candidate_exchange_and_restore_work_after_clearing_game_selection(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from war3_services import hero_skill_swap as service

    game = Game()
    game.candidates = {}
    game.check = game.config
    monkeypatch.setattr(service, '_selected_heroes', lambda host, **kwargs: nullcontext(game))
    owner = [1]
    host = SimpleNamespace(fullclone_owner=lambda: dict(handle=game.selection_set[0].handle,
                           rawcode=game.selection_set[0].ref.rawcode, a=owner[0]))
    first, second = game.config(game.a), game.config(game.b)
    game.selection_set = (game.a,)
    service.capture_candidate(host, 0)
    with pytest.raises(ValueError, match='另一个候选位'):
        service.capture_candidate(host, 1)
    with pytest.raises(ValueError, match='两名不同'):
        service.exchange_hero_skills(host, 0, candidates_only=True)
    game.selection_set = (game.b,)
    owner[0] = 27
    service.capture_candidate(host, 1)
    assert [candidate[1]['player'] for candidate in game.candidates.values()] == [2, 28]
    game.selection_set = ()
    assert service.exchange_hero_skills(host, 0, candidates_only=True) == 2
    assert game.config(game.a)[0] == second[0] and game.config(game.b)[0] == first[0]
    service.clear_candidates(host)
    game.selection_set = (game.a, game.b)
    with pytest.raises(ValueError, match='两名不同'):
        service.exchange_hero_skills(host, 0, candidates_only=True)
    assert service.restore_hero_skills(host) == dict(restored=2, pending=0, issues=[])
    assert game.config(game.a) == first and game.config(game.b) == second


def test_skill_transaction_opens_writable_scope_before_any_operation(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from war3_services import hero_skill_swap as service

    pid = 789
    accesses = []
    read = SimpleNamespace()
    session = SimpleNamespace(lock=nullcontext(), prepare=lambda memory: (object(), None, None))

    def open_memory(requested, *, write):
        assert requested == pid
        accesses.append(write)
        if write:
            raise PermissionError('cannot open writable scope')
        return nullcontext(read)

    engine = SimpleNamespace(pid=pid, session=session, memory_factory=open_memory)
    host = SimpleNamespace(_engine_instance_24268=lambda: engine)
    monkeypatch.setattr('war3_backend.uses_indexed_backend', lambda host: True)
    monkeypatch.setattr(service, 'session_scope', lambda session: nullcontext())
    monkeypatch.setattr(service, 'SelectedHeroes', lambda host, engine, memory, registry: memory)

    with service._selected_heroes(host) as scope:
        assert scope is read
    with pytest.raises(PermissionError, match='writable scope'):
        service.exchange_hero_skills(host, 1)
    with pytest.raises(PermissionError, match='writable scope'):
        service.restore_hero_skills(host)
    assert accesses == [False, True, True]
