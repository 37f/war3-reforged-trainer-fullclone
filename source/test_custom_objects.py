"""Hand-built object records pin binary boundaries and cross-layer names."""
import struct

import pytest

from war3_custom_objects import parse_object_data, parse_wts, merge_objects


def obj_file(kind="unit", records=(), version=2, original=()):
    def table(rows, custom):
        out = struct.pack('<i', len(rows))
        for base, rawcode, fields in rows:
            out += base.encode('latin1') + (rawcode.encode('latin1') if custom else b'\0'*4)
            if version == 3:
                out += struct.pack('<ii', 1, 0)
            out += struct.pack('<i', len(fields))
            for field, value in fields:
                out += field.encode() + struct.pack('<i', 3 if isinstance(value, str) else 0)
                if kind == 'ability':
                    out += struct.pack('<ii', 1, 0)
                out += value.encode('utf8') + b'\0' if isinstance(value, str) else struct.pack('<i', value)
                out += rawcode.encode('latin1') if custom else b'\0'*4
        return out
    return struct.pack('<i', version) + table(original, False) + table(records, True)


@pytest.mark.parametrize('kind,field,base', [('unit','unam','hfoo'),('item','unam','ckng'),('ability','anam','AHhb')])
@pytest.mark.parametrize('version', [1,2,3])
def test_new_objects_parse_each_kind_and_version(kind, field, base, version):
    definitions = parse_object_data(obj_file(kind, [(base,'X001',[(field,'自定义')])], version), kind)
    rows = merge_objects(definitions, (), {}, {}, kind)
    assert [(x.rawcode,x.name,x.base_id,x.object_type) for x in rows] == [('X001','自定义',base,'新增')]


def test_scoped_strings_and_field_overlay_keep_campaign_name():
    campaign = parse_object_data(obj_file(records=[('hfoo','X001',[('unam','TRIGSTR_1')])]), 'unit')
    chapter = parse_object_data(obj_file(records=[('hfoo','X001',[('uhpm',999)])]), 'unit')
    row = merge_objects(campaign, chapter, {1:'战役名'}, {1:'章节名'}, 'unit')[0]
    assert (row.name,row.source) == ('战役名','战役公共 + 所选章节')
    chapter = parse_object_data(obj_file(records=[('hfoo','X001',[('unam','TRIGSTR_1')])]), 'unit')
    assert merge_objects(campaign, chapter, {1:'战役名'}, {1:'章节名'}, 'unit')[0].name == '章节名'


def test_original_changes_not_miscounted_as_new():
    defs = parse_object_data(obj_file(original=[('hfoo','hfoo',[('unam','步兵甲')])]), 'unit')
    row = merge_objects((), defs, {}, {}, 'unit')[0]
    assert (row.rawcode,row.object_type,row.name) == ('hfoo','原版改动','步兵甲')


def test_chapter_original_table_can_modify_a_campaign_custom_object():
    campaign = parse_object_data(obj_file(records=[('hfoo','X001',[('unam','公共名字')])]), 'unit')
    chapter = parse_object_data(obj_file(original=[('X001','X001',[('unam','章节名字')])]), 'unit')
    row = merge_objects(campaign, chapter, {}, {}, 'unit')[0]
    assert (row.name,row.base_id,row.object_type,row.copyable) == ('章节名字','hfoo','新增',True)


def test_inherited_name_and_color_codes():
    defs = parse_object_data(obj_file(records=[('hfoo','X001',[('unam','|cffff0000队长|r')]),('X001','X002',[])]), 'unit')
    rows = {x.rawcode:x for x in merge_objects(defs, (), {}, {}, 'unit')}
    assert rows['X002'].name == '队长'
    assert '继承' in rows['X002'].note


def test_cycle_and_conflicting_bases_are_visible():
    defs = parse_object_data(obj_file(records=[('X002','X001',[]),('X001','X002',[])]), 'unit')
    assert all('循环' in x.note for x in merge_objects(defs, (), {}, {}, 'unit'))
    other = parse_object_data(obj_file(records=[('hfoo','X001',[])]), 'unit')
    row = merge_objects(defs, other, {}, {}, 'unit')[0]
    assert '冲突' in row.note and not row.copyable


def test_unresolved_string_remains_visible():
    defs = parse_object_data(obj_file(records=[('hfoo','X001',[('unam','TRIGSTR_7')])]), 'unit')
    row = merge_objects(defs, (), {}, {}, 'unit')[0]
    assert row.name == 'TRIGSTR_7' and '未解析' in row.note


def test_invalid_rawcode_is_not_replaced_with_fake_copyable_id():
    defs = parse_object_data(obj_file(records=[('hfoo','\x80ABC',[('unam','名字')])]), 'unit')
    row = merge_objects(defs, (), {}, {}, 'unit')[0]
    assert not row.copyable and '80414243' in row.rawcode


def test_wts_multiline_and_duplicate_detection():
    assert parse_wts(b'\xef\xbb\xbf// header\nSTRING 1\n{\nhello\nworld\n}\n') == {1:'hello\nworld'}
    with pytest.raises(ValueError, match='重复'):
        parse_wts(b'STRING 1\n{\na\n}\nSTRING 1\n{\nb\n}\n')


def test_world_editor_wts_comments_between_header_and_brace():
    assert parse_wts(b'STRING 15\r\n// Unit name\r\n{\r\nKeagan\r\n}\r\n') == {15:'Keagan'}
    assert parse_wts(b'STRING 15\r\n// Name (\x1e\x1eeditor metadata)\r\n{\r\nName\r\n}\r\n') == {15:'Name'}


@pytest.mark.parametrize('rawcode', ['0x12','0XAB'])
def test_rawcodes_ambiguous_in_existing_input_syntax_are_not_copyable(rawcode):
    defs=parse_object_data(obj_file(records=[('hfoo',rawcode,[('unam','Name')])]),'unit')
    row=merge_objects(defs,(),{}, {},'unit')[0]
    assert row.rawcode==rawcode and not row.copyable
    assert '输入' in row.note


def test_old_editor_opaque_trailer_is_not_a_new_object_id():
    data=obj_file(records=[('hfoo','X001',[('unam','Name')])])
    data=data[:-4]+b'nskg'
    row=merge_objects(parse_object_data(data,'unit'),(),{}, {},'unit')[0]
    assert (row.rawcode,row.name)==('X001','Name')


@pytest.mark.parametrize('data', [b'',struct.pack('<iii',4,0,0),struct.pack('<ii',2,-1),obj_file()[:-1],obj_file()+b'garbage'])
def test_malformed_or_unsupported_records_rejected(data):
    with pytest.raises(ValueError):
        parse_object_data(data,'unit')


def test_duplicate_object_ids_rejected():
    with pytest.raises(ValueError, match='重复'):
        parse_object_data(obj_file(records=[('hfoo','X001',[]),('hfoo','X001',[])]),'unit')


def test_bad_field_type_and_truncated_trailer_rejected():
    data = obj_file(records=[('hfoo','X001',[('unam','x')])])
    with pytest.raises(ValueError):
        parse_object_data(data[:-1],'unit')
    data = data.replace(b'unam\x03\0\0\0',b'unam\x09\0\0\0')
    with pytest.raises(ValueError):
        parse_object_data(data,'unit')
