"""Exercise the real combat tick with fake game handlers and no game process."""
import ctypes
import struct
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from test_fullclone_migration import B, F, I, U, V, dll
from war3_fullclone_ai_protocol import (
    DESTRUCTIBLES, DESTRUCTIBLE_HANDLERS, ITEM_HANDLERS, NEUTRAL_BUILDINGS, NEUTRAL_CREATURES,
    PICKUP, SIGNATURES, WORLD_COMMON, build_work, decode_work,
)
from war3_fullclone_application import FullCloneApplication
from war3_selection_protocol import SIGNATURES as SELECTION


class AIWorld:
    def __init__(self):
        self.owner = 1
        self.controller = 0
        self.commands = []
        self.nearby_queries = 0
        self.entries = {}
        self.groups = {}
        self.units = {}
        self.callbacks = []
        self.reassign_player = False
        self.player_states = {1: 250, 2: 125, 4: 20, 5: 12, 6: 100}
        self.placements = []
        self.wood_accepts = False
        self.research_accepts = set()
        self.train_accepts = set()
        self.tech_levels = {}
        self.tech_limits = {}
        self.computers = set()
        self.rivals = {2}
        self.starts = {}
        self.reject_orders = set()
        self.widgets = {}
        self.locations = {}
        signatures = dict(SELECTION + SIGNATURES + WORLD_COMMON + ITEM_HANDLERS + DESTRUCTIBLE_HANDLERS)

        def bind(name, result, args, function):
            callback = ctypes.CFUNCTYPE(result, *args)(function)
            self.callbacks.append(callback)
            self.entries[name] = SimpleNamespace(name=name, signature=signatures[name],
                                                 handler=ctypes.cast(callback, ctypes.c_void_p).value)

        def create_group():
            group = len(self.groups) + 100
            self.groups[group] = []
            return group

        def get(unit, key, default=0):
            return self.units[unit].get(key, default)

        def invulnerable(target):
            remaining = target.get('checks_before_invulnerable')
            if remaining is not None:
                if remaining > 0:
                    target['checks_before_invulnerable'] = remaining - 1
                else:
                    return 1
            return target.get('invulnerable', 0)

        def real_bits(value):
            return struct.unpack('<I', struct.pack('<f', value))[0]

        def real(unit, key, default=0.0):
            return real_bits(get(unit, key, default))

        def enum_nearby(group, x, y, radius, _filter, limit):
            self.nearby_queries += 1
            found = [u for u in self.units if
                     (get(u, 'x') - x[0]) ** 2 + (get(u, 'y') - y[0]) ** 2 <= radius[0] ** 2]
            self.groups[group].extend(found[:limit])

        def order(unit, command, target):
            if command in self.reject_orders:
                return 0
            self.commands.append((unit, command, target))
            self.units[unit]['order'] = command
            if self.reassign_player:
                self.owner = 2
            return 1

        bind('GetLocalPlayer', U, (), lambda: self.owner)
        bind('CreateGroup', U, (), create_group)
        bind('GroupEnumUnitsSelected', V, (U, U, U), lambda *args: None)
        bind('FirstOfGroup', U, (U,), lambda g: next(iter(self.groups[g]), 0))
        bind('GroupRemoveUnit', B, (U, U), lambda g, u: (self.groups[g].remove(u), 1)[1])
        bind('DestroyGroup', V, (U,), lambda g: self.groups.pop(g))
        bind('GetUnitTypeId', I, (U,), lambda u: self.units[u].get('code', 1) if u in self.units else 0)
        bind('GetHeroLevel', I, (U,), lambda u: 1)
        bind('GetPlayerController', U, (U,), lambda p: self.controller if p == self.owner else int(p in self.computers))
        bind('ConvertMapControl', U, (I,), lambda p: p)
        bind('GetPlayerSlotState', U, (U,), lambda p: 1)
        bind('ConvertPlayerSlotState', U, (I,), lambda p: p)
        # Include the whole list, to exercise the independent owner check.
        bind('GroupEnumUnitsOfPlayer', V, (U, U, U), lambda g, p, f: self.groups[g].extend(self.units))
        bind('GroupEnumUnitsInRangeCounted', V, (U, F, F, F, U, I), enum_nearby)
        bind('GroupClear', V, (U,), lambda g: self.groups[g].clear())
        bind('GetOwningPlayer', U, (U,), lambda u: get(u, 'owner'))
        bind('GetUnitCurrentOrder', I, (U,), lambda u: get(u, 'order'))
        bind('GetWidgetLife', ctypes.c_uint32, (U,), lambda u: real_bits(self.widgets[u].get('life', 100.0)) if u in self.widgets else real(u, 'life', 400.0))
        bind('IsUnitHidden', B, (U,), lambda u: get(u, 'hidden'))
        bind('IsUnitPaused', B, (U,), lambda u: get(u, 'paused'))
        bind('IsUnitType', B, (U, U), lambda u, t: t in get(u, 'types', (6,)))
        bind('ConvertUnitType', U, (I,), lambda t: t)
        bind('GetUnitX', ctypes.c_uint32, (U,), lambda u: real(u, 'x'))
        bind('GetUnitY', ctypes.c_uint32, (U,), lambda u: real(u, 'y'))
        bind('IsUnitEnemy', B, (U, U), lambda u, p: get(u, 'owner') in (2, 25))
        bind('IsUnitVisible', B, (U, U), lambda u, p: get(u, 'visible', 1))
        bind('IsUnitInvisible', B, (U, U), lambda u, p: get(u, 'invisible'))
        bind('IsUnitDetected', B, (U, U), lambda u, p: get(u, 'detected'))
        bind('BlzIsUnitInvulnerable', B, (U,), lambda u: invulnerable(self.units[u]))
        bind('IssueTargetOrderById', B, (U, I, U), order)
        bind('GetResourceAmount', I, (U,), lambda u: get(u, 'resource'))
        bind('GetPlayerId', I, (U,), lambda p: p - 1)
        bind('GetPlayerNeutralPassive', I, (), lambda: 27)
        bind('GetPlayerState', I, (U, U), lambda p, state: self.player_states.get(state, 0))
        bind('ConvertPlayerState', U, (I,), lambda state: state)
        bind('ConvertPathingType', U, (I,), lambda pathing: pathing)
        bind('IsTerrainPathable', B, (F, F, U), lambda x, y, pathing: 0)
        bind('IsPointBlighted', B, (F, F), lambda x, y: 1)

        def build(unit, code, x, y):
            self.placements.append((unit, code, x[0], y[0]))
            return 1

        bind('IssueBuildOrderById', B, (U, I, F, F), build)
        bind('GetUnitAbilityLevel', I, (U, I), lambda u, code: get(u, 'spells', {}).get(code, 0))
        bind('BlzGetUnitAbilityCooldownRemaining', ctypes.c_uint32, (U, I), lambda u, code: real(u, 'cooldown'))
        bind('BlzGetUnitAbilityManaCost', I, (U, I, I), lambda u, code, level: 75)
        bind('GetUnitState', ctypes.c_uint32, (U, U), lambda u, state: real(u, 'mana'))
        bind('ConvertUnitState', U, (I,), lambda state: state)
        bind('BlzGetUnitAbility', U, (U, I), lambda u, code: u + 10000)
        bind('BlzGetAbilityRealLevelField', ctypes.c_uint32, (U, U, I), lambda a, f, level: 0x44160000)
        bind('ConvertAbilityRealLevelField', U, (I,), lambda field: field)
        bind('BlzGetUnitMaxHP', I, (U,), lambda u: get(u, 'max_life', 500))
        bind('IssueImmediateOrderById', B, (U, I), lambda u, cmd: order(u, cmd, 0)
             if cmd in self.research_accepts or cmd in self.train_accepts or (cmd==852022 and self.wood_accepts) else 0)
        bind('BlzGetUnitOrderCount', I, (U,), lambda u: get(u, 'queued'))
        bind('GetPlayerNeutralAggressive', I, (), lambda: 24)
        bind('GetPlayerTechCount', I, (U, I, I), lambda p, cmd, specific: self.tech_levels.get(cmd, 0))
        bind('GetPlayerTechMaxAllowed', I, (U, I), lambda p, cmd: self.tech_limits.get(cmd, -1))
        bind('IssuePointOrderById', B, (U, I, F, F), lambda u, cmd, x, y: order(u, cmd, (x[0], y[0])))
        bind('Player', U, (I,), lambda slot: slot + 1)
        bind('IsPlayerEnemy', B, (U, U), lambda own, target: target in self.rivals)
        bind('GetPlayerStartLocation', I, (U,), lambda player: player - 1 if player - 1 in self.starts else -1)
        bind('GetStartLocationX', ctypes.c_uint32, (I,), lambda i: real_bits(self.starts[i][0]))
        bind('GetStartLocationY', ctypes.c_uint32, (I,), lambda i: real_bits(self.starts[i][1]))
        bind('GetUnitLevel', I, (U,), lambda u: get(u, 'level', 1))
        def create_location(x, y):
            handle = 9000 + len(self.locations)
            self.locations[handle] = (x[0], y[0])
            return handle

        bind('Location', U, (F, F), create_location)
        bind('MoveLocation', V, (U, F, F), lambda h, x, y: self.locations.__setitem__(h, (x[0], y[0])))
        bind('IsLocationVisibleToPlayer', B, (U, U), lambda h, p: self.locations[h][0] >= 0 and p == self.owner)
        bind('RemoveLocation', V, (U,), lambda h: self.locations.pop(h))
        bind('UnitInventorySize', I, (U,), lambda u: len(get(u, 'inventory', ())))
        bind('UnitItemInSlot', U, (U, I), lambda u, slot: get(u, 'inventory')[slot])
        bind('ConvertItemBooleanField', U, (I,), lambda field: field)
        bind('BlzGetItemBooleanField', B, (U, U), lambda h, f:
             f == int.from_bytes(b'ipow', 'big') and self.widgets[h].get('instant', False))
        bind('ConvertUnitIntegerField', U, (I,), lambda field: field)
        bind('BlzGetUnitIntegerField', I, (U, U), lambda h, f:
             get(h, 'primary') if f == int.from_bytes(b'upra', 'big') else 0)
        bind('BlzGetItemAbilityByIndex', U, (U, I), lambda h, i:
             h * 32 + i if i < len(self.widgets[h].get('attributes', ())) else 0)
        bind('ConvertAbilityIntegerLevelField', U, (I,), lambda field: field)
        bind('BlzGetAbilityIntegerLevelField', I, (U, U, I), lambda ability, field, level:
             self.widgets[ability // 32]['attributes'][ability % 32].get(field.to_bytes(4, 'big'), 0))
        bind('IsItemOwned', B, (U,), lambda h: self.widgets[h].get('owned', 0))
        bind('IsItemVisible', B, (U,), lambda h: self.widgets[h].get('visible', 1))
        for kind in ('Item', 'Destructable'):
            bind(f'Get{kind}TypeId', I, (U,), lambda h, kind=kind:
                 self.widgets[h].get('code', 1) if self.widgets[h]['kind'] == kind else 0)
            bind(f'Get{kind}X', ctypes.c_uint32, (U,), lambda h: real_bits(self.widgets[h]['x']))
            bind(f'Get{kind}Y', ctypes.c_uint32, (U,), lambda h: real_bits(self.widgets[h].get('y', 0)))
            bind(f'Is{kind}Invulnerable', B, (U,), lambda h: invulnerable(self.widgets[h]))

    def world_registry(self, image):
        addr = ctypes.addressof
        root = ctypes.create_string_buffer(128)
        table = ctypes.create_string_buffer(16 * (len(self.widgets) + 1))
        base = ctypes.create_string_buffer(8)
        struct.pack_into('<Q', base, 0, addr(root))
        struct.pack_into('<Q', root, 24, addr(table))
        struct.pack_into('<I', root, 48, len(self.widgets) + 1)
        keep = [root, table, base]
        handles = {}
        for index, (handle, widget) in enumerate(self.widgets.items(), 1):
            owner = ctypes.create_string_buffer(152)
            obj = ctypes.create_string_buffer(128)
            full = (55 << 32) | index
            tag = widget.get('tag', b'lga+meti' if widget['kind'] == 'Item' else b'lga+d3w+')
            struct.pack_into('<I4xQ', table, index * 16, 0xfffffffe, addr(owner))
            struct.pack_into('<8sQ', owner, 24, tag, full)
            struct.pack_into('<Q', owner, 144, addr(obj))
            struct.pack_into('<Q', obj, 24, full)
            struct.pack_into('<I', obj, 112, widget.get('code', 1))
            handles[addr(obj)] = handle
            keep.extend((owner, obj))
        callback = ctypes.CFUNCTYPE(U, U, B)(lambda obj, _create: handles[obj])
        keep.append(callback)
        self.world_buffers = keep
        image.FCFixtureRegistryRootZero()
        return dict(world_base=addr(base), converter=ctypes.cast(callback, ctypes.c_void_p).value)

    def run(self, image, owner=1, cursor=0, *, inspect_world=False, **options):
        if owner and (not options.get('inspect') or inspect_world) and options.get('features', 0) & (PICKUP | DESTRUCTIBLES):
            options.update(self.world_registry(image))
            if options.get('features', 0) & DESTRUCTIBLES:
                options.setdefault('selectable_destructibles', tuple(sorted({
                    widget.get('code', 1) for widget in self.widgets.values()
                    if widget['kind'] == 'Destructable'
                })))
        work = build_work(self.entries, 0x20000, owner=owner, cursor=cursor, **options)
        buf = ctypes.create_string_buffer(work, len(work))
        count = image.FCFixtureRun(buf, 6)
        assert not self.groups and not self.locations
        return decode_work(buf.raw, count)


def test_only_idle_owned_combat_units_attack_eligible_visible_enemy(dll):
    world = AIWorld()
    world.units = {
        101: dict(owner=1),
        102: dict(owner=1, order=851986),
        103: dict(owner=1, types=(2, 6)),
        104: dict(owner=1, types=(16, 6)),
        105: dict(owner=1, paused=1),
        106: dict(owner=1, life=0.0),
        107: dict(owner=1, hidden=1),
        108: dict(owner=1, types=()),
        109: dict(owner=3),
        201: dict(owner=2, x=80.0, invisible=1),
        202: dict(owner=2, x=100.0, visible=0),
        203: dict(owner=2, x=110.0, invulnerable=1),
        204: dict(owner=2, x=120.0, types=(3,)),
        205: dict(owner=2, x=180.0),
        206: dict(owner=2, x=320.0),
    }
    assert world.run(dll, owner=0) == dict(owner=1, cursor=0, changed=0, built=False,
                                          status=0, mined=0, wood=0, spells=0, researched=0, creeps=0, trained=0, built_kind=0, upgraded=False, train_kind=0, train_wait=0)
    assert world.commands == []
    assert world.run(dll)['changed'] == 1
    assert world.commands == [(101, 851983, 205)]
    assert world.run(dll)['changed'] == 0


@pytest.mark.parametrize('feature,target', [(NEUTRAL_CREATURES, 204), (NEUTRAL_BUILDINGS, 205)])
def test_neutral_creatures_and_buildings_use_independent_filters(dll, feature, target):
    world = AIWorld()
    world.units = {
        101: dict(owner=1),
        102: dict(owner=1, order=851986),
        201: dict(owner=2, x=30.0),
        202: dict(owner=28, x=70.0, invulnerable=1),
        203: dict(owner=28, x=80.0, types=(2,), invulnerable=1),
        204: dict(owner=28, x=4100.0),
        205: dict(owner=25, x=4160.0, types=(2,)),
    }
    assert world.run(dll, features=feature, radius=4000)['changed'] == 0
    assert world.run(dll, features=feature, radius=4800)['changed'] == 1
    assert world.commands == [(101, 851983, target)]


def test_pickup_orders_use_free_inventory_and_eligible_ground_items(dll):
    world = AIWorld()
    world.units = {
        101: dict(owner=1, types=(0, 6), inventory=(0, 0)),
        102: dict(owner=1, types=(0, 6), inventory=(0,)),
        103: dict(owner=1, types=(0, 6), inventory=(42,)),
        104: dict(owner=2, types=(0, 6), inventory=(0,)),
        105: dict(owner=1, types=(0, 6), inventory=(0,), order=851986),
    }
    world.widgets = {
        201: dict(kind='Item', x=50.0, owned=1),
        202: dict(kind='Item', x=60.0, invulnerable=1),
        203: dict(kind='Item', x=70.0, visible=0),
        204: dict(kind='Item', x=-80.0),
        205: dict(kind='Item', x=90.0, life=0.0),
        206: dict(kind='Destructable', x=95.0, tag=b'lga+meti'),
        207: dict(kind='Item', x=100.0),
        208: dict(kind='Item', x=120.0),
        209: dict(kind='Item', x=9000.0),
    }
    assert world.run(dll, features=PICKUP)['changed'] == 2
    assert world.commands == [(101, 851971, 207), (102, 851971, 208)]


def test_nearest_hero_with_space_picks_normal_items(dll):
    world = AIWorld()
    world.units = {
        101: dict(owner=1, types=(0, 6), x=0.0, inventory=(0,)),
        102: dict(owner=1, types=(0, 6), x=100.0, inventory=(1,)),
        103: dict(owner=1, types=(0, 6), x=140.0, inventory=(0,)),
        104: dict(owner=1, x=108.0, inventory=(0,)),
    }
    world.widgets = {201: dict(kind='Item', x=110.0)}
    assert world.run(dll, features=PICKUP)['changed'] == 1
    assert world.commands == [(103, 851971, 201)]


@pytest.mark.parametrize('code_name', ['gfor', 'rhe2', 'lmbr', 'gold', 'I001'])
def test_full_backpacks_allow_only_instant_items(dll, code_name):
    world = AIWorld()
    world.units = {
        101: dict(owner=1, types=(0, 6), x=0.0, inventory=(1,)),
        102: dict(owner=1, types=(0, 6), x=100.0, inventory=(2,)),
    }
    world.widgets = {
        201: dict(kind='Item', x=100.0),
        202: dict(kind='Item', code=code(code_name), x=110.0, instant=True),
    }
    assert world.run(dll, features=PICKUP)['changed'] == 1
    assert world.commands == [(102, 851971, 202)]


@pytest.mark.parametrize('attribute,book', [(1, b'Istr'), (2, b'Iint'), (3, b'Iagi')])
def test_single_stat_book_prefers_closest_matching_primary_even_when_full(dll, attribute, book):
    world = AIWorld()
    world.units = {
        101: dict(owner=1, types=(0, 6), x=105.0, inventory=(0,), primary=attribute % 3 + 1),
        102: dict(owner=1, types=(0, 6), x=220.0, inventory=(2,), primary=attribute),
        103: dict(owner=1, types=(0, 6), x=200.0, inventory=(3,), primary=attribute),
    }
    world.widgets = {201: dict(kind='Item', x=100.0, instant=True, attributes=({book: 2},))}
    assert world.run(dll, features=PICKUP)['changed'] == 1
    assert world.commands == [(103, 851971, 201)]


@pytest.mark.parametrize('expected', ['enemy', 'neutral', 'destructible', 'item'])
def test_combined_modes_choose_nearest_eligible_target(dll, expected):
    world = AIWorld()
    positions = dict(enemy=300.0, neutral=300.0, destructible=300.0, item=300.0)
    positions[expected] = 50.0
    world.units = {
        101: dict(owner=1, types=(0, 6), inventory=(0,)),
        201: dict(owner=2, types=(2,), x=positions['enemy']),
        202: dict(owner=28, types=(2,), x=positions['neutral']),
    }
    world.widgets = {
        203: dict(kind='Destructable', x=positions['destructible']),
        204: dict(kind='Item', x=positions['item']),
    }
    assert world.run(dll, features=1 | PICKUP | NEUTRAL_BUILDINGS | DESTRUCTIBLES)['changed'] == 1
    target = ('enemy', 'neutral', 'destructible', 'item').index(expected) + 201
    assert world.commands == [(101, 851971 if expected == 'item' else 851983, target)]


def test_world_converter_preflight_retries_after_read_only_group_query(monkeypatch):
    from contextlib import nullcontext
    from threading import RLock
    from war3_engine_24268 import EngineExecutionError
    from war3_services.fullclone import FullCloneService

    entries = AIWorld().entries
    registry = SimpleNamespace(base=0x100000)
    recorded = []
    reads = []

    class Engine(FullCloneService):
        pid = 1
        session = SimpleNamespace(lock=RLock(), cache={}, epoch=3, profile=None,
                                  prepare=lambda memory: (registry, None, None))

        def memory_factory(self, pid):
            return nullcontext()

        def _execute(self, kind, names, builder, decoder, request):
            recorded.append((request['features'], request['inspect']))
            try:
                return builder(entries, 0x20000)
            except Exception as exc:
                raise EngineExecutionError(str(exc), {'dispatch_attempted': False}) from exc

    def converter(*_):
        reads.append(1)
        if len(reads) == 1:
            raise OSError(0, 'temporarily unreadable', None, 299)
        return 0x110000

    monkeypatch.setattr('war3_fullclone_runtime.widget_converter', converter)
    engine = Engine()
    engine.fullclone_local_ai(owner=1, expected_epoch=3, features=PICKUP)
    engine.fullclone_local_ai(owner=1, expected_epoch=3, features=DESTRUCTIBLES)
    assert recorded == [(PICKUP, False), (1, True), (PICKUP, False), (DESTRUCTIBLES, False)]
    assert len(reads) == 2


def test_world_inspection_reports_only_visible_targets_without_issuing_orders(dll):
    world = AIWorld()
    world.units = {101: dict(owner=1, inventory=(0,))}
    world.widgets = {
        201: dict(kind='Item', x=80.0),
        202: dict(kind='Item', x=-90.0),
        203: dict(kind='Destructable', x=100.0),
        204: dict(kind='Destructable', x=-110.0),
    }
    result = world.run(dll, features=PICKUP | DESTRUCTIBLES, inspect=True, inspect_world=True)
    assert (result['world_items'], result['world_destructibles']) == (1, 1)
    assert result['changed'] == 0 and world.commands == []


def test_destructible_orders_skip_invulnerable_dead_and_incompatible_targets(dll):
    world = AIWorld()
    world.units = {101: dict(owner=1, types=(5,)), 102: dict(owner=1), 103: dict(owner=2)}
    world.widgets = {
        201: dict(kind='Destructable', x=40.0, invulnerable=1),
        202: dict(kind='Destructable', x=60.0, life=0.0),
        203: dict(kind='Destructable', x=-70.0),
        204: dict(kind='Item', x=80.0, tag=b'lga+d3w+'),
        205: dict(kind='Destructable', x=4900.0),
    }
    assert world.run(dll, features=DESTRUCTIBLES, radius=4800)['changed'] == 0
    assert world.run(dll, features=DESTRUCTIBLES, radius=6400)['changed'] == 1
    assert world.commands == [(102, 851983, 205)]


@pytest.mark.parametrize('feature,command', [(1, 851983), (PICKUP, 851971), (DESTRUCTIBLES, 851983)])
def test_expanded_target_search_radius_reaches_far_targets(dll, feature, command):
    world = AIWorld()
    world.units = {101: dict(owner=1, types=(0, 6), inventory=(0,))}
    if feature == 1:
        world.units[201] = dict(owner=2, x=24000.0)
    else:
        kind = 'Item' if feature == PICKUP else 'Destructable'
        world.widgets[201] = dict(kind=kind, x=24000.0)

    assert world.run(dll, features=feature, radius=19200)['changed'] == 0
    assert world.run(dll, features=feature, radius=25600)['changed'] == 1
    assert world.commands == [(101, command, 201)]


@pytest.mark.parametrize('feature,owner,types', [
    (1, 2, (2,)), (32, 25, (6,)),
    (NEUTRAL_CREATURES, 28, (6,)), (NEUTRAL_BUILDINGS, 28, (2,)),
])
def test_attack_skips_all_invulnerable_candidates_and_rechecks_before_order(dll, feature, owner, types):
    world = AIWorld()
    world.units = {
        101: dict(owner=1),
        **{u: dict(owner=owner, x=40.0, types=types, invulnerable=1) for u in range(200, 420)},
        501: dict(owner=owner, x=21000.0, types=types, checks_before_invulnerable=1),
        502: dict(owner=owner, x=24000.0, types=types),
    }
    result = world.run(dll, features=feature, radius=25600)
    assert result['changed'] == 1
    assert world.commands == [(101, 851983, 502)]


def test_destructible_selection_reads_the_boolean_not_selection_size():
    from war3_fullclone_ai_destructibles import selectable_type_ids

    stock = b'''ID;PWXL;N;E
C;X1;Y1;K"destructableid"
C;X2;Y1;K"selectable"
C;X1;Y2;K"ROCK"
C;X2;Y2;K0
C;X1;Y3;K"DOOR"
C;X2;Y3;K1
E
'''

    def records(originals=(), customs=()):
        def table(rows):
            return struct.pack('<I', len(rows)) + b''.join(rows)
        return struct.pack('<I', 2) + table(originals) + table(customs)

    selection_size = b'ROCK' + bytes(4) + struct.pack('<I4sIfI', 1, b'bsel', 1, 100.0, 0)
    inherited = b'DOORCstm' + struct.pack('<I', 0)
    assert selectable_type_ids(stock, (((), (records((selection_size,), (inherited,)),)),)) == (
        code('Cstm'), code('DOOR'),
    )
    off = b'Cstm' + bytes(4) + struct.pack('<I4sIII', 1, b'bgse', 0, 0, 0)
    on = b'ROCK' + bytes(4) + struct.pack('<I4sIII', 1, b'bgse', 0, 1, 0)
    assert selectable_type_ids(stock, (
        ((), (records((selection_size,), (inherited,)),)),
        ((), (records((off, on)),)),
    )) == (code('DOOR'), code('ROCK'))


def test_destructible_attack_skips_nonselectable_and_unknown_types(dll):
    world = AIWorld()
    world.units = {101: dict(owner=1)}
    world.widgets = {
        201: dict(kind='Destructable', code=code('ROCK'), x=40.0),
        202: dict(kind='Destructable', code=code('CSTM'), x=60.0),
        203: dict(kind='Destructable', code=code('DOOR'), x=110.0),
    }
    assert world.run(dll, features=DESTRUCTIBLES, selectable_destructibles=())['changed'] == 0
    assert world.run(dll, features=DESTRUCTIBLES,
                     selectable_destructibles=(code('DOOR'),))['changed'] == 1
    assert world.commands == [(101, 851983, 203)]


def test_destructible_that_becomes_invulnerable_is_replaced(dll):
    world = AIWorld()
    world.units = {101: dict(owner=1)}
    world.widgets = {
        201: dict(kind='Destructable', x=50.0, invulnerable=1),
        202: dict(kind='Destructable', x=80.0, checks_before_invulnerable=1),
        203: dict(kind='Destructable', x=150.0),
    }
    assert world.run(dll, features=DESTRUCTIBLES)['changed'] == 1
    assert world.commands == [(101, 851983, 203)]


def test_ai_resumes_in_batches_and_stops_on_changed_identity(dll):
    world = AIWorld()
    world.units = {u: dict(owner=1) for u in range(100, 130)}
    world.units[200] = dict(owner=2, x=75.0)
    first = world.run(dll)
    assert first['changed'] == 24 and first['cursor'] == 24
    assert world.run(dll, cursor=first['cursor']) == dict(owner=1, cursor=0, changed=6, built=False,
                                                         status=0, mined=0, wood=0, spells=0, researched=0, creeps=0, trained=0, built_kind=0, upgraded=False, train_kind=0, train_wait=0)
    world.owner = 3
    with pytest.raises(RuntimeError, match='本地玩家已变化'):
        world.run(dll)
    assert len(world.commands) == 30


def test_ai_checks_player_again_after_order_callbacks(dll):
    world = AIWorld()
    world.units = {100: dict(owner=1), 101: dict(owner=1), 200: dict(owner=2, x=75.0)}
    world.reassign_player = True
    with pytest.raises(RuntimeError, match='本地玩家已变化'):
        world.run(dll)
    assert world.commands == [(100, 851983, 200)]
    world.controller = 1
    with pytest.raises(RuntimeError, match='没有可托管'):
        world.run(dll, owner=0)


def test_stop_invalidates_queued_game_tick_and_map_change_requires_new_start():
    from threading import RLock

    calls = []
    queued = []

    class Engine:
        pid, hwnd = 100, 200
        session = SimpleNamespace(epoch=3, lock=RLock(), cache={})

        def fullclone_local_ai(self, **options):
            calls.append(options)
            if options and options['expected_epoch'] != self.session.epoch:
                raise RuntimeError('map changed')
            return dict(owner=1, cursor=7, built=False, status=0, mined=0, wood=0, spells=0,
                        researched=0, creeps=0, trained=0, built_kind=0, upgraded=False, train_kind=0, train_wait=0)

    engine = Engine()
    trainer = SimpleNamespace(pid=100, hwnd=200, _engine_instance_24268=lambda: engine)
    state = dict(trainer=trainer)
    root = SimpleNamespace(after=lambda ms, callback, *args: queued.append((callback, args)))
    app = FullCloneApplication()
    app.view = SimpleNamespace(value=dict(state=state, root=root).__getitem__)
    app.trainer = lambda: trainer

    def run_queued():
        callback, args = queued.pop(0)
        callback(*args)

    assert not app.fc_local_ai_status()['active']
    app.fc_action('local_ai_start')
    app.fc_action('local_ai_stop')
    run_queued()
    assert calls == [{}]
    assert not queued
    app.fc_action('local_ai_start')
    run_queued()
    assert calls[-1] == dict(owner=1, cursor=0, expected_epoch=3, radius=900, features=1,
                             allow_build=False, allow_research=False, allow_train=False, blocked_builds=0, blocked_train=0)
    engine.session.epoch += 1
    run_queued()
    assert calls[-1] == dict(owner=1, cursor=7, expected_epoch=3, radius=900, features=1,
                             allow_build=False, allow_research=False, allow_train=False, blocked_builds=0, blocked_train=0)
    assert not queued
    assert app.fc_local_ai_status() == dict(active=False, stopped=True, detail='map changed', progress=None)


def code(rawcode):
    return int.from_bytes(rawcode.encode('ascii'), 'big')


def test_squad_defends_before_hero_or_army_and_preserves_queued_orders(dll):
    world = AIWorld()
    world.units = {
        100: dict(owner=1, code=code('htow'), types=(2,)),
        101: dict(owner=1),
        102: dict(owner=1, queued=1),
        103: dict(owner=1, types=(16, 6)),
        104: dict(owner=1, life=100),
        201: dict(owner=2, x=40.0, visible=0),
        202: dict(owner=3, x=60.0),
        203: dict(owner=25, x=80.0),
        204: dict(owner=2, x=140.0, y=20.0),
    }
    result = world.run(dll, features=129)
    assert result['tactics_mode'] == 1 and result['tactics_issued'] == 1
    assert world.commands == [(101, 851983, (140.0, 20.0))]


def test_squad_retargets_before_sending_attack_move(dll):
    world = AIWorld()
    world.units = {
        100: dict(owner=1, code=code('htow'), types=(2,)),
        101: dict(owner=1),
        201: dict(owner=2, x=80.0, types=(2,), checks_before_invulnerable=1),
        202: dict(owner=2, x=150.0),
    }
    result = world.run(dll, features=129)
    assert result['tactics_mode'] == 1 and result['tactics_issued'] == 1
    assert world.commands == [(101, 851983, (150.0, 0.0))]


def test_squad_waits_for_stock_threshold_then_rallies_and_advances(dll):
    world = AIWorld()
    world.computers = {2, 3}
    world.starts = {1: (4600.0, 100.0), 2: (3500.0, 100.0)}
    world.units = {
        100: dict(owner=1, code=code('ogre'), types=(2,)),
        101: dict(owner=1, types=(0, 6)),
        102: dict(owner=1, x=20.0),
        103: dict(owner=1, x=1200.0),
    }
    options = dict(features=128, wave_troops=(2, 3, 6, 2))
    assert world.run(dll, **options)['changed'] == 0
    world.units[104] = dict(owner=1, x=25.0)
    assert world.run(dll, **options)['tactics_mode'] == 2
    assert world.commands == [(103, 851986, (0.0, 0.0))]
    world.units[103].update(x=100.0, order=0)
    world.commands.clear()
    result = world.run(dll, **options)
    assert result['tactics_mode'] == 4 and result['tactics_ready'] == 3
    assert world.commands == [(unit, 851983, (4600.0, 100.0)) for unit in range(101, 105)]


def test_undead_keeps_lumber_crew_and_attacks_eligible_creep_as_group(dll):
    world = AIWorld()
    world.wood_accepts = True
    world.units = {
        100: dict(owner=1, code=code('unpl'), types=(2,)),
        101: dict(owner=1, types=(0, 6)),
        **{u: dict(owner=1, code=code('ugho'), types=(16, 6)) for u in range(102, 110)},
        200: dict(owner=25, x=50.0, level=8),
        201: dict(owner=25, x=150.0, level=3),
    }
    result = world.run(dll, features=128 | 32 | 2)
    assert result['wood'] == 2 and result['tactics_ready'] == 6
    assert result['tactics_mode'] == 3 and result['tactics_issued'] == 7
    assert world.commands[:2] == [(u, 852022, 0) for u in (102, 103)]
    assert world.commands[2:] == [(u, 851983, (150.0, 0.0)) for u in (101, *range(104, 110))]


def test_radius_changes_eligible_visible_targets(dll):
    world = AIWorld()
    world.units = {100: dict(owner=1), 200: dict(owner=2, x=2300.0)}
    assert world.run(dll, radius=1600)['changed'] == 0
    assert world.run(dll, radius=2400)['changed'] == 1
    assert world.commands == [(100, 851983, 200)]


def test_mining_wood_and_construction_only_issue_orders_to_own_idle_workers(dll):
    world = AIWorld()
    world.units = {
        100: dict(owner=1, code=code('hpea'), types=(16,)),
        101: dict(owner=3, code=code('hpea'), types=(16,)),
        102: dict(owner=1, code=code('hpea'), types=(16,), order=851986),
        150: dict(owner=28, code=code('ngol'), resource=12000, x=640.0, types=(2,)),
        151: dict(owner=2, code=code('ngol'), resource=12000, x=100.0, types=(2,)),
        160: dict(owner=1, code=code('htow'), types=(2,)),
    }
    assert world.run(dll, features=2)['changed'] == 1
    assert world.commands == [(100, 852018, 150)]
    world.units[100]['order'] = 0
    world.player_states[2] = 50
    world.wood_accepts = True
    assert world.run(dll, features=2)['changed'] == 1
    assert world.commands[-1] == (100, 852022, 0)
    world.units[100]['order'] = 0
    assert not world.run(dll, features=4, allow_build=True)['built']
    world.player_states[5] = 18
    assert not world.run(dll, features=4)['built']
    assert world.run(dll, features=6, allow_build=True)['built']
    # The first point is obstructed by the nearby mine.
    assert world.placements == [(100, code('hhou'), 0.0, 512.0)]


def test_hero_cast_checks_learned_level_mana_cooldown_and_visibility(dll):
    world = AIWorld()
    world.units = {
        100: dict(owner=1, mana=74.0, spells={code('AHtb'): 1}, types=(0, 6)),
        101: dict(owner=1, mana=100.0, cooldown=2.0, spells={code('AHtb'): 1}, types=(0, 6)),
        102: dict(owner=1, mana=100.0, spells={code('AHtb'): 0}, types=(0, 6)),
        103: dict(owner=1, mana=100.0, spells={code('AHtb'): 1}, types=(0, 6)),
        104: dict(owner=3, mana=100.0, spells={code('AHtb'): 1}, types=(0, 6)),
        200: dict(owner=2, x=80.0, visible=0),
        201: dict(owner=2, x=200.0),
        202: dict(owner=2, x=80.0, types=(26,)),
    }
    assert world.run(dll, features=8)['changed'] == 1
    assert world.commands == [(103, 852095, 201)]


def test_gold_recovers_stock_order_rejection_and_supports_owned_proxy_mine(dll):
    world = AIWorld()
    world.reject_orders.add(852018)
    world.units = {
        100: dict(owner=1, code=code('hpea'), types=(16,)),
        101: dict(owner=1, code=code('ewsp'), types=(16,)),
        150: dict(owner=28, code=code('ngol'), resource=9000, x=300.0, types=(2,)),
        151: dict(owner=1, code=code('egol'), resource=0, x=310.0, types=(2,)),
    }
    assert world.run(dll, features=2)['mined'] == 2
    assert world.commands == [(100, 851971, 150), (101, 851971, 151)]


def test_supply_can_reassign_gathering_but_not_moving_or_other_players(dll):
    world = AIWorld()
    world.player_states[5] = 17
    world.units = {
        100: dict(owner=1, code=code('hpea'), types=(16,), order=851986),
        101: dict(owner=2, code=code('hpea'), types=(16,), order=852018),
        102: dict(owner=1, code=code('hpea'), types=(16,), order=852018),
        160: dict(owner=1, code=code('htow'), types=(2,)),
        180: dict(owner=28, code=code('ngol'), resource=12000, x=1000.0, types=(2,)),
    }
    from war3_fullclone_ai_protocol import SITE
    preview = world.run(dll, features=6, allow_build=True, inspect=True)
    assert preview['status'] & SITE
    assert preview['changed'] == 0 and not world.placements and not world.commands
    assert world.run(dll, features=4, allow_build=True)['built']
    assert [placement[0] for placement in world.placements] == [102]


def test_construction_requires_the_ordered_building_at_the_expected_location(dll):
    world = AIWorld()
    crypt = code('usep')
    world.units = {
        100: dict(owner=1, code=code('unpl'), types=(2,)),
        **{u: dict(owner=1, code=code('uaco'), types=(16,)) for u in range(101, 106)},
    }
    ordered = world.run(dll, features=68, allow_build=True)
    site = ordered['ordered_site']
    assert site[0] == crypt and not ordered['build_started']
    world.units[200] = dict(owner=2, code=crypt, types=(2,), x=site[1], y=site[2])
    world.units[201] = dict(owner=1, code=crypt, types=(2,), x=1100.0)
    assert not world.run(dll, features=68, pending_site=site)['build_started']
    world.units[200].update(owner=1, life=3.0)
    assert world.run(dll, features=68, pending_site=site)['build_started']
    for unit in (200, 201):
        del world.units[unit]
    retry = world.run(dll, features=68, allow_build=True, avoid_site=site)
    assert retry['ordered_site'][1:] != site[1:]
    assert retry['ordered_site'][0] == crypt


def test_undead_keeps_a_builder_and_places_second_supply_before_food_shortage(dll):
    world = AIWorld()
    acolyte, crypt, altar, ziggurat = (code(tag) for tag in ('uaco', 'usep', 'uaod', 'uzig'))
    world.player_states[5] = 10
    world.units = {
        100: dict(owner=1, code=code('unpl'), types=(2,)),
        **{u: dict(owner=1, code=acolyte, types=(16,)) for u in range(101, 106)},
        110: dict(owner=1, code=code('ugol'), types=(2,), x=640.0),
        111: dict(owner=1, code=crypt, types=(2,), x=460.0),
        112: dict(owner=1, code=altar, types=(2,), x=320.0),
        113: dict(owner=1, code=ziggurat, types=(2,), y=450.0),
    }
    world.train_accepts.add(acolyte)
    options = dict(features=128 | 64 | 4 | 2, allow_train=True)
    world.run(dll, **options)
    assert world.units[101].get('order', 0) == 0
    assert all(world.units[u]['order'] == 851971 for u in range(102, 106))
    assert (100, acolyte, 0) in world.commands
    assert world.run(dll, allow_build=True, **options)['built_kind'] == 1
    assert world.placements[-1][0:2] == (101, ziggurat)


def test_failed_start_retries_another_site_and_holds_resources():
    site = (code('usep'), 512.0, 0.0)
    new_site = (code('usep'), 0.0, 512.0)
    calls = []
    responses = iter((
        dict(built=True, built_kind=2, ordered_site=site),
        dict(built=False, build_started=False),
        dict(built=True, built_kind=2, ordered_site=new_site),
        dict(built=False, build_started=True),
    ))
    def tick(**kwargs):
        calls.append(kwargs)
        return dict(owner=1, cursor=0, status=0, mined=0, wood=0, spells=0,
                    researched=0, creeps=0, trained=0, upgraded=False, train_kind=0,
                    **next(responses))

    engine = SimpleNamespace(session=SimpleNamespace(cache={}), fullclone_local_ai=tick)
    control = dict(engine=engine, trainer=SimpleNamespace(), owner=1, epoch=1, cursor=0,
                   build_cooldowns={}, train_cooldowns={}, next_research=0, build_state={},
                   progress=None)
    app = FullCloneApplication()
    for second in (0, 26, 28, 32):
        with patch('war3_fullclone_application.monotonic', return_value=second):
            app.fc_local_ai_orders(control, 68, 900)
    assert calls[0]['allow_build']
    assert calls[1]['pending_site'] == site and not calls[1]['allow_build'] and not calls[1]['allow_train']
    assert calls[2]['avoid_site'] == site and calls[2]['allow_build']
    assert calls[3]['pending_site'] == new_site
    assert control['progress']['built'] == 2 and control['progress']['buildStarted'] == 1
    assert control['progress']['buildTimeouts'] == 1 and not control['build_state']


def test_custom_peon_retaining_stock_abilities_can_be_assigned(dll):
    world = AIWorld()
    abilities = {code('AHbu'): 1, code('Ahar'): 1}
    world.units = {
        100: dict(owner=1, code=code('h005'), types=(16,), spells=abilities),
        101: dict(owner=1, code=code('h006'), types=(6,), spells=abilities),
        150: dict(owner=28, code=code('ngol'), resource=12000, x=1100.0, types=(2,)),
        160: dict(owner=1, code=code('htow'), types=(2,)),
    }
    assert world.run(dll, features=2)['mined'] == 1
    assert world.commands == [(100, 852018, 150)]
    world.player_states[5] = 19
    assert world.run(dll, features=4, allow_build=True)['built']
    assert [placement[0] for placement in world.placements] == [100]


def test_research_queues_stock_upgrade_once_and_respects_building_owner_and_caps(dll):
    world = AIWorld()
    forge = code('hbla')
    world.units = {
        100: dict(owner=2, code=forge, types=(2,)),
        101: dict(owner=1, code=forge, types=(2,), order=852000),
        102: dict(owner=1, code=forge, types=(2,)),
        103: dict(owner=1, code=forge, types=(2,)),
    }
    melee, armor, ranged = (code(t) for t in ('Rhme','Rhar','Rhra'))
    world.research_accepts = {melee, armor, ranged}
    world.tech_levels = {melee: 3}
    world.tech_limits = {armor: 0}
    assert world.run(dll, features=16, allow_research=True, inspect=True)['changed'] == 0
    assert world.run(dll, features=16)['changed'] == 0
    assert world.run(dll, features=16, allow_research=True)['researched'] == 1
    assert world.commands == [(102, ranged, 0)]


def test_creep_mode_targets_visible_neutral_hostile_and_skips_low_health(dll):
    world = AIWorld()
    world.units = {
        100: dict(owner=1),
        101: dict(owner=1, life=200.0),
        102: dict(owner=3),
        200: dict(owner=2, x=140.0),
        201: dict(owner=25, x=160.0, types=(2,)),
        202: dict(owner=25, x=180.0, visible=0),
        203: dict(owner=25, x=300.0),
    }
    assert world.run(dll, features=32)['creeps'] == 1
    assert world.commands == [(100, 851983, 203)]


@pytest.mark.parametrize('ids,target', [
    (('htow', 'hpea', 'hbar', 'hfoo'), 8),
    (('ogre', 'opeo', 'obar', 'ogru'), 8),
    (('unpl', 'uaco', 'usep', 'ugho'), 5),
    (('etol', 'ewsp', 'eaom', 'earc'), 8),
])
def test_training_replenishes_workers_then_trains_combat_units(dll, ids, target):
    hall, worker, factory, soldier = (int.from_bytes(code.encode('ascii'), 'big') for code in ids)
    world = AIWorld()
    world.units = {
        100: dict(owner=1, code=hall, types=(2,)),
        200: dict(owner=1, code=factory, types=(2,)),
        300: dict(owner=2, code=factory, types=(2,)),
    }
    world.train_accepts = {worker, soldier}
    assert world.run(dll, features=64, allow_train=True, inspect=True)['trained'] == 0
    assert world.run(dll, features=64, allow_train=True)['trained'] == 1
    assert world.commands == [(100, worker, 0)]
    world.units[100]['order'] = 0
    assert world.run(dll, features=64, allow_train=True, blocked_train=3)['trained'] == 0
    for i in range(target):
        world.units[400+i] = dict(owner=1, code=worker, types=(16,), hidden=1)
    world.units[100]['order'] = 0
    assert world.run(dll, features=64, allow_train=True)['trained'] == 1
    assert world.commands[-1] == (200, soldier, 0)
    world.units[200].update(order=0, queued=1)
    assert world.run(dll, features=64, allow_train=True)['trained'] == 0
    world.units[200].update(queued=0)
    world.player_states[4] = world.player_states[5]
    assert world.run(dll, features=64, allow_train=True)['trained'] == 0
    assert len(world.commands) == 2


def test_opening_builds_owned_factory_only_when_construction_is_enabled(dll):
    hall, worker, factory = (int.from_bytes(code, 'big') for code in (b'htow', b'hpea', b'hbar'))
    world = AIWorld()
    world.units = {
        100: dict(owner=1, code=hall, types=(2,)),
        200: dict(owner=2, code=factory, types=(2,), x=1200.0),
        **{u: dict(owner=1, code=worker, types=(16,)) for u in range(101, 106)},
    }
    assert not world.run(dll, features=64, allow_train=True)['built']
    assert world.run(dll, features=68, allow_build=True)['built']
    assert world.placements[0][1] == factory
    world.units[300] = dict(owner=1, code=factory, types=(2,), x=512.0, queued=1)
    assert not world.run(dll, features=68, allow_build=True)['built']
    assert len(world.placements) == 1


def test_training_checks_costs_and_trains_first_hero_when_altar_is_ready(dll):
    factory, altar, soldier, hero = (int.from_bytes(code, 'big') for code in (b'hbar', b'halt', b'hfoo', b'Hamg'))
    world = AIWorld()
    world.units = {
        100: dict(owner=1, code=factory, types=(2,)),
        101: dict(owner=1, code=altar, types=(2,), order=1000),
    }
    world.train_accepts = {soldier, hero}
    world.player_states[1] = 100
    assert world.run(dll, features=64, allow_train=True)['trained'] == 0
    assert world.commands == []
    world.units[101]['order'] = 0
    assert world.run(dll, features=64, allow_train=True)['trained'] == 1
    assert world.commands == [(101, hero, 0)]


@pytest.mark.parametrize('faction_seed,hall,altar,stock,expected', [
    (1, 'htow', 'halt', ('Hamg', 'Hmkg', 'Hpal', 'Hblm'), 'Hmkg'),
    (2 << 8, 'ogre', 'oalt', ('Obla', 'Ofar', 'Otch', 'Oshd'), 'Otch'),
    (3 << 16, 'unpl', 'uaod', ('Udea', 'Udre', 'Ulic', 'Ucrl'), 'Ucrl'),
    (1 << 24, 'etol', 'eate', ('Edem', 'Ekee', 'Emoo', 'Ewar'), 'Ekee'),
])
def test_stock_hero_pool_selects_by_faction(dll, faction_seed, hall, altar, stock, expected):
    world = AIWorld()
    world.units = {
        100: dict(owner=1, code=code(hall), types=(2,)),
        101: dict(owner=1, code=code(altar), types=(2,)),
    }
    world.train_accepts = set(map(code, stock))
    assert world.run(dll, features=64, allow_train=True, hero_seed=faction_seed)['trained'] == 1
    assert world.commands == [(101, code(expected), 0)]


def test_hero_choices_respect_tier_map_cap_and_existing_classes(dll):
    world = AIWorld()
    archmage, paladin, mountain, blood = map(code, ('Hamg', 'Hpal', 'Hmkg', 'Hblm'))
    world.units = {
        100: dict(owner=1, code=code('htow'), types=(2,)),
        101: dict(owner=1, code=code('halt'), types=(2,)),
        102: dict(owner=1, code=archmage, types=(0,)),
    }
    world.train_accepts = {archmage, paladin, mountain, blood}
    options = dict(features=64, allow_train=True)
    assert world.run(dll, **options)['trained'] == 0
    world.units[100]['code'] = code('hkee')
    world.tech_limits.update({code('HERO'): 1, blood: 0})
    assert world.run(dll, **options)['trained'] == 0
    world.tech_limits[code('HERO')] = 3
    assert world.run(dll, **options)['trained'] == 1
    assert world.commands == [(101, paladin, 0)]
    world.units[103] = dict(owner=1, code=paladin, types=(0,))
    world.units[101]['order'] = 0
    assert world.run(dll, **options)['trained'] == 0
    world.units[100]['code'] = code('hcas')
    assert world.run(dll, **options)['trained'] == 1
    assert world.commands[-1] == (101, mountain, 0)


def test_fallen_hero_queues_normal_revive_at_own_idle_altar(dll):
    world = AIWorld()
    world.units = {
        100: dict(owner=1, code=code('unp1'), types=(2,)),
        101: dict(owner=2, code=code('uaod'), types=(2,)),
        102: dict(owner=1, code=code('uaod'), types=(2,), queued=1),
        103: dict(owner=2, code=code('Udea'), types=(0, 1), life=0.0),
        104: dict(owner=1, code=code('Ulic'), types=(0, 1), life=0.0, hidden=1),
    }
    world.train_accepts = {code('Udre')}
    options = dict(features=64, allow_train=True)
    assert not world.run(dll, **options)['revive_queued']
    assert world.commands == []
    world.units[102]['queued'] = 0
    assert world.run(dll, **options, inspect=True)['changed'] == 0
    result = world.run(dll, **options)
    assert result['revive_queued'] and result['trained'] == 0 and result['train_kind'] == 4
    assert world.commands == [(102, 852039, 104)]
    assert not world.run(dll, **options)['revive_queued']
    assert world.commands == [(102, 852039, 104)]


def test_undead_opens_crypt_with_three_acolytes_and_other_construction_can_follow(dll):
    world = AIWorld()
    hall, worker, crypt, ziggurat, altar = (int.from_bytes(code, 'big') for code in
                                           (b'unpl', b'uaco', b'usep', b'uzig', b'uaod'))
    world.units = {
        101: dict(owner=1, code=hall, types=(2,)),
        **{u: dict(owner=1, code=worker, types=(16,)) for u in range(102,105)},
    }
    world.player_states.update({1:500, 2:150, 4:10, 5:5})
    assert world.run(dll,features=68,allow_build=True)['built_kind']==2
    assert world.placements[-1][1]==crypt
    world.units[105] = dict(owner=1,code=crypt,types=(2,),x=512.0,queued=1)
    assert world.run(dll,features=68,allow_build=True,blocked_builds=2)['built_kind']==1
    assert world.placements[-1][1]==ziggurat
    assert world.run(dll,features=68,allow_build=True,blocked_builds=3)['built_kind']==4
    assert world.placements[-1][1]==altar
    assert not world.run(dll,features=68,allow_build=True,blocked_builds=7)['built']


def test_undead_base_upgrade_checks_state_and_uses_idle_own_hall(dll):
    world = AIWorld()
    acolyte, ghoul, base, altar, graveyard, tier_two, enemy_base = (
        int.from_bytes(code,'big') for code in (b'uaco',b'ugho',b'unpl',b'uaod',b'ugrv',b'unp1',b'unpl'))
    world.units = {
        101:dict(owner=1,code=base,types=(2,)),
        102:dict(owner=2,code=enemy_base,types=(2,)),
        103:dict(owner=1,code=altar,types=(2,)),
        104:dict(owner=1,code=graveyard,types=(2,)),
        105:dict(owner=1,types=(0,)),
        **{u:dict(owner=1,code=acolyte,types=(16,)) for u in range(110,115)},
        **{u:dict(owner=1,code=ghoul,types=(6,)) for u in range(120,124)},
    }
    world.train_accepts = {tier_two}
    world.player_states.update({1:400,2:260,4:20,5:20})
    assert not world.run(dll,features=64,allow_train=True)['upgraded']
    world.units[101]['queued'] = 1
    assert not world.run(dll,features=68,allow_train=True)['upgraded']
    world.units[101]['queued'] = 0
    result=world.run(dll,features=68,allow_train=True)
    assert result['upgraded'] and result['trained']==0 and result['changed']==1
    assert world.commands==[(101,tier_two,0)]


@pytest.mark.parametrize('ids', [
    (b'hpea', b'hfoo', b'htow', b'hkee', b'hcas', b'hbar', b'halt', b'hbla', b'hars', b'hgra', b'hmpr', b'hgry'),
    (b'opeo', b'ogru', b'ogre', b'ostr', b'ofrt', b'obar', b'oalt', b'ofor', b'obea', b'otto', b'orai', b'otau'),
    (b'ewsp', b'earc', b'etol', b'etoa', b'etoe', b'eaom', b'eate', b'edob', b'eaoe', b'edos', b'edry', b'echm'),
])
def test_stock_faction_reaches_tier_three_and_trains_from_owned_specialist_factories(dll, ids):
    worker, troop, hall, tier_two, tier_three, factory, altar, prereq, support, late, support_unit, late_unit = (
        int.from_bytes(code, 'big') for code in ids)
    world = AIWorld()
    world.units = {
        101: dict(owner=1, code=hall, types=(2,)),
        102: dict(owner=1, code=factory, types=(2,)),
        103: dict(owner=1, code=altar, types=(2,)),
        104: dict(owner=1, types=(0,)),
        105: dict(owner=2, code=support, types=(2,)),
        **{u: dict(owner=1, code=worker, types=(16,)) for u in range(110,118)},
        **{u: dict(owner=1, code=troop) for u in range(120,124)},
    }
    world.player_states.update({1:1000, 2:1000, 4:60, 5:20})
    world.train_accepts = {tier_two, tier_three, support_unit, late_unit}
    options = dict(features=68, allow_build=True)
    assert not world.run(dll, features=68, allow_train=True)['upgraded']
    assert world.run(dll, **options)['built_kind'] == 8
    assert world.placements[-1][1] == prereq
    world.units[106] = dict(owner=1, code=prereq, types=(2,), x=1000.0)
    assert not world.run(dll, features=64, allow_train=True)['upgraded']
    assert world.run(dll, features=68, allow_train=True)['upgraded']
    assert world.commands[-1] == (101, tier_two, 0)
    world.units[101].update(code=tier_two, order=0)
    assert not world.run(dll, features=68, allow_train=True)['upgraded']
    assert world.run(dll, **options)['built_kind'] == 32
    assert world.placements[-1][1] == support
    world.units[107] = dict(owner=1, code=support, types=(2,), x=1000.0)
    assert world.run(dll, features=68, allow_train=True, blocked_train=1)['trained'] == 1
    assert world.commands[-1] == (107, support_unit, 0)
    assert world.run(dll, features=68, allow_train=True)['upgraded']
    assert world.commands[-1] == (101, tier_three, 0)
    world.units[101].update(code=tier_three, order=0)
    if ids[2] == b'htow':
        assert world.run(dll, **options)['built_kind'] == 16
        mill = int.from_bytes(b'hlum', 'big')
        assert world.placements[-1][1] == mill
        world.units[108] = dict(owner=1, code=mill, types=(2,), x=1000.0)
    assert world.run(dll, **options)['built_kind'] == 64
    assert world.placements[-1][1] == late
    world.units[109] = dict(owner=1, code=late, types=(2,), x=1000.0)
    assert world.run(dll, features=68, allow_train=True, blocked_train=8)['trained'] == 1
    assert world.commands[-1] == (109, late_unit, 0)



def test_stock_opening_changes_build_order_and_worker_target(dll):
    from test_fullclone_ai_stock import COMMON, SCRIPT
    from war3_fullclone_ai_stock import FACTIONS, project_opening

    world = AIWorld()
    hall, worker, altar, supply, factory = (
        int.from_bytes(code, 'big') for code in (b'ogre', b'opeo', b'oalt', b'otrb', b'obar'))
    world.units = {
        101: dict(owner=1, code=hall, types=(2,)),
        **{u: dict(owner=1, code=worker, types=(16,)) for u in range(102, 108)},
        201: dict(owner=2, code=altar, types=(2,), x=3000.0),
    }
    world.player_states.update({1:1000, 2:1000, 4:60, 5:8})
    world.train_accepts = {worker}
    plans = (None, project_opening(COMMON, SCRIPT, FACTIONS[1]), None, None)
    assert world.run(dll, features=68, allow_build=True)['built_kind'] == 2
    assert world.placements[-1][1] == factory
    assert world.run(dll, features=68, allow_build=True, openings=plans)['built_kind'] == 4
    assert world.placements[-1][1] == altar
    # The inferred opening already has the 6 workers required for the altar.
    assert not world.run(dll, features=68, allow_train=True, openings=plans)['trained']
    world.units[109] = dict(owner=1, code=altar, types=(2,), x=1000.0)
    assert world.run(dll, features=68, allow_train=True, openings=plans)['trained']
    assert world.commands[-1] == (101, worker, 0)
    assert world.run(dll, features=68, allow_build=True, openings=plans)['built_kind'] == 1
    world.units[110] = dict(owner=1, code=supply, types=(2,), x=1000.0)
    assert world.run(dll, features=68, allow_build=True, openings=plans)['built_kind'] == 1
    world.units[111] = dict(owner=1, code=supply, types=(2,), x=1100.0)
    assert world.run(dll, features=68, allow_build=True, openings=plans)['built_kind'] == 2
    assert world.placements[-1][1] == factory
