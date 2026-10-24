"""R20 offline catalog: read-only MPQ access, selected chapter, scoped diagnostics."""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path, PureWindowsPath
import struct
import tempfile
import time

from war3_custom_objects import Reader, MAX_OBJECT_BYTES, parse_object_data, parse_wts, resolve_string, merge_objects

STORMLIB_SHA256 = '93321f6f030be5d7d79eb4cbf433d6ef7e83ce20d47d8963717f207d54afbe16'
MAX_MAP_BYTES = 512 * 1024 * 1024


@lru_cache(maxsize=1)
def _storm_library():
    path = Path(__file__).resolve().parent / 'tools' / 'StormLib.dll'
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != STORMLIB_SHA256:
        raise ValueError('打包的 StormLib 校验失败，请使用完整发布包')
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    if data[offset:offset+4] != b'PE\0\0' or struct.unpack_from('<H',data,offset+4)[0] != 0x8664:
        raise ValueError('StormLib 不是所需的 x64 版本')
    dll = C.WinDLL(str(path), use_last_error=True)
    signatures = {
        'SFileOpenArchive': ([C.c_wchar_p,C.c_uint32,C.c_uint32,C.POINTER(C.c_void_p)],C.c_bool),
        'SFileCloseArchive': ([C.c_void_p],C.c_bool),
        'SFileOpenFileEx': ([C.c_void_p,C.c_char_p,C.c_uint32,C.POINTER(C.c_void_p)],C.c_bool),
        'SFileGetFileSize': ([C.c_void_p,C.POINTER(C.c_uint32)],C.c_uint32),
        'SFileReadFile': ([C.c_void_p,C.c_void_p,C.c_uint32,C.POINTER(C.c_uint32),C.c_void_p],C.c_bool),
        'SFileCloseFile': ([C.c_void_p],C.c_bool),
    }
    for name,(args,result) in signatures.items():
        function=getattr(dll,name); function.argtypes=args; function.restype=result
    return dll


class StormArchive:
    """Only read operations are exposed; archive is always MPQ_OPEN_READ_ONLY."""
    def __init__(self, path: Path, deadline: float | None = None):
        self.path = Path(path)
        self.deadline = deadline or time.monotonic()+60
        self.dll = _storm_library()
        self.handle = C.c_void_p()

    def check_time(self):
        if time.monotonic() > self.deadline:
            raise ValueError('文件检测超过 60 秒时间上限')

    def __enter__(self):
        self.check_time()
        if not self.dll.SFileOpenArchive(str(self.path),0,0x100,C.byref(self.handle)):
            raise OSError(C.get_last_error(), '无法只读打开战役/章节档案（可能占用、损坏或不支持）')
        return self

    def __exit__(self, *_):
        if self.handle:
            self.dll.SFileCloseArchive(self.handle)
            self.handle = C.c_void_p()

    def read(self, name: str, max_bytes: int = MAX_OBJECT_BYTES) -> bytes | None:
        self.check_time()
        if not self.handle:
            raise ValueError('档案已关闭')
        file = C.c_void_p()
        if not self.dll.SFileOpenFileEx(self.handle,name.encode('utf8'),0,C.byref(file)):
            error = C.get_last_error()
            if error == 2:
                return None
            raise OSError(error,f'无法读取档案条目：{name}')
        try:
            high = C.c_uint32()
            C.set_last_error(0)
            low = self.dll.SFileGetFileSize(file,C.byref(high))
            if low == 0xffffffff and C.get_last_error():
                raise OSError(C.get_last_error(),f'无法获取条目大小：{name}')
            size = low + (high.value << 32)
            if size > max_bytes:
                raise ValueError(f'{name} 超过读取大小上限')
            chunks = []
            while size:
                self.check_time()
                amount=min(size,1024*1024)
                buffer=C.create_string_buffer(amount); read=C.c_uint32()
                if not self.dll.SFileReadFile(file,buffer,amount,C.byref(read),None) or read.value != amount:
                    raise OSError(C.get_last_error(),f'条目读取不完整：{name}')
                chunks.append(buffer.raw); size -= amount
            return b''.join(chunks)
        finally:
            self.dll.SFileCloseFile(file)


@dataclass(frozen=True)
class Chapter:
    title: str
    path: str


@dataclass(frozen=True)
class CampaignInfo:
    path: Path
    sha256: str
    chapters: tuple[Chapter,...]
    issues: tuple[str,...] = ()


@dataclass(frozen=True)
class CatalogResult:
    entries: dict
    issues: tuple[str,...]
    statuses: tuple[str,...]

    @property
    def partial(self):
        return bool(self.issues)


def _sha256(path: Path, deadline: float) -> str:
    if path.stat().st_size > 8*1024**3:
        raise ValueError('战役超过 8 GiB 大小上限')
    digest=hashlib.sha256()
    with path.open('rb') as file:
        while chunk := file.read(1024*1024):
            if time.monotonic() > deadline:
                raise ValueError('战役校验超过时间上限')
            digest.update(chunk)
    return digest.hexdigest()


def _valid_map_path(path):
    value=PureWindowsPath(path)
    return bool(path) and not value.is_absolute() and not value.drive and '..' not in value.parts and value.suffix.lower() in ('.w3x','.w3m')


def parse_campaign_info(data: bytes, strings: dict) -> tuple[Chapter,...]:
    r=Reader(data)
    if r.integer() != 1:
        raise ValueError('不支持的战役清单格式版本')
    r.raw(8)
    for _ in range(4): r.string()
    r.raw(8); r.string(); r.string(); r.raw(4); r.string(); r.raw(24)
    chapters=[]
    for _ in range(r.count(4096)):
        r.integer()
        chapter_title,map_title,path=r.string(),r.string(),r.string()
        title,_=resolve_string(chapter_title,strings)
        name,_=resolve_string(map_title,strings)
        if _valid_map_path(path):
            chapters.append(Chapter(' / '.join(x for x in (title,name) if x) or path,path))
        else:
            raise ValueError('战役清单包含无效章节路径')
    for _ in range(r.count(4096)):
        r.raw(1); path=r.string()
        if not _valid_map_path(path):
            raise ValueError('战役顺序表包含无效章节路径')
        if not any(x.path.lower()==path.lower() for x in chapters):
            chapters.append(Chapter(path,path))
    r.finish()
    return tuple(chapters)


def _read_optional(archive,name,issues,statuses):
    try:
        data=archive.read(name)
        statuses.append(f'{name}：'+('无此文件' if data is None else '已读取'))
        return data
    except (ValueError,OSError) as exc:
        issues.append(f'{name}：{exc}')
        statuses.append(f'{name}：读取失败')
        return None


def _strings(archive,name,issues,statuses):
    data=_read_optional(archive,name,issues,statuses)
    if data is None: return {}
    try:
        return parse_wts(data)
    except ValueError as exc:
        issues.append(f'{name}：{exc}')
        return {}


def list_campaign(path: Path) -> CampaignInfo:
    path=Path(path).resolve(strict=True)
    if path.suffix.lower() != '.w3n':
        raise ValueError('请选择 .w3n 战役文件')
    deadline=time.monotonic()+60
    before=_sha256(path,deadline)
    issues,statuses,chapters=[],[],[]
    with StormArchive(path,deadline) as archive:
        strings=_strings(archive,'war3campaign.wts',issues,statuses)
        data=_read_optional(archive,'war3campaign.w3f',issues,statuses)
        if data is not None:
            try: chapters.extend(parse_campaign_info(data,strings))
            except ValueError as exc: issues.append(f'war3campaign.w3f：{exc}')
        else:
            issues.append('未读取战役章节清单；使用档案列表补充，章节列表可能不完整')
        listing=_read_optional(archive,'(listfile)',issues,statuses)
        if listing is not None:
            for name in listing.decode('utf8','backslashreplace').splitlines():
                if len(chapters)>=4096: raise ValueError('章节数量超过上限')
                if _valid_map_path(name) and not any(x.path.lower()==name.lower() for x in chapters):
                    chapters.append(Chapter(name,name))
    if _sha256(path,deadline) != before:
        raise ValueError('战役文件在读取过程中发生变化，请重新选择')
    if not chapters:
        raise ValueError('未能找到可读取的章节。'+ '；'.join(issues))
    return CampaignInfo(path,before,tuple(chapters),tuple(issues))


def detect_campaign(info: CampaignInfo, chapter: Chapter) -> CatalogResult:
    deadline=time.monotonic()+60
    if chapter not in info.chapters or not _valid_map_path(chapter.path):
        raise ValueError('章节不属于当前所选战役清单')
    if _sha256(info.path,deadline) != info.sha256:
        raise ValueError('战役文件已发生变化，请重新选择战役')
    issues,statuses=list(info.issues),[]
    with StormArchive(info.path,deadline) as campaign:
        inner=campaign.read(chapter.path,MAX_MAP_BYTES)
        if inner is None: raise ValueError('所选章节不存在于战役档案中')
        # Archive names never become disk paths. TemporaryDirectory is outside live game data.
        with tempfile.TemporaryDirectory(prefix='war3-catalog-') as temp:
            map_path=Path(temp)/'chapter.mpq'; map_path.write_bytes(inner)
            del inner
            with StormArchive(map_path,deadline) as map_archive:
                campaign_strings=_strings(campaign,'war3campaign.wts',issues,statuses)
                map_strings=_strings(map_archive,'war3map.wts',issues,statuses)
                entries={}
                for kind,ext in (('unit','w3u'),('item','w3t'),('ability','w3a')):
                    layers=[]
                    for archive,prefix in ((campaign,'war3campaign'),(map_archive,'war3map')):
                        name=f'{prefix}.{ext}'
                        data=_read_optional(archive,name,issues,statuses)
                        try: definitions=parse_object_data(data,kind) if data is not None else ()
                        except ValueError as exc:
                            issues.append(f'{name}：{exc}'); definitions=()
                        layers.append(definitions)
                    entries[kind]=merge_objects(*layers,campaign_strings,map_strings,kind)
                    for entry in entries[kind]:
                        if any(word in entry.note for word in ('未解析','循环','冲突','缺失','未找到','非 UTF-8')):
                            issues.append(f'{kind} {entry.rawcode}：{entry.note}')
    if _sha256(info.path,deadline) != info.sha256:
        raise ValueError('战役文件在检测过程中发生变化，结果已丢弃')
    return CatalogResult(entries,tuple(issues),tuple(statuses))
