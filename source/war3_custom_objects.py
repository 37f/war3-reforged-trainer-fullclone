"""R20: bounded, read-only Warcraft object definitions; no process access."""
from __future__ import annotations

from dataclasses import dataclass
import re
import struct

from war3_id_catalog import ID_CATALOG

MAX_OBJECT_BYTES = 32 * 1024 * 1024
MAX_STRING_BYTES = 1024 * 1024
MAX_OBJECTS = 100000
MAX_MODIFICATIONS = 1000000


class Reader:
    def __init__(self, data: bytes, limit: int = MAX_OBJECT_BYTES):
        if len(data) > limit:
            raise ValueError('数据超过读取大小上限')
        self.data, self.pos = data, 0

    def raw(self, size: int) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError(f'数据截断，偏移 {self.pos}')
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def integer(self) -> int:
        return struct.unpack('<i', self.raw(4))[0]

    def count(self, maximum: int) -> int:
        value = self.integer()
        if not 0 <= value <= maximum:
            raise ValueError(f'记录数量越界：{value}')
        return value

    def string(self) -> str:
        end = self.data.find(b'\0', self.pos, self.pos + MAX_STRING_BYTES + 1)
        if end < 0:
            raise ValueError('字符串未结束或超过长度上限')
        raw = self.raw(end - self.pos)
        self.raw(1)
        # Preserve undecodable bytes visibly; never silently invent a name.
        return raw.decode('utf-8', 'backslashreplace')

    def finish(self) -> None:
        if self.pos != len(self.data):
            raise ValueError(f'存在未识别的尾部数据：{len(self.data) - self.pos} 字节')


@dataclass(frozen=True)
class ObjectDefinition:
    rawcode: bytes
    base: bytes
    custom: bool
    fields: dict[tuple[bytes, int, int], str | int | float]


@dataclass(frozen=True)
class CustomObjectEntry:
    rawcode: str
    name: str
    base_id: str
    object_type: str
    source: str
    note: str = ''
    copyable: bool = True


def display_rawcode(value: bytes) -> str:
    return value.decode('ascii') if all(33 <= c <= 126 for c in value) else f'<0x{value.hex()}>'


def parse_object_data(data: bytes, kind: str) -> tuple[ObjectDefinition, ...]:
    if kind not in ('unit', 'item', 'ability'):
        raise ValueError('未知对象类别')
    reader = Reader(data)
    version = reader.integer()
    if version not in (1, 2, 3):
        raise ValueError(f'不支持的对象格式版本：{version}')
    result, seen, total_mods = [], set(), 0
    for custom in (False, True):
        count = reader.count(MAX_OBJECTS - len(result))
        for _ in range(count):
            base, new = reader.raw(4), reader.raw(4)
            rawcode = new if custom else base
            if base == b'\0'*4 or rawcode == b'\0'*4 or (not custom and new != b'\0'*4):
                raise ValueError('对象 ID 无效')
            if rawcode in seen:
                raise ValueError(f'重复对象 ID：{display_rawcode(rawcode)}')
            seen.add(rawcode)
            fields = {}
            sets = reader.count(128) if version == 3 else 1
            for _ in range(sets):
                if version == 3:
                    reader.integer()  # Reforged object set flag.
                modifications = reader.count(MAX_MODIFICATIONS - total_mods)
                total_mods += modifications
                for _ in range(modifications):
                    field, field_type = reader.raw(4), reader.integer()
                    level, pointer = (reader.integer(), reader.integer()) if kind == 'ability' else (0, 0)
                    if field_type == 3:
                        value = reader.string()
                    elif field_type == 0:
                        value = reader.integer()
                    elif field_type in (1, 2):
                        value = struct.unpack('<f', reader.raw(4))[0]
                    else:
                        raise ValueError(f'未知字段类型：{field_type}')
                    # The format stores an opaque uint32 here. Old editors can
                    # leave another rawcode (e.g. nskg), so equality is not validity.
                    reader.raw(4)
                    key = field, level, pointer
                    if key in fields and fields[key] != value:
                        raise ValueError('同一对象含多个不同值的字段，无法唯一解析')
                    fields[key] = value
            result.append(ObjectDefinition(rawcode, base, custom, fields))
    reader.finish()
    return tuple(result)


def parse_wts(data: bytes) -> dict[int, str]:
    if len(data) > MAX_OBJECT_BYTES:
        raise ValueError('字符串表超过大小上限')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('字符串表不是可确定的 UTF-8 编码') from exc
    # Line parser permits World Editor comments outside string bodies without
    # stripping literal // text from names, and avoids unbounded regex backtracking.
    # Only CR/LF are WTS line endings. Control bytes such as U+001E can
    # occur inside editor comments and must not create artificial lines.
    lines, result, pos = text.split('\n'), {}, 0
    def skip_comments(index):
        while index < len(lines) and (not lines[index].strip() or lines[index].lstrip().startswith('//')):
            index += 1
        return index
    while (pos := skip_comments(pos)) < len(lines):
        match = re.fullmatch(r'\s*STRING\s+(\d+)\s*(\{)?\s*(?://[^\r\n]*)?', lines[pos].rstrip('\r\n'))
        if not match:
            raise ValueError('字符串表存在未识别记录')
        key = int(match[1]); pos += 1
        if not match[2]:
            pos = skip_comments(pos)
            if pos >= len(lines) or lines[pos].strip() != '{':
                raise ValueError('字符串表缺少正文开始标记')
            pos += 1
        body, size = [], 0
        while pos < len(lines) and lines[pos].strip() != '}':
            size += len(lines[pos].encode('utf8'))
            if size > MAX_STRING_BYTES:
                raise ValueError('字符串表超过长度上限')
            body.append(lines[pos]); pos += 1
        if pos >= len(lines):
            raise ValueError('字符串表缺少正文结束标记')
        pos += 1
        value='\n'.join(body).removesuffix('\r')
        if key in result:
            raise ValueError(f'字符串表重复编号：{key}')
        if not 0 <= key <= 0xffffffff or len(result) >= MAX_OBJECTS:
            raise ValueError('字符串表超过数量或长度上限')
        result[key] = value
    return result


def resolve_string(value: str, strings: dict[int, str]) -> tuple[str, str]:
    match = re.fullmatch(r'TRIGSTR_(\d+)', value)
    if match:
        key = int(match[1])
        if key not in strings:
            return value, '名称字符串未解析'
        value = strings[key]
    note = '名称含非 UTF-8 字节' if re.search(r'\\x[0-9a-f]{2}', value) else ''
    return re.sub(r'\|c[0-9A-Fa-f]{8}|\|r', '', value, flags=re.I), note


def merge_objects(campaign, chapter, campaign_strings, chapter_strings, kind: str) -> tuple[CustomObjectEntry, ...]:
    """Overlay fields with their WTS scope attached, then resolve inheritance."""
    merged = {}
    for layer, definitions, strings in (('战役公共', campaign, campaign_strings), ('所选章节', chapter, chapter_strings)):
        for definition in definitions:
            rawcode = definition.rawcode
            if rawcode not in merged:
                merged[rawcode] = [definition, {}, [], False]
            previous, fields, sources, conflict = merged[rawcode]
            # A chapter original-table row may modify an object created by the campaign.
            existing_custom_override = previous.custom and not definition.custom and definition.base == rawcode
            if not existing_custom_override:
                conflict |= previous.base != definition.base or previous.custom != definition.custom
            for key, value in definition.fields.items():
                fields[key] = (value, strings)
            sources.append(layer)
            merged[rawcode] = [previous if existing_custom_override else definition, fields, sources, conflict]
    if len(merged) > MAX_OBJECTS:
        raise ValueError('合并对象数量超过上限')
    generic = {entry.rawcode: entry.name_zh or entry.name_en for entry in ID_CATALOG[kind]}
    name_field = b'anam' if kind == 'ability' else b'unam'

    def name_for(rawcode, visited):
        if rawcode in visited or len(visited) >= 64:
            return '名称无法解析', '基础对象继承循环或超过深度上限'
        record = merged.get(rawcode)
        if record is None:
            name = generic.get(display_rawcode(rawcode))
            return (name, '名称回退到通用目录') if name else ('名称缺失', '基础对象未找到')
        definition, fields, _, conflict = record
        if conflict:
            return '定义冲突', '战役与章节的基础 ID 或对象类型冲突'
        names = sorted((key, value) for key, value in fields.items() if key[0] == name_field)
        if names:
            value, strings = names[0][1]
            if isinstance(value, str) and value:
                return resolve_string(value, strings)
        if definition.base == rawcode:
            return name_for_base(rawcode)
        name, note = name_for(definition.base, visited | {rawcode})
        return name, '继承基础名称' + (f'；{note}' if note else '')

    def name_for_base(rawcode):
        name = generic.get(display_rawcode(rawcode))
        return (name, '名称回退到通用目录') if name else ('名称缺失', '名称缺失：通用目录无对应名称')

    result = []
    for rawcode, (definition, _, sources, conflict) in sorted(merged.items()):
        name, note = name_for(rawcode, set())
        display = display_rawcode(rawcode)
        ascii_id = all(33 <= c <= 126 for c in rawcode)
        ambiguous_input = display.lower().startswith('0x')
        copyable = not conflict and ascii_id and not ambiguous_input
        if not copyable and not conflict:
            reason = 'ID 与现有输入框的十六进制语法冲突，禁止直接复制' if ambiguous_input else 'ID 不是四个可显示 ASCII 字符，禁止复制为指令 ID'
            note = (note + '；' if note else '') + reason
        result.append(CustomObjectEntry(display, name, display_rawcode(definition.base),
            '新增' if definition.custom else '原版改动', ' + '.join(sources), note, copyable))
    return tuple(result)
