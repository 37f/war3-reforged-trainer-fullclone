"""R22 source contracts/profile proof use owned memory; never scan/inject a game."""
from dataclasses import replace
import hashlib
import struct
import time
import pytest

from war3_current_map_script import (ScriptSnapshot,CurrentMapScriptClient,
    read_profiled_map_metadata,SourceUnavailable)


DIFFICULTY_TAIL=bytes.fromhex('488b055a99f00148b9c9aeef3dfdbb3a364833c1483305aa7bf8017511b957000000e8c63e69ff33c04883c428c3488b80702600000fb6406e4883c428c3')
CAMPAIGN_TEST=bytes.fromhex('33c0488d15b79b1f023805b19b1f02480f45c24885c0740c80b94f300000007503b001c332c0c3')


class ProfileMemory:
    base=0x180000000
    world=0x600000000
    config=0x600010000
    entry=0x600020000
    chars=0x600030000
    def __init__(self):
        self.spans={}
        dos=bytearray(64);dos[:2]=b'MZ';struct.pack_into('<I',dos,0x3c,0x80);self.put(self.base,dos)
        pe=bytearray(0x108);pe[:4]=b'PE\0\0';struct.pack_into('<H',pe,4,0x8664);struct.pack_into('<I',pe,8,0x69e54471)
        struct.pack_into('<H',pe,24,0x20b);struct.pack_into('<I',pe,80,0xdd20000);self.put(self.base+0x80,pe)
        self.put(self.base+0xc50003,DIFFICULTY_TAIL);self.put(self.base+0x9dde50,CAMPAIGN_TEST)
        self.q(self.base+0x2b59964,self.world^0x363abbfd3defaec9^123)
        self.q(self.base+0x2bd7bc8,123)
        self.q(self.world,self.base+0x23d0690);self.q(self.world+0x2670,self.config)
        self.put(self.world+0x304f,b'\0')
        self.q(self.config,self.base+0x23d0508);self.q(self.config+0x40,self.base+0x21dea60)
        self.q(self.config+0x50,self.entry);self.q(self.entry,self.base+0x21de9b0)
        self.q(self.entry+0x38,self.chars)
        self.put(self.chars,b'chapter3.w3x\0'+b'\0'*4096)
        self.put(self.base+0x2bd7a10,'C:/Campaigns/战役.w3n'.encode()+b'\0'*256)
    def put(self,address,value):self.spans[address]=bytes(value)
    def q(self,address,value):self.put(address,struct.pack('<Q',value))
    def read(self,address,count):
        for start,value in reversed(tuple(self.spans.items())):
            if start<=address and address+count<=start+len(value):return value[address-start:address-start+count]
        raise OSError('unreadable synthetic span')


def test_profile_metadata_binds_current_config_and_campaign_without_writes():
    memory=ProfileMemory();before=dict(memory.spans)
    m=read_profiled_map_metadata(memory.read,memory.base,123)
    assert m.map_path=='chapter3.w3x' and m.campaign_path=='C:/Campaigns/战役.w3n'
    assert m.is_campaign and m.session_token==123 and m.fingerprint
    assert memory.spans==before
    memory.put(memory.chars,b'chapter4.w3x\0'+b'\0'*4096)
    assert read_profiled_map_metadata(memory.read,memory.base,123).fingerprint!=m.fingerprint


@pytest.mark.parametrize('change',('code','version','world_type','config_type','string_type','unreadable','path'))
def test_unverified_source_profile_or_path_is_rejected(change):
    m=ProfileMemory()
    if change=='code':m.put(m.base+0x9dde50,b'\x90'*39)
    elif change=='version':m.put(m.base+0x80,b'PE\0\0'+b'\0'*260)
    elif change=='world_type':m.q(m.world,0)
    elif change=='config_type':m.q(m.config,0)
    elif change=='string_type':m.q(m.entry,0)
    elif change=='unreadable':m.q(m.entry+0x38,0x100000)
    else:m.put(m.chars,b'../escape.w3x\0'+b'\0'*4096)
    with pytest.raises(SourceUnavailable):read_profiled_map_metadata(m.read,m.base,123)


def test_stale_campaign_path_is_not_used_for_standalone_game():
    m=ProfileMemory();m.put(m.world+0x304f,b'\1')
    metadata=read_profiled_map_metadata(m.read,m.base,123)
    assert not metadata.is_campaign and metadata.campaign_path==''
    with pytest.raises(SourceUnavailable):read_profiled_map_metadata(m.read,m.base,0)


def test_observed_loaded_header_machine_marker_is_supported():
    m=ProfileMemory();pe=bytearray(m.read(m.base+0x80,0x108));struct.pack_into('<H',pe,4,0x200)
    m.put(m.base+0x80,pe)
    assert read_profiled_map_metadata(m.read,m.base,123).map_path=='chapter3.w3x'


def snapshot(identity='game',language='jass'):
    script=b'function main takes nothing returns nothing\nendfunction\n';strings=b''
    return ScriptSnapshot(identity,123,'campaign.w3n::chapter3.w3x',language,script,strings,
        hashlib.sha256(script).hexdigest(),hashlib.sha256(strings).hexdigest(),time.monotonic(),
        ('active-map/config-and-owned-file',),())


def test_client_checks_identity_hashes_provenance_and_cancellation():
    s=snapshot();calls=[]
    def query(*,snapshot=None,cancelled=lambda:False):
        calls.append(snapshot);return s if snapshot is None else True
    c=CurrentMapScriptClient(query,lambda:'game')
    assert c.read()==s and c.check(s)
    with pytest.raises(RuntimeError,match='取消'):c.read(lambda:True)
    for invalid in (replace(s,script=b'changed'),replace(s,identity='other'),replace(s,provenance=()),replace(s,session_token=0)):
        c=CurrentMapScriptClient(lambda **kw:invalid,lambda:'game')
        with pytest.raises((ValueError,RuntimeError)):c.read()


def test_client_cannot_publish_after_connection_or_cancel_changes():
    identity=['old'];cancel=[False]
    def query(**kwargs):identity[0]='new';return snapshot('old')
    with pytest.raises(RuntimeError,match='连接'):CurrentMapScriptClient(query,lambda:identity[0]).read()
    def query(**kwargs):cancel[0]=True;return snapshot()
    with pytest.raises(RuntimeError,match='取消'):CurrentMapScriptClient(query,lambda:'game').read(lambda:cancel[0])


def test_source_size_and_deadline_are_explicit(monkeypatch):
    import war3_current_map_script as m
    s=snapshot();monkeypatch.setattr(m,'MAX_SCRIPT_BYTES',10)
    with pytest.raises(ValueError,match='上限'):CurrentMapScriptClient(lambda **kw:s,lambda:'game').read()


def test_lua_is_a_real_source_but_not_silently_relabelled_jass():
    s=snapshot(language='lua')
    assert CurrentMapScriptClient(lambda **kw:s,lambda:'game').read().language=='lua'


@pytest.mark.parametrize('token',(-1,2**64,True))
def test_snapshot_session_token_is_an_unsigned_nonzero_word(token):
    s=replace(snapshot(),session_token=token)
    with pytest.raises(ValueError):CurrentMapScriptClient(lambda **kw:s,lambda:'game').read()


def test_source_deadline_covers_slow_provider_and_check_revalidates_identity(monkeypatch):
    import war3_current_map_script as m
    clock=[100.];monkeypatch.setattr(m.time,'monotonic',lambda:clock[0]);s=snapshot()
    def slow(**kw):clock[0]+=61;return replace(s,validated_at=clock[0])
    with pytest.raises(TimeoutError):CurrentMapScriptClient(slow,lambda:'game').read()
    identity=['game']
    def changed(**kw):identity[0]='other';return True
    assert not CurrentMapScriptClient(changed,lambda:identity[0]).check(s)


def test_owned_file_binding_is_exact_and_rejects_recent_or_replaced_sources():
    from war3_current_map_script import MapSourceMetadata,GameSourceFile,bind_owned_source
    m=MapSourceMetadata(123,'proof','chapter.w3x','C:/Campaigns/a.w3n',True)
    f=GameSourceFile('C:/Campaigns/a.w3n',(1,2),100,10,20)
    b=bind_owned_source(m,(f,),lambda path:f)
    assert b.member=='chapter.w3x' and b.file==f
    for rows,local in (((),f),((f,),replace(f,file_id=(1,3))),((replace(f,modified=21),),replace(f,modified=21))):
        with pytest.raises(SourceUnavailable):bind_owned_source(m,rows,lambda path:local)


def test_standalone_relative_path_requires_unique_game_owned_file():
    from war3_current_map_script import MapSourceMetadata,GameSourceFile,bind_owned_source
    m=MapSourceMetadata(123,'proof','Maps/One.w3x','',False)
    a=GameSourceFile('C:/Game/Maps/One.w3x',(1,2),100,10,20)
    b=replace(a,path='D:/Other/Maps/One.w3x',file_id=(2,3))
    assert bind_owned_source(m,(a,),lambda path:a).file==a
    with pytest.raises(SourceUnavailable,match='不唯一'):bind_owned_source(m,(a,b),lambda path:a)


def test_bound_nested_script_read_is_readonly_and_keeps_exact_origin(tmp_path):
    from test_campaign_catalog import make_mpq
    from war3_current_map_script import MapSourceMetadata,GameSourceFile,RuntimeScriptSource
    inner=tmp_path/'chapter.w3x';script=b'function main takes nothing returns nothing\nendfunction\n'
    wts=b'STRING 1\n{\nQuest\n}\n';make_mpq(inner,{'war3map.j':script,'war3map.wts':wts})
    outer=tmp_path/'campaign.w3n';make_mpq(outer,{'chapter.w3x':inner.read_bytes()})
    before=outer.read_bytes();m=MapSourceMetadata(123,'proof','chapter.w3x',str(outer),True)
    f=GameSourceFile(str(outer),(1,2),len(before),10,20)
    source=RuntimeScriptSource(lambda:m,lambda:(f,),lambda path:f,lambda:'game')
    client=CurrentMapScriptClient(source.query,lambda:'game');s=client.read()
    assert s.script==script and s.strings_data==wts and 'chapter.w3x' in s.origin
    assert s.script_sha256==hashlib.sha256(script).hexdigest() and client.check(s)
    assert outer.read_bytes()==before


def test_official_map_uses_exact_casc_member_and_rechecks_session_and_content(tmp_path,monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from test_campaign_catalog import make_mpq
    import war3_casc_source as casc
    from war3_current_map_script import GameSourceFile,MapSourceMetadata,RuntimeScriptSource
    archive_path=tmp_path/'official.w3m'
    script=b'function main takes nothing returns nothing\nendfunction\n'
    strings=b'STRING 1\n{\nOfficial quest\n}\n'
    make_mpq(archive_path,{'war3map.j':script,'war3map.wts':strings})
    original=archive_path.read_bytes();current=[original]
    metadata=MapSourceMetadata(123,'official-session','Campaign/Classic/ROC/Prologue01.w3m','',False)
    build=casc.CascBuildIdentity(str(tmp_path),'9a94ff7d25781db6c09190cd69d52458','2.0.4.23745','w3','zhCN',
        hashlib.sha256(b'build').hexdigest(),(1,2,3,4))
    def read_build(root):assert Path(root)==tmp_path;return build
    class FakeArchive:
        def __init__(self,root,identity,deadline=None,cancelled=lambda:False):
            assert Path(root)==tmp_path and identity==build
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read_entry(self,member,max_bytes):
            assert member=='war3.w3mod:campaign\\classic\\roc\\prologue01.w3m'
            assert max_bytes>=len(current[0])
            if current[0] is None:return None
            return SimpleNamespace(data=current[0],content_key='key',segment_index=17,
                segment_offset=32,encoded_size=len(current[0]),span_count=1)
    monkeypatch.setattr(casc,'read_build_identity',read_build)
    monkeypatch.setattr(casc,'CascArchive',FakeArchive)
    monkeypatch.setattr(casc,'ensure_no_local_map_override',lambda root,path,**kwargs:None)
    storage=[GameSourceFile(str(tmp_path/'Data'/'data'/'data.017'),(1,7),len(original)+1024,10,20)]
    def inspect_storage(path):
        assert Path(path)==Path(storage[0].path)
        return storage[0]
    source=RuntimeScriptSource(lambda:metadata,lambda:(),inspect_storage,
        lambda:'game',casc_root=lambda:tmp_path,casc_owned_files=lambda path,cancelled:(storage[0],))
    client=CurrentMapScriptClient(source.query,lambda:'game')
    result=client.read()
    assert result.script==script and result.strings_data==strings
    assert 'war3.w3mod:campaign\\classic\\roc\\prologue01.w3m' in result.origin
    assert result.stamp[0]=='official-casc'
    assert client.check(result)
    current[0]=original+b'changed'
    assert not client.check(result)
    current[0]=original
    storage[0]=replace(storage[0],file_id=(1,8))
    assert not client.check(result)
    unowned=RuntimeScriptSource(lambda:metadata,lambda:(),inspect_storage,
        lambda:'game',casc_root=lambda:tmp_path,casc_owned_files=lambda path,cancelled:())
    with pytest.raises(SourceUnavailable,match='持有'):unowned.query()


def test_official_casc_source_refuses_local_map_override(tmp_path,monkeypatch):
    import hashlib
    from test_campaign_catalog import make_mpq
    import war3_casc_source as casc
    from war3_current_map_script import MapSourceMetadata,RuntimeScriptSource
    archive_path=tmp_path/'official.w3m';make_mpq(archive_path,{'war3map.j':b'function main takes nothing returns nothing\nendfunction'})
    metadata=MapSourceMetadata(123,'official-session','Campaign/Classic/ROC/Prologue01.w3m','',False)
    build=casc.CascBuildIdentity(str(tmp_path),'9a94ff7d25781db6c09190cd69d52458','2.0.4.23745','w3','zhCN',
        hashlib.sha256(b'build').hexdigest(),(1,2,3,4))
    monkeypatch.setattr(casc,'read_build_identity',lambda root:build)
    monkeypatch.setattr(casc,'ensure_no_local_map_override',lambda root,path:(_ for _ in ()).throw(casc.CascUnavailable('本地覆盖')))
    source=RuntimeScriptSource(lambda:metadata,lambda:(),lambda path:None,lambda:'game',casc_root=lambda:tmp_path)
    with pytest.raises(SourceUnavailable):
        source.query()


def test_different_jass_lua_entries_are_not_guessed(tmp_path):
    from test_campaign_catalog import make_mpq
    from war3_current_map_script import MapSourceMetadata,GameSourceFile,RuntimeScriptSource
    path=tmp_path/'map.w3x';make_mpq(path,{'war3map.j':b'JASS','war3map.lua':b'Lua'})
    m=MapSourceMetadata(123,'proof',str(path),'',False);f=GameSourceFile(str(path),(1,2),path.stat().st_size,10,20)
    c=CurrentMapScriptClient(RuntimeScriptSource(lambda:m,lambda:(f,),lambda path:f,lambda:1).query,lambda:1)
    with pytest.raises(SourceUnavailable,match='入口'):c.read()


def test_runtime_source_check_expires_on_source_or_map_changes(tmp_path):
    from test_campaign_catalog import make_mpq
    from war3_current_map_script import MapSourceMetadata,GameSourceFile,RuntimeScriptSource
    path=tmp_path/'map.w3x';make_mpq(path,{'war3map.j':b'// empty'})
    m=[MapSourceMetadata(123,'proof',str(path),'',False)]
    file=[GameSourceFile(str(path),(1,2),path.stat().st_size,10,20)]
    c=CurrentMapScriptClient(RuntimeScriptSource(lambda:m[0],lambda:(file[0],),lambda path:file[0],lambda:1).query,lambda:1)
    s=c.read();m[0]=replace(m[0],session_token=124);assert not c.check(s)
    m[0]=replace(m[0],session_token=123);file[0]=replace(file[0],modified=11);assert not c.check(s)


def test_windows_file_binding_matches_actual_open_handle_and_unicode_path(tmp_path):
    import os
    from war3_current_map_script import enumerate_game_files,inspect_windows_source_file
    path=tmp_path/'源.w3x';path.write_bytes(b'fixture')
    with path.open('rb'):
        info=inspect_windows_source_file(str(path),os.getpid())
        files=enumerate_game_files(os.getpid())
    assert info.size==7 and info.file_id[1] and info.process_created>0
    assert any(row.file_id==info.file_id and row.size==7 for row in files)


def test_exact_storage_handle_can_be_rechecked_inside_the_game_process(tmp_path):
    import os
    from war3_current_map_script import enumerate_game_files,inspect_windows_source_file
    path=tmp_path/'data.017';path.write_bytes(b'fixture')
    with path.open('rb'):
        ordinary=enumerate_game_files(os.getpid())
        selected=enumerate_game_files(os.getpid(),exact_paths=(path,))
        local=inspect_windows_source_file(path,os.getpid())
        assert not any(row.file_id==local.file_id for row in ordinary)
        assert len(selected)==1 and selected[0].file_id==local.file_id
        assert selected[0].handle>0 and local.handle==0


def test_cancelled_owned_file_enumeration_stops_before_scan():
    import os
    from war3_current_map_script import enumerate_game_files
    with pytest.raises(RuntimeError,match='取消'):enumerate_game_files(os.getpid(),lambda:True)


def test_runtime_factory_preserves_closed_connection_rejection(monkeypatch):
    import war3_current_map_script as m
    class ClosedCatalog:
        def identity(self):return ('closed',True)
        def query(self,*args,**kwargs):raise RuntimeError('游戏连接已关闭')
    def forbidden():raise AssertionError('closed query must not open process memory')
    client=m.create_current_map_script_client(1,ClosedCatalog(),forbidden)
    with pytest.raises(RuntimeError,match='关闭'):client.read()


@pytest.mark.parametrize('header',[(0,1,123,1,1,1),(0x31544352,99,123,1,1,1),
    (0x31544352,1,0,1,1,1),(0x31544352,1,123)])
def test_factory_rejects_bad_active_map_protocol_before_opening_memory(header):
    from war3_current_map_script import create_current_map_script_client
    class Catalog:
        def identity(self):return 'game'
        def query(self,*args):return header
    def forbidden():raise AssertionError('malformed active-map proof must not open memory')
    with pytest.raises(ValueError):create_current_map_script_client(1,Catalog(),forbidden).read()
