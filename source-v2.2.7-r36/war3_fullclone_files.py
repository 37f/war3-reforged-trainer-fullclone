"""Retained R30 Windows file-identity queries only; no game addresses."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import PureWindowsPath
import struct,time
MAX_READ_SECONDS=10

class SourceUnavailable(RuntimeError):
    pass

@dataclass(frozen=True)
class GameSourceFile:
    path:str
    file_id:tuple[int,int]
    size:int
    modified:int
    process_created:int
    handle:int=0

def _path_parts(path):
    value=str(path).replace('/','\\')
    if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
    elif value.startswith(('\\\\?\\','\\??\\')):value=value[4:]
    return tuple(part.casefold() for part in PureWindowsPath(value).parts)

def _file_signature(file):return file.file_id,file.size,file.modified,file.process_created

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

def _handle_file_info(k,C,handle,path,created,game_handle=0):
    # BY_HANDLE_FILE_INFORMATION has 4-byte alignment, including FILETIMEs.
    info=C.create_string_buffer(52)
    if not k.GetFileInformationByHandle(handle,info):raise SourceUnavailable('无法查询来源文件身份')
    attributes,_,_,modified,volume,high,low,_,index_high,index_low=struct.unpack('<IQQQIIIIII',info.raw)
    if attributes&0x10:raise SourceUnavailable('来源不是普通文件')
    return GameSourceFile(str(path),(volume,(index_high<<32)|index_low),(high<<32)|low,modified,created,game_handle)

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
                try:rows.append(_handle_file_info(k,C,duplicate,path.value,created,value))
                except SourceUnavailable:continue
                if len(rows)>4096:raise SourceUnavailable('游戏地图文件数量超过查询上限')
            finally:k.CloseHandle(duplicate)
    finally:k.CloseHandle(process)
    return tuple(rows)
