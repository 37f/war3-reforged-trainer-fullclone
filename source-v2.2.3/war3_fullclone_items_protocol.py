"""Relocate captured existing item identities; no item creation is available."""
import math
import struct

HEADER=128
ROW=64
MAX_ITEMS=100000
ABI=struct.pack('<3I',0x46333102,216,0)
SIGNATURES=(('GetItemTypeId','(Hitem;)I'),('IsItemOwned','(Hitem;)B'),
    ('IsItemVisible','(Hitem;)B'),('GetWidgetLife','(Hwidget;)R'),
    ('SetItemPosition','(Hitem;RR)V'),('GetItemX','(Hitem;)R'),('GetItemY','(Hitem;)R'),('GetItemCharges','(Hitem;)I'))


def build_work(entries,tls,*,base,converter,item_tag,items,x,y,preview=False):
    pointers=[converter]
    for name,sig in SIGNATURES:
        e=entries[name]
        if e.name!=name or e.signature!=sig:raise ValueError('物品接口签名不同：'+name)
        pointers.append(e.handler)
    p=struct.pack('<11Q2f6IQ',*pointers,base,tls,x,y,len(items),int(preview),0,0,0,0,item_tag)
    p+=b''.join(struct.pack('<2Q2I',r['full'],r['address'],r['rawcode'],0)+bytes(40) for r in items)
    validate_work(p);return p


def validate_work(p):
    if len(p)<HEADER or (len(p)-HEADER)%ROW:raise ValueError('地面物品事务长度无效')
    values=struct.unpack_from('<11Q2f6IQ',p);ptrs=values[:11];x,y=values[11:13]
    n,preview,error,done,changed,visited=values[13:19]
    if any(not 0x10000<=v<0x800000000000 for v in ptrs) or n>MAX_ITEMS or len(p)!=HEADER+n*ROW or preview not in (0,1) or error or done or changed or visited:raise ValueError('地面物品事务参数无效')
    if not all(math.isfinite(v) and abs(v)<=1e6 for v in (x,y)):raise ValueError('鼠标坐标无效')
    identities=set()
    for i in range(n):
        full,obj,raw,res=struct.unpack_from('<2Q2I',p,HEADER+i*ROW)
        if not full or not 0x10000<=obj<0x800000000000 or obj%8 or not raw or res or full in identities or any(p[HEADER+i*ROW+24:HEADER+(i+1)*ROW]):raise ValueError('物品身份或结果初值无效')
        identities.add(full)


def decode_work(p,_count=None):
    if len(p)<HEADER:raise ValueError('地面物品结果不完整')
    x,y=struct.unpack_from('<2f',p,88);n,preview,error,done,changed,visited=struct.unpack_from('<6I',p,96)
    if error or done!=1 or changed>n or visited>n or len(p)!=HEADER+n*ROW:raise RuntimeError(f'聚集地面物品未完成：error={error}，已处理={changed}（不自动重放）')
    return dict(count=n,changed=changed,visited=visited,preview=bool(preview),x=x,y=y)
