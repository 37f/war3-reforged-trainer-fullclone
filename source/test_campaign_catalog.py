"""Real nested MPQ fixtures, created only under pytest's temporary folder."""
import ctypes as C
import hashlib
from pathlib import Path
import struct

import pytest

from test_custom_objects import obj_file
from war3_campaign_catalog import StormArchive, list_campaign, detect_campaign


def make_mpq(path, entries):
    dll = C.WinDLL(str(Path(__file__).parent / 'tools' / 'StormLib.dll'), use_last_error=True)
    dll.SFileCreateArchive.argtypes = [C.c_wchar_p,C.c_uint32,C.c_uint32,C.POINTER(C.c_void_p)]
    dll.SFileCreateArchive.restype = C.c_bool
    dll.SFileCreateFile.argtypes = [C.c_void_p,C.c_char_p,C.c_uint64,C.c_uint32,C.c_uint32,C.c_uint32,C.POINTER(C.c_void_p)]
    dll.SFileCreateFile.restype = C.c_bool
    dll.SFileWriteFile.argtypes = [C.c_void_p,C.c_void_p,C.c_uint32,C.c_uint32]
    dll.SFileWriteFile.restype = C.c_bool
    dll.SFileFinishFile.argtypes = [C.c_void_p]
    dll.SFileFinishFile.restype = C.c_bool
    dll.SFileCloseArchive.argtypes = [C.c_void_p]
    dll.SFileCloseArchive.restype = C.c_bool
    archive=C.c_void_p()
    assert dll.SFileCreateArchive(str(path),0x100000,64,C.byref(archive)), C.get_last_error()
    try:
        for name,data in entries.items():
            file=C.c_void_p()
            assert dll.SFileCreateFile(archive,name.encode('utf8'),0,len(data),0,0x200,C.byref(file))
            assert dll.SFileWriteFile(file,C.create_string_buffer(data),len(data),2)
            assert dll.SFileFinishFile(file)
    finally:
        assert dll.SFileCloseArchive(archive)


def w3f():
    s=lambda value:value.encode('utf8')+b'\0'
    return (struct.pack('<iii',1,0,0)+s('战役')+s('')+s('作者')+s('')
        +struct.pack('<ii',0,0)+s('')+s('')+struct.pack('<i',0)+s('')
        +struct.pack('<i3f4si',0,0.,0.,0.,b'\0'*4,0)
        +struct.pack('<ii',1,1)+s('第一章')+s('测试地图')+s('Maps\\One.w3x')+struct.pack('<i',0))


@pytest.fixture
def campaign(tmp_path):
    inner=tmp_path/'inner.w3x'
    make_mpq(inner, {'war3map.w3u':obj_file(records=[('hfoo','X001',[('unam','TRIGSTR_1')])]),
        'war3map.wts':b'STRING 1\n{\nChapter Unit\n}\n','war3map.w3a':b'broken'})
    outer=tmp_path/'中文战役.w3n'
    make_mpq(outer, {'war3campaign.w3f':w3f(), 'Maps\\One.w3x':inner.read_bytes(),
        'war3campaign.w3t':obj_file('item',[('ckng','I001',[('unam','战役物品')])])})
    return outer


def test_nested_campaign_detection_is_readonly_and_partial(campaign):
    before=hashlib.sha256(campaign.read_bytes()).hexdigest()
    info=list_campaign(campaign)
    assert len(info.chapters)==1 and '第一章' in info.chapters[0].title
    result=detect_campaign(info,info.chapters[0])
    assert [(x.rawcode,x.name) for x in result.entries['unit']]==[('X001','Chapter Unit')]
    assert [(x.rawcode,x.name) for x in result.entries['item']]==[('I001','战役物品')]
    assert result.partial and any('war3map.w3a' in x for x in result.issues)
    assert hashlib.sha256(campaign.read_bytes()).hexdigest()==before


def test_changed_campaign_rejected(campaign):
    info=list_campaign(campaign)
    with campaign.open('ab') as f:
        f.write(b'changed')
    with pytest.raises(ValueError,match='变化'):
        detect_campaign(info,info.chapters[0])


def test_archive_missing_is_distinct_from_size_error(campaign):
    with StormArchive(campaign) as archive:
        assert archive.read('not-there') is None
        with pytest.raises(ValueError,match='上限'):
            archive.read('Maps\\One.w3x',max_bytes=1)


def test_listfile_can_discover_chapter_without_w3f(tmp_path):
    inner=tmp_path/'inner.w3x'; make_mpq(inner,{})
    outer=tmp_path/'outer.w3n'; make_mpq(outer,{'Two.w3x':inner.read_bytes()})
    info=list_campaign(outer)
    assert [x.path for x in info.chapters]==['Two.w3x']
    assert info.issues
    result=detect_campaign(info,info.chapters[0])
    assert result.partial and all(not rows for rows in result.entries.values())


def test_non_campaign_and_invalid_chapter_rejected(campaign,tmp_path):
    path=tmp_path/'bad.w3n'; path.write_bytes(b'not an archive')
    with pytest.raises((ValueError,OSError)):
        list_campaign(path)
    info=list_campaign(campaign)
    from war3_campaign_catalog import Chapter
    with pytest.raises(ValueError):
        detect_campaign(info,Chapter('not listed','../outside.w3x'))
