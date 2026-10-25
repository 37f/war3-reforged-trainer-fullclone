"""R23 local CASC boundary: native I/O is doubled; policy/limits stay real."""
import ctypes as C
import hashlib
import importlib
from pathlib import Path

import pytest


def build_info(path,rows=None):
    header='Active!DEC:1|Build Key!HEX:16|Version!STRING:0|Product!STRING:0|Tags!STRING:0\n'
    path.joinpath('.build.info').write_text(header+(rows or
        '1|9a94ff7d25781db6c09190cd69d52458|2.0.4.23745|w3|zhCN text?\n'),encoding='utf8')


class LocalCasc:
    """A disk-API double, with real opaque handle lifetime and typed buffers."""
    def __init__(self,module,root,data=b'function main takes nothing returns nothing\nendfunction\n'):
        self.module,self.root,self.data=module,root,data
        self.resources=set();self.short=False;self.bad_key=False;self.not_local=False

    def CascOpenStorage(self,path,locale,out):
        assert Path(path)==self.root
        out._obj.value=100;self.resources.add(100);return True

    def CascCloseStorage(self,handle):
        self.resources.remove(handle.value);return True

    def CascOpenFile(self,storage,name,locale,flags,out):
        assert storage.value==100 and flags==0
        if name!=b'war3.w3mod:campaign\\classic\\roc\\prologue01.w3m':
            C.set_last_error(2);return False
        out._obj.value=101;self.resources.add(101);return True

    def CascCloseFile(self,handle):
        self.resources.remove(handle.value);return True

    def CascGetFileSize64(self,handle,out):
        if self.not_local:C.set_last_error(2);return False
        out._obj.value=len(self.data);return True

    def CascGetFileInfo(self,handle,kind,buffer,size,needed):
        assert kind==2
        info=self.module._FileInfo()
        key=hashlib.md5(self.data).digest()
        if self.bad_key:key=b'X'*16
        info.CKey[:]=key;info.EKey[:]=b'E'*16
        info.DataFileName=b'data.017';info.StorageOffset=0x400000021
        info.SegmentOffset=33;info.ContentSize=len(self.data);info.EncodedSize=len(self.data)+30
        info.SegmentIndex=17;info.SpanCount=1
        needed._obj.value=C.sizeof(info);C.memmove(buffer,C.byref(info),C.sizeof(info));return True

    def CascReadFile(self,handle,buffer,amount,out):
        if self.short:out._obj.value=max(0,amount-1);return True
        C.memmove(buffer,self.data,amount);out._obj.value=amount;return True


@pytest.fixture
def casc(tmp_path,monkeypatch):
    module=importlib.import_module('war3_casc_source');build_info(tmp_path)
    native=LocalCasc(module,tmp_path);monkeypatch.setattr(module,'_load_library',lambda:native)
    return module,tmp_path,native


def test_build_selects_unique_active_warcraft_build_and_records_identity(tmp_path):
    module=importlib.import_module('war3_casc_source');build_info(tmp_path,
        '0|aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|1.0.0.0|w3|enUS\n'
        '1|9a94ff7d25781db6c09190cd69d52458|2.0.4.23745|w3|zhCN text?\n')
    identity=module.read_build_identity(tmp_path)
    assert identity.build_key=='9a94ff7d25781db6c09190cd69d52458'
    assert identity.version=='2.0.4.23745' and identity.product=='w3'
    assert identity.build_info_sha256==hashlib.sha256((tmp_path/'.build.info').read_bytes()).hexdigest()


@pytest.mark.parametrize('rows',[
    '1|not-a-key|2.0.4.23745|w3|zhCN\n',
    '1|aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|2.0.4.23745|wow|zhCN\n',
    '1|aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|2.0.4.23745|w3|zhCN\n'
    '1|bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb|2.0.4.23745|w3|zhCN\n',
])
def test_invalid_or_ambiguous_active_build_is_rejected(tmp_path,rows):
    module=importlib.import_module('war3_casc_source');build_info(tmp_path,rows)
    with pytest.raises(module.CascUnavailable):module.read_build_identity(tmp_path)


def test_member_maps_active_path_and_rejects_namespace_or_path_escape():
    module=importlib.import_module('war3_casc_source')
    assert module.official_member('Campaign/Classic/ROC/Prologue01.w3m')=='war3.w3mod:campaign\\classic\\roc\\prologue01.w3m'
    for path in ('C:/Campaign/one.w3m','../Campaign/one.w3m','Campaign/../one.w3m',
                 'other.w3mod:Campaign/one.w3m','Campaign/one.w3m\x00x','Maps/one.w3x'):
        with pytest.raises(module.CascUnavailable):module.official_member(path)


def test_read_preserves_content_and_returns_storage_proof(casc):
    module,root,native=casc;identity=module.read_build_identity(root)
    with module.CascArchive(root,identity) as archive:
        entry=archive.read_entry(module.official_member('Campaign/Classic/ROC/Prologue01.w3m'),1024)
        assert entry.data==b'function main takes nothing returns nothing\nendfunction\n'
        assert entry.segment_index==17 and entry.segment_offset==33 and entry.span_count==1
        assert archive.read('war3.w3mod:scripts\\missing.j',1024) is None
    assert native.resources==set()


@pytest.mark.parametrize('fault',['short','bad_key','not_local'])
def test_failed_or_inconsistent_resource_never_returns_success_and_closes_handles(casc,fault):
    module,root,native=casc;setattr(native,fault,True)
    with pytest.raises(module.CascUnavailable):
        with module.CascArchive(root,module.read_build_identity(root)) as archive:
            archive.read_entry(module.official_member('Campaign/Classic/ROC/Prologue01.w3m'),1024)
    assert native.resources==set()


def test_resource_over_limit_rejected_before_allocating_or_reading(casc):
    module,root,native=casc
    with pytest.raises(module.CascUnavailable,match='上限'):
        with module.CascArchive(root,module.read_build_identity(root)) as archive:
            archive.read('war3.w3mod:campaign\\classic\\roc\\prologue01.w3m',1)
    assert native.resources==set()


def test_changed_build_after_open_invalidates_even_a_successful_native_read(casc):
    module,root,native=casc
    with module.CascArchive(root,module.read_build_identity(root)) as archive:
        build_info(root,'1|bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb|2.0.4.23745|w3|zhCN\n')
        with pytest.raises(module.CascUnavailable,match='变化'):
            archive.read('war3.w3mod:campaign\\classic\\roc\\prologue01.w3m',1024)
    assert native.resources==set()


def test_cancellation_and_timeout_do_not_leave_native_resources(casc):
    module,root,native=casc
    with pytest.raises(module.CascUnavailable,match='取消'):
        with module.CascArchive(root,module.read_build_identity(root),cancelled=lambda:True):pass
    with pytest.raises(module.CascUnavailable,match='时间'):
        with module.CascArchive(root,module.read_build_identity(root),deadline=0):pass
    assert native.resources==set()
