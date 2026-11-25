"""Identity-bound skill writes work with no game selection or other game state."""
import ctypes
import struct
from types import SimpleNamespace

import pytest

from test_fullclone_migration import B, I, U, dll
from war3_game_session import FullHandle, ObjectAddress, UnitRef
from war3_hero_skill_bound_protocol import SIGNATURES, build_work, decode_work


def test_bound_skill_add_level_remove_and_refusal_on_changed_identity(dll):
    buffer = ctypes.create_string_buffer(1024)
    address = ctypes.addressof(buffer)
    ref = UnitRef(None, 0, FullHandle(0x123456), ObjectAddress(address), 0x4870616c)
    dll.FCFixtureHeroObjectField.argtypes = [ctypes.c_uint32]
    dll.FCFixtureHeroObjectField.restype = ctypes.c_uint32
    full_offset, raw_offset = [dll.FCFixtureHeroObjectField(i) for i in range(2)]
    struct.pack_into('<Q', buffer, full_offset, ref.handle.value)
    struct.pack_into('<I', buffer, raw_offset, ref.rawcode)
    entries, callbacks, changes = {}, [], []
    skill, unit, state = 0x41486862, 1001, {'level': 0}

    def bind(name, result, args, callback):
        native = ctypes.CFUNCTYPE(result, *args)(callback)
        callbacks.append(native)
        entries[name] = SimpleNamespace(name=name, signature=dict(SIGNATURES)[name],
                                        handler=ctypes.cast(native, ctypes.c_void_p).value)

    def level(handle, code, value):
        changes.append((handle, code, value))
        state['level'] = value
        return value

    def ability(handle, code):
        return 173 if state['level'] else 0

    bind('UnitAddAbility', B, (U, I), lambda h, c: level(h, c, 1))
    bind('UnitRemoveAbility', B, (U, I), lambda h, c: not level(h, c, 0))
    bind('SetUnitAbilityLevel', I, (U, I, I), level)
    bind('GetUnitAbilityLevel', I, (U, I), lambda *args: state['level'])
    bind('BlzGetUnitAbility', U, (U, I), ability)
    bind('BlzGetAbilityId', I, (U,), lambda a: skill)
    bind('BlzGetUnitAbilityByIndex', U, (U, I), lambda h, i: ability(h, skill) if i==0 else 0)
    bind('GetUnitTypeId', I, (U,), lambda h: ref.rawcode)
    resolver = ctypes.CFUNCTYPE(U, U)(lambda h: address if h==unit else 0)

    def run(action=0, prior=0, level=0):
        resolver_address = ctypes.cast(resolver, ctypes.c_void_p).value
        data = build_work(entries, 0x20000, resolver_address, ref, unit, skill, action, prior, level)
        work = ctypes.create_string_buffer(data, len(data))
        count = dll.FCFixtureRun(work, 7)
        return decode_work(work.raw, count, handle=unit, ref=ref, code=skill, action=action,
                           prior=prior, level=level)

    assert run() == {'before': 0, 'after': 0, 'after_handle': 0}
    assert run(1, 0, 2)['after'] == 2
    with pytest.raises(RuntimeError, match='错误 24'):
        run(3, 1, 3)
    assert run(3, 2, 3)['after'] == 3
    assert run(2, 3, 0)['after_handle'] == 0
    assert changes == [(unit, skill, level) for level in (1, 2, 3, 0)]
    struct.pack_into('<Q', buffer, full_offset, ref.handle.value + 1)
    with pytest.raises(RuntimeError, match='错误 1237'):
        run(1, 0, 3)
    assert state['level'] == 0
