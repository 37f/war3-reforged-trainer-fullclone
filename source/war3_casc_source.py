"""R23 bounded, local-only CASC reads. This does not prove an active map.

The caller must separately bind storage/member to the live game before publishing
a ScriptSnapshot. CascLib is opened locally, without online/download flags.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path,PureWindowsPath
import re
import time

CASC_SOURCE_COMMIT='38a34665624b8775bb875274b36191b21c38d97b'
CASC_DLL_SHA256='5641c4f30cb4367127a97dc6b00dda6bc906064323f3e3df5829872b2a829947'
MAX_BUILD_BYTES=65536
MAX_CASC_BYTES=256*1024*1024


class CascUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CascBuildIdentity:
    root:str
    build_key:str
    version:str
    product:str
    tags:str
    build_info_sha256:str
    stamp:tuple[int,int,int,int]


@dataclass(frozen=True)
class CascEntry:
    member:str
    data:bytes
    content_key:str
    encoded_key:str
    segment_index:int
    segment_offset:int
    encoded_size:int
    span_count:int


def _stamp(path):
    value=path.stat()
    return value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns


def read_build_identity(root:Path)->CascBuildIdentity:
    root=Path(root).resolve();path=root/'.build.info'
    try:
        before=_stamp(path)
        if before[2]>MAX_BUILD_BYTES:raise CascUnavailable('CASC 构建信息超过大小上限')
        with path.open('rb') as stream:data=stream.read(MAX_BUILD_BYTES+1)
        if len(data)>MAX_BUILD_BYTES:raise CascUnavailable('CASC 构建信息超过大小上限')
        if _stamp(path)!=before:raise CascUnavailable('CASC 构建信息在读取时变化')
        lines=data.decode('utf-8-sig').splitlines()
        if not lines or len(lines)>65:raise CascUnavailable('CASC 构建信息格式无效')
        header=[x.split('!',1)[0] for x in lines[0].split('|')]
        if len(header)!=len(set(header)):raise CascUnavailable('CASC 构建信息字段重复')
        required=('Active','Build Key','Version','Product','Tags')
        if any(x not in header for x in required):raise CascUnavailable('CASC 构建信息字段不完整')
        rows=[]
        for line in lines[1:]:
            if not line.strip():continue
            values=line.split('|')
            if len(values)!=len(header):raise CascUnavailable('CASC 构建信息记录不完整')
            row=dict(zip(header,values))
            if row['Active']=='1':rows.append(row)
        if len(rows)!=1:raise CascUnavailable('CASC 当前构建不是唯一匹配')
        row=rows[0]
        if row['Product']!='w3' or not re.fullmatch('[0-9a-fA-F]{32}',row['Build Key']):
            raise CascUnavailable('CASC 当前构建不是有效的 Warcraft III 资源')
        if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+',row['Version']):
            raise CascUnavailable('CASC 游戏版本格式无效')
        return CascBuildIdentity(str(root),row['Build Key'].lower(),row['Version'],row['Product'],
            row['Tags'],hashlib.sha256(data).hexdigest(),before)
    except (OSError,UnicodeError) as exc:
        raise CascUnavailable('无法只读确认 CASC 本地构建：'+str(exc)) from exc


def official_member(map_path:str)->str:
    """Accept canonical map paths supplied by the live game metadata."""
    if not isinstance(map_path,str) or not map_path or len(map_path)>4096 or any(ord(c)<32 for c in map_path):
        raise CascUnavailable('官方地图资源路径无效')
    path=PureWindowsPath(map_path)
    parts=path.parts
    campaign=(len(parts)>=4 and parts[0].casefold()=='campaign' and
        parts[1].casefold() in ('classic','reforged'))
    game_map=(len(parts)>=2 and parts[0].casefold()=='maps')
    if (path.drive or path.root or '..' in parts or ':' in map_path or not (campaign or game_map) or
        path.suffix.casefold() not in ('.w3m','.w3x')):
        raise CascUnavailable('官方地图资源路径无法确认')
    return 'war3.w3mod:'+'\\'.join(x.casefold() for x in parts)


def _local_file_override_configuration():
    """Read the override switch and alternate registered install root only."""
    import os
    if os.name!='nt':raise CascUnavailable('无法核对 Warcraft III 本地文件覆盖设置')
    try:
        import winreg
        key=winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Blizzard Entertainment\Warcraft III')
    except FileNotFoundError:return False,()
    except OSError as exc:raise CascUnavailable('无法读取 Warcraft III 本地文件覆盖设置') from exc
    try:
        try:enabled,kind=winreg.QueryValueEx(key,'Allow Local Files')
        except FileNotFoundError:return False,()
        if kind!=winreg.REG_DWORD or type(enabled) is not int or enabled not in (0,1):
            raise CascUnavailable('Warcraft III 本地文件覆盖设置格式无效')
        roots=[]
        try:
            install_path,install_kind=winreg.QueryValueEx(key,'InstallPath')
            if install_kind==winreg.REG_SZ and isinstance(install_path,str) and install_path.strip():
                roots.append(Path(install_path.strip()).resolve())
        except FileNotFoundError:pass
        return bool(enabled),tuple(roots)
    except OSError as exc:raise CascUnavailable('无法读取 Warcraft III 本地文件覆盖设置') from exc
    finally:winreg.CloseKey(key)


def ensure_no_local_map_override(install_root:Path,map_path:str):
    """Fail closed until the effective local-override search order is proven."""
    official_member(map_path)
    try:enabled,_=_local_file_override_configuration()
    except CascUnavailable:raise
    except Exception as exc:raise CascUnavailable('无法核对 Warcraft III 本地文件覆盖设置') from exc
    if enabled:
        raise CascUnavailable('Warcraft III 已启用本地文件覆盖，尚不能确认官方脚本的实际生效优先级')


class _FileInfo(C.Structure):
    _fields_=[('CKey',C.c_ubyte*16),('EKey',C.c_ubyte*16),('DataFileName',C.c_char*16),
        ('StorageOffset',C.c_uint64),('SegmentOffset',C.c_uint64),('TagBitMask',C.c_uint64),
        ('FileNameHash',C.c_uint64),('ContentSize',C.c_uint64),('EncodedSize',C.c_uint64),
        ('SegmentIndex',C.c_uint32),('SpanCount',C.c_uint32),('FileDataId',C.c_uint32),
        ('LocaleFlags',C.c_uint32),('ContentFlags',C.c_uint32)]


@lru_cache(maxsize=1)
def _load_library():
    path=Path(__file__).resolve().parent/'tools'/'CascLib.dll'
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=CASC_DLL_SHA256:
            raise CascUnavailable('CASC 读取库校验不一致')
        dll=C.WinDLL(str(path),use_last_error=True)
    except OSError as exc:raise CascUnavailable('无法加载配套 CASC 读取库：'+str(exc)) from exc
    signatures={
        'CascOpenStorage':([C.c_wchar_p,C.c_uint32,C.POINTER(C.c_void_p)],C.c_bool),
        'CascCloseStorage':([C.c_void_p],C.c_bool),
        'CascOpenFile':([C.c_void_p,C.c_char_p,C.c_uint32,C.c_uint32,C.POINTER(C.c_void_p)],C.c_bool),
        'CascCloseFile':([C.c_void_p],C.c_bool),
        'CascGetFileSize64':([C.c_void_p,C.POINTER(C.c_uint64)],C.c_bool),
        'CascGetFileInfo':([C.c_void_p,C.c_uint32,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)],C.c_bool),
        'CascReadFile':([C.c_void_p,C.c_void_p,C.c_uint32,C.POINTER(C.c_uint32)],C.c_bool),
    }
    for name,(args,result) in signatures.items():
        function=getattr(dll,name);function.argtypes=args;function.restype=result
    return dll


class CascArchive:
    """Independent local storage. Does not borrow handles from Warcraft III."""
    def __init__(self,root,identity:CascBuildIdentity,deadline=None,cancelled=lambda:False):
        self.root=Path(root).resolve();self.identity=identity
        self.deadline=time.monotonic()+60 if deadline is None else deadline
        self.cancelled=cancelled;self.handle=C.c_void_p();self.dll=None

    def _check(self):
        if self.cancelled():raise CascUnavailable('CASC 读取已取消')
        if time.monotonic()>self.deadline:raise CascUnavailable('CASC 读取超过时间上限')
        if str(self.root)!=self.identity.root or _stamp(self.root/'.build.info')!=self.identity.stamp:
            raise CascUnavailable('CASC 本地构建已变化')

    def __enter__(self):
        self._check()
        if read_build_identity(self.root)!=self.identity:raise CascUnavailable('CASC 本地构建已变化')
        self.dll=_load_library()
        # CascOpenStorage creates local storage with no ALLOW_DOWNLOAD feature.
        if not self.dll.CascOpenStorage(str(self.root),0,C.byref(self.handle)):
            raise CascUnavailable(f'无法只读打开本地 CASC 资源：{C.get_last_error()}')
        try:self._check()
        except BaseException:
            self.__exit__(None,None,None);raise
        return self

    def __exit__(self,*_):
        if self.handle:
            self.dll.CascCloseStorage(self.handle);self.handle=C.c_void_p()

    def read(self,member,max_bytes=MAX_CASC_BYTES):
        result=self.read_entry(member,max_bytes)
        return None if result is None else result.data

    def read_entry(self,member,max_bytes=MAX_CASC_BYTES)->CascEntry|None:
        self._check()
        if not self.handle:raise CascUnavailable('CASC 档案已关闭')
        if type(max_bytes) is not int or not 0<=max_bytes<=MAX_CASC_BYTES:
            raise CascUnavailable('CASC 读取大小上限无效')
        if (not isinstance(member,str) or len(member)>4096 or
            not member.startswith('war3.w3mod:') or any(ord(c)<32 for c in member) or
            '..' in PureWindowsPath(member.split(':',1)[1]).parts):
            raise CascUnavailable('CASC 资源成员路径无效')
        file=C.c_void_p()
        if not self.dll.CascOpenFile(self.handle,member.encode('utf8'),0,0,C.byref(file)):
            if C.get_last_error()==2:return None
            raise CascUnavailable(f'CASC 资源无法打开：{C.get_last_error()}')
        try:
            size=C.c_uint64()
            if not self.dll.CascGetFileSize64(file,C.byref(size)):
                raise CascUnavailable(f'CASC 资源内容未完整安装在本地：{C.get_last_error()}')
            if size.value>max_bytes:raise CascUnavailable('CASC 资源超过读取大小上限')
            info=_FileInfo();needed=C.c_size_t()
            if (not self.dll.CascGetFileInfo(file,2,C.byref(info),C.sizeof(info),C.byref(needed)) or
                needed.value!=C.sizeof(info) or info.ContentSize!=size.value or
                not 1<=info.SpanCount<=64):
                raise CascUnavailable('CASC 资源身份信息不完整')
            chunks=[];remaining=size.value
            while remaining:
                self._check();amount=min(1024*1024,remaining)
                buffer=C.create_string_buffer(amount);got=C.c_uint32()
                if not self.dll.CascReadFile(file,buffer,amount,C.byref(got)) or got.value!=amount:
                    raise CascUnavailable(f'CASC 资源读取不完整：{C.get_last_error()}')
                chunks.append(buffer.raw);remaining-=amount
            self._check();data=b''.join(chunks)
            # CKey is the storage content checksum, separate from provenance.
            if hashlib.md5(data).digest()!=bytes(info.CKey):
                raise CascUnavailable('CASC 资源内容与内容键不一致')
            return CascEntry(member,data,bytes(info.CKey).hex(),bytes(info.EKey).hex(),
                info.SegmentIndex,info.SegmentOffset,info.EncodedSize,info.SpanCount)
        finally:self.dll.CascCloseFile(file)
