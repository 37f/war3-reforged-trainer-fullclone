"""R21: bounded current-map query protocol; no Tk, scans or gameplay writes."""
from __future__ import annotations

from dataclasses import dataclass
import struct
import time

from war3_campaign_catalog import CatalogResult
from war3_custom_objects import CustomObjectEntry, display_rawcode, resolve_string
from war3_id_catalog import ID_CATALOG

MAGIC=0x31544352
KINDS=('unit','item','ability')
MAX_OBJECTS=100000
MAX_BYTES=32*1024*1024
MAX_NAME_BYTES=65536
PAGE_SIZE=16


@dataclass(frozen=True)
class RuntimeName:
    set_key:int
    level:int
    data_pointer:int
    value:str


@dataclass(frozen=True)
class RuntimeDefinition:
    rawcode:bytes
    base:bytes
    custom:bool
    names:tuple[RuntimeName,...]


@dataclass(frozen=True)
class CatalogPage:
    token:int
    kind:str
    total:int
    start:int
    records:tuple[RuntimeDefinition,...]


@dataclass(frozen=True)
class RuntimeCatalogSnapshot:
    token:int
    counts:tuple[int,int,int]
    identity:object
    timestamp:float
    elapsed_ms:float
    result:CatalogResult
    validated_at:float


def _words(values):
    if len(values)>MAX_BYTES//8 or any(type(v) is not int or not 0<=v<2**64 for v in values):
        raise ValueError('当前地图返回数据越界')
    return values


def parse_catalog_header(values):
    _words(values)
    if len(values)!=6 or values[:2]!=(MAGIC,1) or not values[2] or sum(values[3:])>MAX_OBJECTS:
        raise ValueError('当前地图目录表头或数量无效')
    return values[2],tuple(values[3:])


def parse_catalog_page(values,expected_token,kind,start):
    _words(values)
    if (len(values)<7 or values[:2]!=(MAGIC,1) or values[2]!=expected_token or
        kind not in KINDS or values[3]!=KINDS.index(kind) or values[5]!=start):
        raise ValueError('当前地图分页会话或类别不一致')
    _,_,token,_,total,_,count=values[:7]
    if total>MAX_OBJECTS or not 0<count<=PAGE_SIZE or start+count>total:
        raise ValueError('当前地图分页数量无效')
    pos=7; rows=[]
    for _ in range(count):
        if pos+4>len(values): raise ValueError('当前地图记录截断')
        base,raw,custom,names=values[pos:pos+4];pos+=4
        if not 0<base<2**32 or not 0<raw<2**32 or custom not in (0,1) or names>128:
            raise ValueError('当前地图对象标识无效')
        if not custom and base!=raw: raise ValueError('原版改动 ID 不一致')
        candidates=[]
        for _ in range(names):
            if pos+4>len(values): raise ValueError('当前地图名称截断')
            key,level,pointer,length=values[pos:pos+4];pos+=4
            words=(length+7)//8
            if max(key,level,pointer)>0xffffffff or length>MAX_NAME_BYTES or pos+words>len(values):
                raise ValueError('当前地图名称长度或字段无效')
            data=struct.pack('<'+'Q'*words,*values[pos:pos+words]);pos+=words
            if any(data[length:]) or b'\0' in data[:length]: raise ValueError('当前地图名称填充无效')
            candidates.append(RuntimeName(key,level,pointer,data[:length].decode('utf8','backslashreplace')))
        rows.append(RuntimeDefinition(raw.to_bytes(4,'little'),base.to_bytes(4,'little'),bool(custom),tuple(candidates)))
    if pos!=len(values): raise ValueError('当前地图分页存在多余数据')
    return CatalogPage(token,kind,total,start,tuple(rows))


def build_runtime_result(records):
    entries={};issues=[]
    if sum(len(rows) for rows in records.values())>MAX_OBJECTS: raise ValueError('对象数量超过上限')
    for kind in KINDS:
        rows=records.get(kind,()); by_id={r.rawcode:r for r in rows}
        if len(by_id)!=len(rows): raise ValueError('当前地图存在重复 ID')
        generic={x.rawcode:x.name_zh or x.name_en for x in ID_CATALOG[kind]}
        def name_for(code,visited):
            if code in visited or len(visited)>=64: return '名称无法解析','基础对象继承循环或超过深度上限'
            row=by_id.get(code)
            if row is None:
                name=generic.get(display_rawcode(code))
                return (name,'名称回退到通用目录') if name else ('名称缺失','基础对象未找到')
            candidates=[(n,resolve_string(n.value,{})) for n in row.names if n.value]
            unique={value for _,(value,_) in candidates}
            if len(unique)>1:
                detail='；'.join(f'集合 {n.set_key}/等级 {n.level}/字段 {n.data_pointer}: {value}' for n,(value,_) in candidates)
                return '名称存在多个候选',detail
            if candidates:
                return candidates[0][1][0],'；'.join(dict.fromkeys(note for _,(_,note) in candidates if note))
            if row.base==code:
                name=generic.get(display_rawcode(code))
                return (name,'名称回退到通用目录') if name else ('名称缺失','名称缺失：通用目录无对应名称')
            name,note=name_for(row.base,visited|{code})
            return name,'继承基础名称'+('；'+note if note else '')
        output=[]
        for row in sorted(rows,key=lambda r:r.rawcode):
            code=display_rawcode(row.rawcode);name,note=name_for(row.rawcode,set())
            copyable=all(33<=b<=126 for b in row.rawcode) and not code.lower().startswith('0x')
            if not copyable: note+='；ID 不适合直接复制到指令输入框'
            if name=='名称存在多个候选' or any(x in note for x in ('未解析','循环','缺失','未找到','非 UTF-8')):
                issues.append(f'{kind} {code}：{note}')
            output.append(CustomObjectEntry(code,name,display_rawcode(row.base),'新增' if row.custom else '原版改动','当前地图',note,copyable))
        entries[kind]=tuple(output)
    return CatalogResult(entries,tuple(issues),('当前地图；检测时快照；未修改游戏对象',))


class CurrentMapCatalogClient:
    def __init__(self,query,identity):
        self.query,self.identity=query,identity

    def read(self,cancelled=lambda:False):
        identity=self.identity();start_time=time.monotonic();size=0
        def request(op,**kwargs):
            nonlocal size
            if cancelled(): raise RuntimeError('当前地图检测已取消')
            if self.identity()!=identity: raise RuntimeError('游戏连接已变化')
            if time.monotonic()-start_time>60: raise TimeoutError('当前地图检测超过时间上限')
            result=tuple(self.query(op,**kwargs));size+=len(result)*8
            if size>MAX_BYTES: raise ValueError('当前地图返回数据超过大小上限')
            if self.identity()!=identity: raise RuntimeError('游戏连接已变化')
            return result
        token,counts=parse_catalog_header(request(318))
        records={}
        for kind,total in zip(KINDS,counts):
            rows=[]
            while len(rows)<total:
                page=parse_catalog_page(request(319,kind=KINDS.index(kind),start=len(rows),token=token),token,kind,len(rows))
                if page.total!=total: raise ValueError('当前地图分页总数量不一致')
                rows.extend(page.records)
            records[kind]=tuple(rows)
        if parse_catalog_header(request(318))!=(token,counts): raise RuntimeError('地图会话已变化，请重新检测')
        # R21 freshness starts at target validation, before name resolution or
        # a delayed Tk queue delivery can make an old snapshot appear current.
        validated_at=time.monotonic();timestamp=time.time()
        result=build_runtime_result(records)
        if cancelled(): raise RuntimeError('当前地图检测已取消')
        if self.identity()!=identity: raise RuntimeError('游戏连接已变化')
        return RuntimeCatalogSnapshot(token,counts,identity,timestamp,(time.monotonic()-start_time)*1000,result,validated_at)

    def check(self,snapshot):
        if self.identity()!=snapshot.identity: return False
        header=parse_catalog_header(tuple(self.query(318)))
        return header==(snapshot.token,snapshot.counts) and self.identity()==snapshot.identity
