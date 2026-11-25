"""Exchange configured hero skills with the existing selected-unit ability API."""
from contextlib import contextmanager
from dataclasses import dataclass

from war3_contracts import format_rawcode
from war3_game_session import ObjectAddress, session_scope


_RECORDS = 'fullclone_original_hero_skills'
_CANDIDATES = 'fullclone_hero_candidates'


@dataclass(frozen=True)
class Hero:
    ref: object
    handle: int


@dataclass(frozen=True)
class Plan:
    hero: Hero
    before: tuple
    after: tuple
    levels: dict
    target_levels: dict
    slots: tuple


class SelectedHeroes:
    def __init__(self, host, engine, memory, registry):
        self.host, self.engine, self.memory, self.registry = host, engine, memory, registry
        self.session = engine.session
        self.identity, self.epoch = self.session.identity, self.session.epoch
        self.records = self.session.cache.setdefault(_RECORDS, {})
        self.candidates = self.session.cache.setdefault(_CANDIDATES, {})
        self.layout = self.session.profile.section('layouts')
        self.count = host.HERO_SKILL_SLOT_COUNT

    def selection(self, expected=None):
        candidates = tuple(candidate for candidate, _ in self.host._selected_candidates_snapshot(self.memory))
        if expected is not None and len(candidates) != expected:
            raise ValueError('请在游戏里只选中一名英雄' if expected == 1 else '请在游戏里同时选中两名英雄')
        refs = tuple(self.session.bind_unit(self.memory, self.registry, ObjectAddress(candidate.unit_address))
                     for candidate in candidates)
        if len(set(refs)) != len(refs) or any(
                (ref.handle.value, ref.rawcode) != (candidate.handle, candidate.unit_type_id)
                for ref, candidate in zip(refs, candidates, strict=True)):
            raise ValueError('选中单位的身份已变化，请重新选择')
        if not refs:
            return ()
        bindings = self.engine.bind_unit_refs(refs, strict_selection=True)
        if tuple(ref for _, ref in bindings) != refs:
            raise ValueError('选中单位的原生身份无法核对')
        return tuple(Hero(ref, handle.value) for handle, ref in bindings)

    def check(self, hero):
        self.registry, _, _ = self.session.prepare(self.memory)
        if (self.session.identity, self.session.epoch) != (self.identity, self.epoch):
            raise ValueError('地图或连接已变化，旧技能记录已失效')
        address = self.session.resolve(self.memory, self.registry, hero.ref)
        return address

    def addresses(self, hero):
        address = self.check(hero)
        _, owner = self.registry.resolve_unit(self.memory, address)
        component = self.host._selected_components(self.memory, owner).get('hero')
        if not component:
            raise ValueError('请选择具有英雄技能栏的单位')
        _, data = component
        if self.memory.read_u64(data + self.layout['ability']['unit_owner']) != address:
            raise ValueError('英雄技能组件的身份已变化')
        layout = self.layout['hero']
        return tuple((data + layout['skill_name_native'] + i * 4,
                      data + layout['skill_cache_native'] + i * 4) for i in range(self.count))

    def config(self, hero):
        slots = tuple((self.memory.read_u32(name), self.memory.read_u32(cache))
                      for name, cache in self.addresses(hero))
        if any(code and len(format_rawcode(code)) != 4 for code, _ in slots):
            raise ValueError('英雄技能栏包含无法核对的技能 ID')
        return slots

    def observations(self, heroes, codes):
        by_hero = {hero: {} for hero in heroes}
        for hero in heroes:
            self.check(hero)
            for code in sorted(codes):
                row = self.engine.hero_skill_bound(hero.ref, hero.handle, code)
                by_hero[hero][code] = (row['after'], bool(row['after_handle']))
        return by_hero

    def set_level(self, hero, code, prior, target):
        self.check(hero)
        action = 2 if not target else 3 if prior else 1
        self.engine.hero_skill_bound(hero.ref, hero.handle, code, action, prior, target)
        self.check(hero)

    def write_config(self, hero, source, desired, slots, *, recovery=False):
        addresses = self.addresses(hero)
        self.session.require_write()
        for index in slots:
            name, cache = addresses[index]
            allowed = (source[index][0], desired[index][0]) if recovery else (source[index][0],)
            if self.memory.read_u32(name) not in allowed:
                raise ValueError('英雄技能栏在写入期间发生变化')
            for address, value in zip((name, cache), desired[index]):
                if self.memory.read_u32(address) != value:
                    self.memory.write_u32(address, value)
        result = self.config(hero)
        if any(result[index] != desired[index] for index in slots):
            raise ValueError('英雄技能栏写入后读回不一致')


@contextmanager
def _selected_heroes(host, *, write=False):
    from war3_backend import uses_indexed_backend

    if not uses_indexed_backend(host):
        raise ValueError('英雄技能互换需要当前版本的 3.0 读取接口')
    engine = host._engine_instance_24268()
    session = engine.session
    # A read-only process handle cannot commit the two skill-slot words.
    # Open the writable handle before changing skill levels so a denied open
    # cannot leave a partially applied exchange.
    with session.lock, engine.memory_factory(engine.pid, write=write) as memory:
        registry, _, _ = session.prepare(memory)
        with session_scope(session):
            yield SelectedHeroes(host, engine, memory, registry)


def _plan(hero, config, live, desired):
    after = list(config)
    touched = []
    for index, (slot, level) in desired.items():
        code = slot[0]
        old_code = config[index][0]
        old_level = live[old_code][0] if old_code else 0
        if (slot, level) != (config[index], old_level):
            after[index] = slot
            touched.append(index)
        if code and not 0 <= level <= 100000:
            raise ValueError('英雄技能等级超出可验证范围')
    codes = [code for code, _ in after if code]
    if len(codes) != len(set(codes)):
        raise ValueError('交换后出现重复技能，请改用交换全部技能或换一名英雄')
    affected = ({config[i][0] for i in touched} | {after[i][0] for i in touched}) - {0}
    configured = {slot[0] for slot in config}
    target = {after[i][0]: level for i, (_, level) in desired.items() if after[i][0] in affected}
    levels = {}
    for code in affected:
        rank, exists = live[code]
        if rank < 0 or (not rank and exists) or (code not in configured and (rank or exists)):
            raise ValueError(f'技能 {format_rawcode(code)} 存在未确认的实例，已停止本次操作')
        levels[code] = rank
        target.setdefault(code, 0)
    return Plan(hero, config, tuple(after), levels, target, tuple(touched))


def _set_levels(game, hero, before, after):
    changes = [(code, before[code], level) for code, level in sorted(after.items()) if before[code] != level]
    for code, prior, level in sorted(changes, key=lambda row: row[2] > 0):
        game.set_level(hero, code, prior, level)


def _apply(game, plans):
    attempted = []
    try:
        for plan in plans:
            if game.config(plan.hero) != plan.before:
                raise ValueError('已记录的英雄技能栏发生变化')
            current = game.observations((plan.hero,), plan.levels)[plan.hero]
            if any(current[code][0] != level or (not level and current[code][1])
                   for code, level in plan.levels.items()):
                raise ValueError('英雄技能等级已变化，请重新操作')
            attempted.append(plan)
            _set_levels(game, plan.hero, plan.levels, plan.target_levels)
        for plan in plans:
            game.write_config(plan.hero, plan.before, plan.after, plan.slots)
            observed = game.observations((plan.hero,), plan.target_levels)[plan.hero]
            if any(observed[code][0] != level or (not level and observed[code][1])
                   for code, level in plan.target_levels.items()):
                raise ValueError('技能等级或未学习状态核对失败')
    except Exception as exc:
        failures = []
        for plan in reversed(attempted):
            try:
                current = game.observations((plan.hero,), plan.levels)[plan.hero]
                if any(not level and exists for level, exists in current.values()):
                    raise ValueError('回滚时发现未确认的技能实例')
                _set_levels(game, plan.hero, {code: state[0] for code, state in current.items()}, plan.levels)
                game.write_config(plan.hero, plan.after, plan.before, plan.slots, recovery=True)
                observed = game.observations((plan.hero,), plan.levels)[plan.hero]
                if any(observed[code][0] != level or (not level and observed[code][1])
                       for code, level in plan.levels.items()):
                    raise ValueError('回滚后技能等级无法核对')
            except Exception:
                failures.append(format_rawcode(plan.hero.ref.rawcode))
                _remember(game, plan, uncertain=True)
        if failures:
            raise RuntimeError(f'技能操作未完成，回滚未确认（{", ".join(failures)}），已保留还原记录：{exc}') from exc
        raise RuntimeError(f'技能操作未完成，已回滚：{exc}') from exc


def _remember(game, plan, *, uncertain=False):
    _, records = game.records.setdefault(plan.hero.ref, (plan.hero, {}))
    for index in plan.slots:
        before, after = plan.before[index], plan.after[index]
        baseline, _ = records.get(index, ((before, plan.levels.get(before[0], 0)), ()))
        records[index] = (baseline, (before[0], after[0]) if uncertain else (after[0],))


def _exchange(game, slot, heroes=None):
    if heroes is None:
        heroes = game.selection(expected=2)
    configs = {hero: game.config(hero) for hero in heroes}
    slots = range(game.count) if slot is None else (slot,)
    codes = {configs[hero][index][0] for hero in heroes for index in slots} - {0}
    live = game.observations(heroes, codes)
    plans = []
    for hero, donor in (heroes, heroes[::-1]):
        desired = {}
        for index in slots:
            code = configs[donor][index][0]
            config = configs[hero][index] if configs[hero][index][0] == code else (code, code)
            desired[index] = config, live[donor][code][0] if code else 0
        plan = _plan(hero, configs[hero], live[hero], desired)
        if plan.slots:
            plans.append(plan)
    _apply(game, plans)
    for plan in plans:
        _remember(game, plan)
    return sum(len(plan.slots) for plan in plans)


def _restore(game, heroes=None):
    if not game.records:
        return dict(restored=0, pending=0, issues=[])
    restored, issues = 0, []
    if heroes is None:
        heroes = game.selection()
    for hero in heroes:
        entry = game.records.get(hero.ref)
        if not entry:
            continue
        _, records = entry
        try:
            config = game.config(hero)
            if any(config[i][0] not in expected for i, (_, expected) in records.items()):
                raise ValueError('技能栏已被其他操作更改')
            known = {code for _, expected in records.values() for code in expected} - {0}
            codes = known | ({saved[0][0] for saved, _ in records.values()} - {0})
            live = game.observations((hero,), codes)[hero]
            configured = {slot[0] for slot in config}
            if any(live[code][0] or live[code][1] for code in known - configured):
                raise ValueError('检测到未归入技能栏的存留技能，已保留还原记录')
            plan = _plan(hero, config, live, {i: saved for i, (saved, _) in records.items()})
            if plan.slots:
                _apply(game, [plan])
            game.records.pop(hero.ref)
            restored += 1
        except (OSError, RuntimeError, ValueError) as exc:
            issues.append(f'{format_rawcode(hero.ref.rawcode)}：{exc}')
    return dict(restored=restored, pending=len(game.records), issues=issues)


def exchange_hero_skills(host, slot=None, *, candidates_only=False):
    if slot is not None and (type(slot) is not int or slot not in range(4)):
        raise ValueError('英雄技能栏位必须为 1～4')
    with _selected_heroes(host, write=True) as game:
        if not candidates_only:
            return _exchange(game, slot)
        if len(game.candidates) != 2:
            raise ValueError('请先加入两名不同的候选英雄')
        return _exchange(game, slot, tuple(game.candidates[i][0] for i in range(2)))


def restore_hero_skills(host):
    with _selected_heroes(host, write=True) as game:
        return _restore(game, tuple(hero for hero, _ in game.records.values()))


def list_candidates(session):
    candidates = session.cache.get(_CANDIDATES, {})
    return [candidates[i][1] if i in candidates else None for i in range(2)]


def clear_candidates(host):
    with _selected_heroes(host) as game:
        game.candidates.clear()


def capture_candidate(host, index):
    from war3_id_catalog import search_id_entries

    if index not in (0, 1):
        raise ValueError('候选英雄栏位无效')
    with _selected_heroes(host) as game:
        hero, = game.selection(expected=1)
        game.config(hero)  # Reject non-heroes before replacing any saved candidate.
        other = game.candidates.get(1 - index)
        if other and other[0].ref == hero.ref:
            raise ValueError('这名英雄已加入另一个候选位')
        row = host.fullclone_owner()
        if not row or (row['handle'], row['rawcode']) != (hero.handle, hero.ref.rawcode):
            raise ValueError('选中的英雄已变化，请重新加入候选')
        game.check(hero)
        rawcode = format_rawcode(hero.ref.rawcode)
        entry = next((e for e in search_id_entries('unit', rawcode) if e.rawcode == rawcode), None)
        game.candidates[index] = (hero, dict(code=rawcode, player=row['a'] + 1,
                                           nameZh=entry.name_zh if entry else '',
                                           nameEn=entry.name_en if entry else ''))
