"""Ability query or mutation for one previously bound hero."""
import struct

from war3_ability_protocol import SIGNATURES as ABILITIES

SIGNATURES = (*ABILITIES, ('GetUnitTypeId', '(Hunit;)I'))
WORK = struct.Struct('<13Q5I2i3I2Q')
ABI = struct.pack('<3I', 0x46485301, 216, WORK.size)


def build_work(entries, tls, resolver, ref, handle, code, action, prior, level):
    handlers = []
    for name, signature in SIGNATURES:
        entry = entries.get(name)
        if entry is None or entry.name != name or entry.signature != signature:
            raise ValueError('英雄技能接口签名不同：' + name)
        handlers.append(entry.handler)
    payload = WORK.pack(*handlers, tls, resolver, ref.address.value, ref.handle.value, handle,
                        ref.rawcode, code, action, prior, level, 0, 0, 0, 0, 0, 0, 0)
    validate_work(payload)
    return payload


def validate_work(payload):
    if len(payload) != WORK.size:
        raise ValueError('候选英雄技能请求大小无效')
    data = WORK.unpack(payload)
    tls, resolver, obj, full, handle, kind, code, action, prior, level = data[8:18]
    if (any(not 0x10000 <= p < 0x800000000000 for p in (*data[:8], tls, resolver, obj))
            or tls % 8 or obj % 8 or not all((full, handle, kind, code)) or action not in range(4)
            or prior > 100000 or level > 100000 or any(data[18:])
            or action == 0 and (prior or level) or action == 1 and (prior or not level)
            or action == 2 and (not prior or level) or action == 3 and (not prior or not level)):
        raise ValueError('候选英雄技能请求无效')


def decode_work(payload, count, *, handle, ref, code, action, prior, level):
    data = WORK.unpack(payload)
    if data[10:18] != (ref.address.value, ref.handle.value, handle, ref.rawcode, code, action, prior, level):
        raise RuntimeError('候选英雄技能回执身份不一致')
    before, after, error, done, reserved, before_handle, after_handle = data[18:]
    if (error or done != 1 or reserved or count != 1 or before < 0
            or (action == 0 and (after, after_handle) != (before, before_handle))
            or (action != 0 and (before != prior or after != level))
            or (action == 1 and (before_handle or not after_handle))
            or (action == 2 and after_handle)
            or (action == 3 and after_handle != before_handle)):
        raise RuntimeError(f'候选英雄技能未确认（错误 {error}）')
    return dict(before=before, after=after, after_handle=after_handle)
