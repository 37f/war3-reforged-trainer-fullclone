"""R34 independent owner-army heal ABI; existing FullClone actions stay intact."""
import struct
from war3_selection_protocol import build_work as selection_work,validate_work as selection_validate
from war3_fullclone_protocol import SIGNATURE_BY_NAME

NAMES=('GetOwningPlayer','GetPlayerId','Player','GroupEnumUnitsOfPlayer','GetUnitState',
    'SetUnitState','ConvertUnitState','GetWidgetLife','IsUnitType','ConvertUnitType','IsUnitHidden')
SIGNATURES=tuple((name,SIGNATURE_BY_NAME[name]) for name in NAMES)
WORK_SIZE=640
ABI=struct.pack('<3I',0x46333401,216,WORK_SIZE)
RESULT='<Q8IQiI'


def build_work(entries,tls,*,mode=0):
    if type(mode) is not int or mode not in (0,1,2):raise ValueError('全军补满范围无效')
    p=bytearray(WORK_SIZE);p[:480]=selection_work(entries)
    for i,(name,sig) in enumerate(SIGNATURES):
        entry=entries[name]
        if entry.name!=name or entry.signature!=sig:raise ValueError('全军补满接口签名不同：'+name)
        struct.pack_into('<Q',p,480+i*8,entry.handler)
    struct.pack_into(RESULT,p,568,tls,mode,0,0,0,0,0,0,0,0,-1,0)
    validate_work(p);return bytes(p)


def validate_work(p):
    if len(p)!=WORK_SIZE:raise ValueError('全军补满数据长度无效')
    selection_validate(p[:480])
    values=struct.unpack_from(RESULT,p,568);tls,mode=values[:2]
    if not 0x10000<=tls<0x800000000000 or tls%8 or mode not in (0,1,2):raise ValueError('全军补满请求无效')
    if any(values[2:10]) or values[10]!=-1 or values[11] or any(p[624:]):raise ValueError('全军补满结果必须初始化')
    if any(not 0x10000<=ptr<0x800000000000 for ptr in struct.unpack_from('<11Q',p,480)):raise ValueError('全军补满接口无效')


def decode_work(p,_count=None):
    if len(p)!=WORK_SIZE:raise ValueError('全军补满结果不完整')
    tls,mode,error,done,changed,eligible,visited,dead,hidden,owner,player,attempted=struct.unpack_from(RESULT,p,568)
    if mode not in (0,1,2) or not 0<=changed<=attempted<=eligible<=visited<=100000 or dead+hidden>visited or any(p[624:]):raise ValueError('全军补满计数无效')
    if error or done!=1:
        raise RuntimeError(f'全军补满未完成：error={error}，已尝试 {attempted} 个单位、已补满 {changed} 个；部分修改可能已生效，不自动重放')
    if (owner==0 and player!=-1) or (owner and not 0<=player<28):raise ValueError('全军补满玩家身份无效')
    return dict(owner=owner,player=player,mode=mode,changed=changed,eligible=eligible,visited=visited,
        skipped_dead=dead,skipped_hidden=hidden,attempted=attempted)
