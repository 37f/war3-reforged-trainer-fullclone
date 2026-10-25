"""R22 source contracts and bounded exact-profile metadata reads.

No heap scans, target calls, task mutations or script execution. A source
provider must additionally bind metadata to game-owned files and map session.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import math
from pathlib import Path,PureWindowsPath
import struct
import tempfile
import time

MAX_SCRIPT_BYTES=32*1024*1024
MAX_STRINGS_BYTES=16*1024*1024
MAX_PATH_BYTES=4096
MAX_READ_SECONDS=60


class SourceUnavailable(RuntimeError):
    pass


class GameMapNotOwned(SourceUnavailable):
    """The active virtual resource is not held as an ordinary map file."""
    pass


@dataclass(frozen=True)
class MapSourceMetadata:
    session_token:int
    fingerprint:str
    map_path:str
    campaign_path:str
    is_campaign:bool


@dataclass(frozen=True)
class ScriptSnapshot:
    identity:object
    session_token:int
    origin:str
    language:str
    script:bytes
    strings_data:bytes
    script_sha256:str
    strings_sha256:str
    validated_at:float
    provenance:tuple[str,...]
    stamp:tuple


def _exact(read,address,count):
    if not 0x10000<=address<0x7fffffffffff or not 0<count<=MAX_PATH_BYTES:
        raise SourceUnavailable('脚本来源字段范围无效')
    data=read(address,count)
    if len(data)!=count:raise SourceUnavailable('脚本来源字段读取不完整')
    return data


def _q(read,address):return struct.unpack('<Q',_exact(read,address,8))[0]


def _c_string(read,address):
    data=bytearray()
    while len(data)<MAX_PATH_BYTES:
        # Do not cross a page just to read the tail of a short string.
        amount=min(64,MAX_PATH_BYTES-len(data),4096-((address+len(data))&4095))
        part=_exact(read,address+len(data),amount);end=part.find(b'\0')
        if end>=0:
            data.extend(part[:end])
            try:value=data.decode('utf8')
            except UnicodeError as exc:raise SourceUnavailable('脚本来源路径不是有效 UTF-8') from exc
            if any(ord(c)<32 or ord(c)==127 for c in value):raise SourceUnavailable('脚本来源路径含控制字符')
            return value
        data.extend(part)
    raise SourceUnavailable('脚本来源路径超过长度上限或未终止')


def _fnv(data):
    value=14695981039346656037
    for byte in data:value=((value^byte)*1099511628211)&0xffffffffffffffff
    return value


def _valid_map_path(value,campaign):
    path=PureWindowsPath(value)
    return (bool(value) and path.suffix.casefold() in ('.w3x','.w3m') and
        '..' not in path.parts and (not campaign or (not path.drive and not path.root)))


def read_profiled_map_metadata(read,base:int,active_token:int)->MapSourceMetadata:
    """Only validated 2.0.4.23745 fields, with an independently active token.

    The observed GetGameDifficulty getter binds the world/config; the campaign
    predicate used by SetCampaignMenuRace binds current-campaign storage.
    Layout evidence: docs/r22-quest-source-feasibility.md (runtime gate).
    """
    try:
        if type(active_token) is not int or not 0<active_token<2**64:
            raise SourceUnavailable('当前地图会话尚未确认')
        dos=_exact(read,base,64)
        if dos[:2]!=b'MZ':raise SourceUnavailable('当前游戏构建不支持脚本来源读取')
        pe_offset=struct.unpack_from('<I',dos,0x3c)[0]
        if not 0x40<=pe_offset<=0x1000:raise SourceUnavailable('当前游戏 PE 表头无效')
        pe=_exact(read,base+pe_offset,0x108)
        # The observed loader changes this field from disk AMD64 (8664) to
        # 0200 in memory. PE32+, exact code hashes and vtables bind this build.
        if (pe[:4]!=b'PE\0\0' or struct.unpack_from('<H',pe,4)[0] not in (0x8664,0x200) or
            struct.unpack_from('<I',pe,8)[0]!=0x69e54471 or
            struct.unpack_from('<H',pe,24)[0]!=0x20b or struct.unpack_from('<I',pe,80)[0]!=0xdd20000):
            raise SourceUnavailable('当前游戏构建不支持脚本来源读取')
        for rva,count,expected in ((0xc50003,62,0xa13bc516c90ae996),(0x9dde50,39,0x9afa250dca103fd3)):
            if _fnv(_exact(read,base+rva,count))!=expected:
                raise SourceUnavailable('脚本来源代码特征不匹配')
        world=_q(read,base+0x2b59964)^0x363abbfd3defaec9^_q(read,base+0x2bd7bc8)
        if _q(read,world)!=base+0x23d0690:raise SourceUnavailable('脚本来源世界对象类型不匹配')
        config=_q(read,world+0x2670)
        if _q(read,config)!=base+0x23d0508:raise SourceUnavailable('脚本来源配置对象类型不匹配')
        if _q(read,config+0x40)!=base+0x21dea60:raise SourceUnavailable('脚本来源路径容器类型不匹配')
        entry=_q(read,config+0x50)
        if _q(read,entry)!=base+0x21de9b0:raise SourceUnavailable('脚本来源字符串类型不匹配')
        map_path=_c_string(read,_q(read,entry+0x38))
        flag=_exact(read,world+0x304f,1)[0]
        if flag not in (0,1):raise SourceUnavailable('脚本来源战役标志无效')
        campaign_path=_c_string(read,base+0x2bd7a10) if flag==0 else ''
        campaign=bool(campaign_path)
        if not _valid_map_path(map_path,campaign):raise SourceUnavailable('当前地图资源路径无法确认')
        if campaign:
            path=PureWindowsPath(campaign_path)
            if not path.is_absolute() or path.suffix.casefold()!='.w3n' or '..' in path.parts:
                raise SourceUnavailable('当前战役来源路径无法确认')
        values=(active_token,world,config,entry,map_path,campaign_path,campaign)
        fingerprint=hashlib.sha256(repr(values).encode('utf8')).hexdigest()
        return MapSourceMetadata(active_token,fingerprint,map_path,campaign_path,campaign)
    except SourceUnavailable:raise
    except (OSError,ValueError,OverflowError,struct.error) as exc:
        raise SourceUnavailable('无法验证当前地图脚本来源：'+str(exc)) from exc


class CurrentMapScriptClient:
    """The provider proves ownership; this layer enforces immutable boundaries.

    query(snapshot=None,cancelled=...) returns a ScriptSnapshot; passing an
    existing snapshot requests a lightweight ownership/session check (bool).
    """
    def __init__(self,query,identity):self.query,self.identity=query,identity

    def read(self,cancelled=lambda:False)->ScriptSnapshot:
        started=time.monotonic();identity=self.identity()
        if cancelled():raise RuntimeError('当前地图脚本读取已取消')
        value=self.query(snapshot=None,cancelled=cancelled)
        if cancelled():raise RuntimeError('当前地图脚本读取已取消')
        if self.identity()!=identity:raise RuntimeError('游戏连接已变化')
        if time.monotonic()-started>MAX_READ_SECONDS:raise TimeoutError('当前地图脚本读取超过时间上限')
        if not isinstance(value,ScriptSnapshot):raise ValueError('脚本来源返回类型无效')
        if value.identity!=identity:raise RuntimeError('脚本来源不属于当前游戏连接')
        if (type(value.session_token) is not int or not 0<value.session_token<2**64 or not value.origin or
            not isinstance(value.provenance,tuple) or not value.provenance or
            any(not isinstance(x,str) or not x for x in value.provenance)):
            raise ValueError('脚本来源证明不完整')
        if type(value.script) is not bytes or type(value.strings_data) is not bytes:
            raise ValueError('脚本或字符串表返回类型无效')
        if len(value.script)>MAX_SCRIPT_BYTES or len(value.strings_data)>MAX_STRINGS_BYTES:
            raise ValueError('脚本或字符串表超过大小上限')
        if (hashlib.sha256(value.script).hexdigest()!=value.script_sha256 or
            hashlib.sha256(value.strings_data).hexdigest()!=value.strings_sha256):
            raise ValueError('脚本或字符串表哈希不一致')
        if value.language not in ('jass','lua'):raise ValueError('不支持的脚本语言')
        if not math.isfinite(value.validated_at) or not 0<=value.validated_at<=time.monotonic():
            raise ValueError('脚本校验时间无效')
        return value

    def check(self,snapshot:ScriptSnapshot)->bool:
        if self.identity()!=snapshot.identity:return False
        result=self.query(snapshot=snapshot,cancelled=lambda:False)
        return result is True and self.identity()==snapshot.identity


@dataclass(frozen=True)
class GameSourceFile:
    path:str
    file_id:tuple[int,int]
    size:int
    modified:int
    process_created:int


@dataclass(frozen=True)
class BoundScriptFile:
    file:GameSourceFile
    member:str


def _path_parts(path):
    value=str(path).replace('/','\\')
    if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
    elif value.startswith(('\\\\?\\','\\??\\')):value=value[4:]
    return tuple(part.casefold() for part in PureWindowsPath(value).parts)


def _file_signature(file):return file.file_id,file.size,file.modified,file.process_created


def bind_owned_source(metadata,files,inspect_file)->BoundScriptFile:
    """Bind runtime paths to an actually open game file, never a directory scan.

    inspect_file opens the host path for metadata and compares its file ID to
    the game's own handle. A recent write is conservatively unverified.
    """
    if not _valid_map_path(metadata.map_path,metadata.is_campaign):
        raise SourceUnavailable('当前地图资源路径无法确认')
    expected=metadata.campaign_path if metadata.is_campaign else metadata.map_path
    absolute=PureWindowsPath(expected).is_absolute();parts=_path_parts(expected)
    if not parts or '..' in parts:raise SourceUnavailable('当前来源路径无效')
    candidates={}
    for file in sorted(files,key=lambda x:x.path):
        candidate=_path_parts(file.path)
        matches=candidate==parts if absolute else candidate[-len(parts):]==parts
        if matches:
            if not file.file_id or len(file.file_id)!=2 or not file.file_id[1]:
                raise SourceUnavailable('游戏持有文件的身份无法确认')
            candidates[file.file_id]=file
    if not candidates:raise GameMapNotOwned('没有找到游戏实际持有的当前地图档案')
    if len(candidates)!=1:raise SourceUnavailable('当前地图档案匹配不唯一，不能确定来源')
    game=next(iter(candidates.values()))
    if game.process_created<=0 or game.modified>game.process_created:
        raise SourceUnavailable('档案写入时间晚于游戏启动，无法确认已加载版本')
    local=inspect_file(expected if absolute else game.path)
    if _file_signature(local)!=_file_signature(game):
        raise SourceUnavailable('当前路径文件与游戏持有文件不一致或已被替换')
    return BoundScriptFile(local,metadata.map_path if metadata.is_campaign else '')


class RuntimeScriptSource:
    """Verified metadata + owned-file or exact installed-CASC source."""
    def __init__(self,metadata,owned_files,inspect_file,identity,casc_root=None,casc_owned_files=None):
        self.metadata,self.owned_files,self.inspect_file,self.identity=metadata,owned_files,inspect_file,identity
        self.casc_root=casc_root
        self.casc_owned_files=casc_owned_files

    def query(self,*,snapshot=None,cancelled=lambda:False):
        if snapshot is not None:
            if snapshot.stamp and snapshot.stamp[0]=='official-casc':
                return self._check_official_snapshot(snapshot)
            if len(snapshot.stamp)!=2:return False
            before,file=snapshot.stamp
            if self.metadata()!=before:return False
            return _file_signature(self.inspect_file(file.path))==_file_signature(file)
        start=time.monotonic();identity=self.identity()
        def check():
            if cancelled():raise RuntimeError('当前地图脚本读取已取消')
            if time.monotonic()-start>MAX_READ_SECONDS:raise TimeoutError('当前地图脚本读取超过时间上限')
            if self.identity()!=identity:raise RuntimeError('游戏连接已变化')
        check();before=self.metadata()
        try:binding=bind_owned_source(before,self.owned_files(),self.inspect_file)
        except GameMapNotOwned:
            if self.casc_root is None:raise
            return self._read_official_map(before,identity,start,check)
        entry,language,script,strings=self._read_map(binding,start+MAX_READ_SECONDS,check)
        check()
        if self.metadata()!=before or _file_signature(self.inspect_file(binding.file.path))!=_file_signature(binding.file):
            raise SourceUnavailable('来源验证时数据发生变化，请重新检索')
        validated_at=time.monotonic()
        origin=binding.file.path+('::'+binding.member if binding.member else '')+'::'+entry
        provenance=('active-map/profiled-config-and-campaign','game-owned-file-id-and-unmodified-since-process-start',
            'read-only-mpq-exact-member','map-string-table:war3map.wts')
        return ScriptSnapshot(identity,before.session_token,origin,language,script,strings,
            hashlib.sha256(script).hexdigest(),hashlib.sha256(strings).hexdigest(),validated_at,
            provenance,(before,binding.file))

    def _read_official_map(self,before,identity,start,check):
        from war3_casc_source import (CascArchive,CascUnavailable,MAX_CASC_BYTES,
            ensure_no_local_map_override,official_member,read_build_identity)
        try:
            root=Path(self.casc_root()).resolve();build=read_build_identity(root)
            if build.product!='w3' or build.version!='2.0.4.23745':
                raise SourceUnavailable('当前游戏版本与官方资源读取器不匹配')
            member=official_member(before.map_path)
            ensure_no_local_map_override(root,before.map_path)
            with CascArchive(root,build,deadline=start+MAX_READ_SECONDS,cancelled=check) as archive:
                entry=archive.read_entry(member,MAX_CASC_BYTES)
            if entry is None:raise SourceUnavailable('当前官方地图在本机 CASC 资源中不存在')
            storage=self._bind_casc_data_file(root,entry,check)
            check()
            script_entry,language,script,strings=self._read_map_data(entry.data,start+MAX_READ_SECONDS,check)
            check()
            if self.metadata()!=before or self.identity()!=identity:
                raise SourceUnavailable('读取官方地图时当前会话发生变化')
            if _file_signature(self.inspect_file(storage.path))!=_file_signature(storage):
                raise SourceUnavailable('官方地图数据文件在读取时变化')
            map_sha256=hashlib.sha256(entry.data).hexdigest()
            origin=f'CASC::{root}::{member}::{script_entry}'
            provenance=('active-map/profiled-config-and-session','official-member-from-live-map-path',
                'local-casc-build-and-exact-resource-content','game-owned-casc-data-file',
                'local-file-overrides-disabled','read-only-mpq-exact-script',
                'map-string-table:war3map.wts:base-resource-text')
            return ScriptSnapshot(identity,before.session_token,origin,language,script,strings,
                hashlib.sha256(script).hexdigest(),hashlib.sha256(strings).hexdigest(),time.monotonic(),
                provenance,('official-casc',before,str(root),build,member,map_sha256,storage))
        except CascUnavailable as exc:
            raise SourceUnavailable(str(exc)) from exc

    def _check_official_snapshot(self,snapshot):
        try:
            _,before,root_text,build,member,map_sha256,storage=snapshot.stamp
            if self.identity()!=snapshot.identity or self.metadata()!=before:return False
            root=Path(self.casc_root()).resolve()
            if str(root)!=root_text:return False
            from war3_casc_source import (CascArchive,CascUnavailable,MAX_CASC_BYTES,
                ensure_no_local_map_override,official_member,read_build_identity)
            current=read_build_identity(root)
            if current!=build or official_member(before.map_path)!=member:return False
            ensure_no_local_map_override(root,before.map_path)
            if _file_signature(self.inspect_file(storage.path))!=_file_signature(storage):return False
            with CascArchive(root,current,deadline=time.monotonic()+MAX_READ_SECONDS) as archive:
                entry=archive.read_entry(member,MAX_CASC_BYTES)
            return (entry is not None and entry.span_count==1 and
                _path_parts(root/'Data'/'data'/f'data.{entry.segment_index:03d}')==_path_parts(storage.path) and
                hashlib.sha256(entry.data).hexdigest()==map_sha256 and
                self.metadata()==before and self.identity()==snapshot.identity)
        except (OSError,RuntimeError,ValueError,TypeError):
            return False

    def _bind_casc_data_file(self,root,entry,check):
        if self.casc_owned_files is None:
            raise SourceUnavailable('官方资源尚未绑定游戏实际持有的数据文件')
        if (entry.span_count!=1 or type(entry.segment_index) is not int or not 0<=entry.segment_index<=9999 or
            type(entry.segment_offset) is not int or entry.segment_offset<0 or
            type(entry.encoded_size) is not int or entry.encoded_size<=0):
            raise SourceUnavailable('官方资源的数据分段身份未受支持')
        path=root/'Data'/'data'/f'data.{entry.segment_index:03d}'
        files={file.file_id:file for file in self.casc_owned_files(path,check)
            if _path_parts(file.path)==_path_parts(path)}
        if len(files)!=1:raise SourceUnavailable('未找到游戏唯一实际持有的官方数据文件')
        game=next(iter(files.values()));check()
        if (len(game.file_id)!=2 or not game.file_id[1] or game.process_created<=0 or
            game.modified>game.process_created or entry.segment_offset+entry.encoded_size>game.size):
            raise SourceUnavailable('官方数据文件身份、加载时间或资源边界无法确认')
        local=self.inspect_file(path)
        if _file_signature(local)!=_file_signature(game):
            raise SourceUnavailable('本地官方数据文件与游戏持有文件不一致')
        return local

    @staticmethod
    def _read_map(binding,deadline,check):
        from war3_campaign_catalog import StormArchive,MAX_MAP_BYTES
        if not binding.member:return RuntimeScriptSource._extract_map_path(Path(binding.file.path),deadline,check)
        with StormArchive(Path(binding.file.path),deadline) as outer:
            check();data=outer.read(binding.member,MAX_MAP_BYTES)
            if data is None:raise SourceUnavailable('当前战役中没有运行时指定的章节档案')
        with tempfile.TemporaryDirectory(prefix='war3-r22-source-') as temporary:
            path=Path(temporary)/'chapter.w3x';path.write_bytes(data)
            check();return RuntimeScriptSource._extract_map_path(path,deadline,check)

    @staticmethod
    def _read_map_data(data,deadline,check):
        with tempfile.TemporaryDirectory(prefix='war3-r23-source-') as temporary:
            path=Path(temporary)/'official-map.w3m';path.write_bytes(data)
            check();return RuntimeScriptSource._extract_map_path(path,deadline,check)

    @staticmethod
    def _extract_map_path(path,deadline,check):
        from war3_campaign_catalog import StormArchive
        with StormArchive(Path(path),deadline) as archive:
            candidates=[];total=0
            for name,language in (('war3map.j','jass'),('scripts\\war3map.j','jass'),
                                  ('war3map.lua','lua'),('scripts\\war3map.lua','lua')):
                check();data=archive.read(name,MAX_SCRIPT_BYTES)
                if data is not None:
                    total+=len(data)
                    if total>MAX_SCRIPT_BYTES:raise SourceUnavailable('脚本入口候选超过总读取上限')
                    candidates.append((name,language,data))
            if not candidates:raise SourceUnavailable('当前地图没有可读取的 JASS/Lua 脚本入口')
            if len({(language,hashlib.sha256(data).digest()) for _,language,data in candidates})!=1:
                raise SourceUnavailable('当前地图有多个不同脚本入口，无法确认生效脚本')
            entry,language,script=candidates[0]
            check();strings=archive.read('war3map.wts',MAX_STRINGS_BYTES) or b''
            return entry,language,script,strings


@lru_cache(maxsize=1)
def _windows_api():
    import ctypes as C
    import os
    if os.name!='nt':raise SourceUnavailable('当前脚本来源查询只支持 Windows')
    k=C.WinDLL('kernel32',use_last_error=True);nt=C.WinDLL('ntdll')
    signatures={
        'OpenProcess':([C.c_uint32,C.c_int,C.c_uint32],C.c_void_p),
        'GetCurrentProcess':([],C.c_void_p),
        'CloseHandle':([C.c_void_p],C.c_int),
        'DuplicateHandle':([C.c_void_p,C.c_void_p,C.c_void_p,C.POINTER(C.c_void_p),C.c_uint32,C.c_int,C.c_uint32],C.c_int),
        'GetFileType':([C.c_void_p],C.c_uint32),
        'GetFinalPathNameByHandleW':([C.c_void_p,C.c_wchar_p,C.c_uint32,C.c_uint32],C.c_uint32),
        'GetFileInformationByHandle':([C.c_void_p,C.c_void_p],C.c_int),
        'GetProcessTimes':([C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p],C.c_int),
        'CreateFileW':([C.c_wchar_p,C.c_uint32,C.c_uint32,C.c_void_p,C.c_uint32,C.c_uint32,C.c_void_p],C.c_void_p),
        'K32EnumProcessModules':([C.c_void_p,C.c_void_p,C.c_uint32,C.POINTER(C.c_uint32)],C.c_int),
        'K32GetModuleFileNameExW':([C.c_void_p,C.c_void_p,C.c_wchar_p,C.c_uint32],C.c_uint32),
    }
    for name,(args,result) in signatures.items():
        function=getattr(k,name);function.argtypes=args;function.restype=result
    nt.NtQuerySystemInformation.argtypes=[C.c_uint32,C.c_void_p,C.c_uint32,C.POINTER(C.c_uint32)]
    nt.NtQuerySystemInformation.restype=C.c_long
    return C,k,nt


def _process_creation(k,C,handle):
    values=[C.c_uint64() for _ in range(4)]
    if not k.GetProcessTimes(handle,*(C.byref(v) for v in values)):
        raise SourceUnavailable('无法查询游戏进程的创建时间')
    return values[0].value


def _handle_file_info(k,C,handle,path,created):
    # BY_HANDLE_FILE_INFORMATION has 4-byte alignment, including FILETIMEs.
    info=C.create_string_buffer(52)
    if not k.GetFileInformationByHandle(handle,info):raise SourceUnavailable('无法查询来源文件身份')
    attributes,_,_,modified,volume,high,low,_,index_high,index_low=struct.unpack('<IQQQIIIIII',info.raw)
    if attributes&0x10:raise SourceUnavailable('来源不是普通文件')
    return GameSourceFile(str(path),(volume,(index_high<<32)|index_low),(high<<32)|low,modified,created)


def inspect_windows_source_file(path,pid)->GameSourceFile:
    """Read file identity/attributes with shared access; no data or writes."""
    C,k,_=_windows_api();process=k.OpenProcess(0x400,False,pid)
    if not process:raise SourceUnavailable('无法查询游戏进程身份')
    handle=None
    try:
        created=_process_creation(k,C,process)
        handle=k.CreateFileW(str(path),0x80,7,None,3,0,None)
        if handle in (None,0,C.c_void_p(-1).value):raise SourceUnavailable('无法只读核对来源文件')
        return _handle_file_info(k,C,handle,str(path),created)
    finally:
        if handle not in (None,0,C.c_void_p(-1).value):k.CloseHandle(handle)
        k.CloseHandle(process)


def enumerate_game_files(pid,cancelled=lambda:False,*,exact_paths=())->tuple[GameSourceFile,...]:
    """Query only this game's existing disk handles; never change file offset."""
    if cancelled():raise RuntimeError('当前地图脚本读取已取消')
    requested=frozenset(_path_parts(path) for path in exact_paths)
    C,k,nt=_windows_api();size=1024*1024;deadline=time.monotonic()+MAX_READ_SECONDS
    for _ in range(8):
        if cancelled():raise RuntimeError('当前地图脚本读取已取消')
        if size>128*1024*1024:raise SourceUnavailable('系统句柄清单超过查询上限')
        buffer=C.create_string_buffer(size);needed=C.c_uint32()
        status=nt.NtQuerySystemInformation(64,buffer,size,C.byref(needed))
        if status==0:break
        if status!=-1073741820:raise SourceUnavailable(f'系统拒绝查询游戏持有文件：{status&0xffffffff:#x}')
        size=max(size*2,needed.value+65536)
    else:raise SourceUnavailable('系统句柄清单持续变化，请重试')
    blob=buffer.raw;count=struct.unpack_from('<Q',blob)[0]
    if 16+count*40>len(blob):raise SourceUnavailable('系统句柄清单返回不完整')
    process=k.OpenProcess(0x1040,False,pid)
    if not process:raise SourceUnavailable('无法查询游戏持有文件')
    rows=[]
    try:
        created=_process_creation(k,C,process)
        for index in range(count):
            if index%256==0:
                if cancelled():raise RuntimeError('当前地图脚本读取已取消')
                if time.monotonic()>deadline:raise SourceUnavailable('游戏文件查询超过时间上限')
            _,owner,value,_,_,_,_,_=struct.unpack_from('<QQQIHHII',blob,16+index*40)
            if owner!=pid:continue
            duplicate=C.c_void_p()
            if not k.DuplicateHandle(process,value,k.GetCurrentProcess(),C.byref(duplicate),0,False,2):continue
            try:
                if k.GetFileType(duplicate)!=1:continue
                path=C.create_unicode_buffer(32768)
                length=k.GetFinalPathNameByHandleW(duplicate,path,len(path),0)
                if not 0<length<len(path):continue
                if requested:
                    if _path_parts(path.value) not in requested:continue
                elif PureWindowsPath(path.value).suffix.casefold() not in ('.w3n','.w3x','.w3m'):continue
                try:rows.append(_handle_file_info(k,C,duplicate,path.value,created))
                except SourceUnavailable:continue
                if len(rows)>4096:raise SourceUnavailable('游戏地图文件数量超过查询上限')
            finally:k.CloseHandle(duplicate)
    finally:k.CloseHandle(process)
    return tuple(rows)


def game_image_base(process_handle)->int:
    """Resolve the game module through OS metadata, without memory scanning."""
    C,k,_=_windows_api();modules=(C.c_void_p*1024)();needed=C.c_uint32()
    if not k.K32EnumProcessModules(process_handle,modules,C.sizeof(modules),C.byref(needed)) or needed.value>C.sizeof(modules):
        raise SourceUnavailable('无法查询游戏映像')
    matches=[]
    for module in modules[:needed.value//C.sizeof(C.c_void_p)]:
        path=C.create_unicode_buffer(32768)
        if k.K32GetModuleFileNameExW(process_handle,module,path,len(path)) and PureWindowsPath(path.value).name.casefold()=='warcraft iii.exe':
            matches.append(int(module))
    if len(matches)!=1:raise SourceUnavailable('游戏映像不是唯一匹配')
    return matches[0]


def game_image_path(process_handle)->Path:
    """Resolve the running game executable path without reading game memory."""
    C,k,_=_windows_api();modules=(C.c_void_p*1024)();needed=C.c_uint32()
    if not k.K32EnumProcessModules(process_handle,modules,C.sizeof(modules),C.byref(needed)) or needed.value>C.sizeof(modules):
        raise SourceUnavailable('无法查询游戏映像路径')
    matches=[]
    for module in modules[:needed.value//C.sizeof(C.c_void_p)]:
        path=C.create_unicode_buffer(32768)
        if k.K32GetModuleFileNameExW(process_handle,module,path,len(path)) and PureWindowsPath(path.value).name.casefold()=='warcraft iii.exe':
            matches.append(Path(path.value))
    if len(matches)!=1:raise SourceUnavailable('游戏映像路径不是唯一匹配')
    return matches[0]


def find_casc_install_root(executable_path)->Path:
    """Bind CASC to the unique supported build above the running executable."""
    from war3_casc_source import CascUnavailable,read_build_identity
    executable=Path(executable_path).resolve()
    matches=[]
    for root in (executable.parent,*executable.parents[:6]):
        if not (root/'.build.info').is_file():continue
        try:identity=read_build_identity(root)
        except CascUnavailable:continue
        if identity.product=='w3' and identity.version=='2.0.4.23745':matches.append(root.resolve())
    matches=tuple(dict.fromkeys(matches))
    if len(matches)!=1:raise SourceUnavailable('无法从当前游戏映像唯一确认官方 CASC 安装目录')
    return matches[0]


def create_current_map_script_client(pid,catalog,memory_factory)->CurrentMapScriptClient:
    """Reuse persistent-helper active-map proof, plus bounded passive metadata.

    memory_factory is the existing trainer's read-only ProcessMemory context;
    none of its selection, resource or mutation methods are modified.
    """
    from war3_current_map_catalog import parse_catalog_header
    def metadata():
        last=None
        for _ in range(3):
            # Catalog bridge rejects close/reconnect after acquiring its lock.
            header=tuple(catalog.query(318))
            token,_=parse_catalog_header(header)
            try:
                with memory_factory() as memory:
                    base=game_image_base(memory.handle)
                    before=read_profiled_map_metadata(memory.read,base,token)
                    after=read_profiled_map_metadata(memory.read,base,token)
                final=tuple(catalog.query(318));parse_catalog_header(final)
                if before==after and final==header:return before
                last=SourceUnavailable('来源验证时数据发生变化，请重新检索')
            except SourceUnavailable as exc:last=exc
        raise last
    def casc_root():
        with memory_factory() as memory:executable=game_image_path(memory.handle)
        return find_casc_install_root(executable)
    source=RuntimeScriptSource(metadata,lambda:enumerate_game_files(pid),
        lambda path:inspect_windows_source_file(path,pid),catalog.identity,casc_root=casc_root,
        casc_owned_files=lambda path,cancelled:enumerate_game_files(pid,cancelled,exact_paths=(path,)))
    return CurrentMapScriptClient(source.query,catalog.identity)
