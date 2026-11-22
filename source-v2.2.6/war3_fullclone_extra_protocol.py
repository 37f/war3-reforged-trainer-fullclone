"""R35 standalone operations. Existing readers, protocols and action IDs stay intact."""
import math,struct
from war3_selection_protocol import build_work as selection_work,validate_work as selection_validate

SIGNATURES=(('GetOwningPlayer','(Hunit;)Hplayer;'),('GetPlayerId','(Hplayer;)I'),('Player','(I)Hplayer;'),
    ('GroupEnumUnitsOfPlayer','(Hgroup;Hplayer;Hboolexpr;)V'),('GetWidgetLife','(Hwidget;)R'),
    ('IsUnitType','(Hunit;Hunittype;)B'),('ConvertUnitType','(I)Hunittype;'),('IsUnitHidden','(Hunit;)B'),
    ('IsUnitPaused','(Hunit;)B'),('PauseUnit','(Hunit;B)V'),('CreateItem','(IRR)Hitem;'),
    ('GetItemTypeId','(Hitem;)I'),('SetItemCharges','(Hitem;I)V'),('GetItemCharges','(Hitem;)I'),
    ('UnitAddItem','(Hunit;Hitem;)B'),('UnitItemInSlot','(Hunit;I)Hitem;'),('UnitInventorySize','(Hunit;)I'),
    ('CreateUnit','(Hplayer;IRRR)Hunit;'),('RemoveUnit','(Hunit;)V'),('UnitAddAbility','(Hunit;I)B'),
    ('BlzSetUnitMaxMana','(Hunit;I)V'),('SetUnitState','(Hunit;Hunitstate;R)V'),('ConvertUnitState','(I)Hunitstate;'),
    ('SetUnitVertexColor','(Hunit;IIII)V'),('SetUnitPathing','(Hunit;B)V'),('IssuePointOrderById','(Hunit;IRR)B'),
    ('GetUnitX','(Hunit;)R'),('GetUnitY','(Hunit;)R'),('GetUnitAbilityLevel','(Hunit;I)I'),
    ('GetItemX','(Hitem;)R'),('GetItemY','(Hitem;)R'),('SetUnitUseFood','(Hunit;B)V'))
REQUIRED={1:(0,1,2,3,4,5,6,7,8),2:(0,4,8,9),3:(0,4,5,6,7,10,11,12,13,14,15,16,26,27,29,30),
    4:(0,17,18,19,20,21,22,23,24,28,31),5:(0,25,28),6:(0,18)}
MAX_ROWS=4096;ROWS=832;ROW=64;WORK_SIZE=ROWS+MAX_ROWS*ROW
ABI=struct.pack('<3I',0x46333501,216,0) # Variable rows, like the author's item catalogue ABI.
HEADER='<QQ8IQQiIIiffQ';ROW_FMT='<4Q4I2fQ'
ROW_KEYS=('unit','full','owner','item','rawcode','paused','desired','status','x','y','reserved')
SPELLS={'AUin':('地狱火',852224),'AHbz':('暴风雪',852089),'AHfs':('烈焰风暴',852488),'ANrf':('火焰雨',852238)}

def build_work(entries,tls,action,*,resolver,flag=0,scope=0,rows=(),target=0,owner=0,rawcode=0,x=0.,y=0.,expected_full=0):
    if type(action) is not int or action not in REQUIRED or type(flag) is not int or flag not in (0,1) or type(scope) is not int or scope not in (0,1,2):raise ValueError('扩展操作参数无效')
    if len(rows)>MAX_ROWS or any(not math.isfinite(v) or abs(v)>1000000 for v in (x,y)):raise ValueError('扩展操作坐标或数量无效')
    capacity=MAX_ROWS if action==1 else len(rows)
    p=bytearray(ROWS+capacity*ROW);p[:480]=selection_work(entries)
    for i in REQUIRED[action]:
        name,sig=SIGNATURES[i];e=entries[name]
        if e.name!=name or e.signature!=sig:raise ValueError('扩展接口签名不同：'+name)
        struct.pack_into('<Q',p,480+i*8,e.handler)
    struct.pack_into(HEADER,p,736,tls,resolver,action,flag,scope,len(rows),0,0,0,0,target,owner,-1,rawcode,capacity,-1,x,y,expected_full)
    for i,row in enumerate(rows):struct.pack_into(ROW_FMT,p,ROWS+i*ROW,*(row.get(k,0) for k in ROW_KEYS))
    validate_work(p);return bytes(p)

def validate_work(p):
    if not ROWS<=len(p)<=WORK_SIZE or (len(p)-ROWS)%ROW:raise ValueError('扩展数据长度无效')
    selection_validate(p[:480]);v=struct.unpack_from(HEADER,p,736)
    tls,resolver,action,flag,scope,requested,count,changed,error,done,target,owner,player,code,capacity,charges,x,y,full=v
    if any(not 0x10000<=q<0x800000000000 for q in (tls,resolver)) or tls%8 or action not in REQUIRED:raise ValueError('扩展请求无效')
    if flag not in (0,1) or scope not in (0,1,2) or capacity!=(len(p)-ROWS)//ROW or not 0<=requested<=capacity or any((count,changed,error,done)) or player!=-1 or charges!=-1:raise ValueError('扩展结果必须初始化')
    if any(not math.isfinite(q) or abs(q)>1000000 for q in (x,y)) or any(p[ROWS+requested*ROW:]):raise ValueError('扩展坐标或空行无效')
    ptrs=struct.unpack_from('<32Q',p,480)
    if any(not 0x10000<=ptrs[i]<0x800000000000 for i in REQUIRED[action]) or any(ptrs[i] for i in range(32) if i not in REQUIRED[action]):raise ValueError('扩展函数槽位无效')
    rs=[dict(zip(ROW_KEYS,struct.unpack_from(ROW_FMT,p,ROWS+i*ROW))) for i in range(requested)]
    if action==1 and (capacity!=MAX_ROWS or any((requested,target,owner,code,full))):raise ValueError('冻结查询不能预填单位')
    if action!=1 and capacity!=requested:raise ValueError('扩展行容量必须匹配请求')
    if action==2 and (requested!=1 or any(not rs[0][k] for k in ('unit','full','owner','rawcode')) or any(rs[0][k] not in (0,1) for k in ('paused','desired'))):raise ValueError('暂停恢复身份无效')
    if action==3 and (not 1<=requested<=32 or any(not r['rawcode'] or not 0<=r['desired']<=1000000001 for r in rs)):raise ValueError('补给包无效')
    if action in (4,5,6) and (code not in [int.from_bytes(s.encode(),'big') for s in SPELLS] or requested or (action!=4 and (not target or not full or not owner))):raise ValueError('固定施法请求无效')
    if action==4 and any((target,owner,full)):raise ValueError('新施法不能预填载体身份')
    if any(r['status'] or r['item'] or r['reserved'] for r in rs):raise ValueError('扩展行结果必须初始化')

def decode_work(p,_count=None):
    if not ROWS<=len(p)<=WORK_SIZE or (len(p)-ROWS)%ROW:raise ValueError('扩展结果不完整')
    v=struct.unpack_from(HEADER,p,736);action,flag,scope,requested,count,changed,error,done=v[2:10]
    if not 0<=changed<=count<=MAX_ROWS or v[14]!=(len(p)-ROWS)//ROW or action<4 and count>v[14]:raise ValueError('扩展返回计数无效')
    if error or done!=1:
        hint={1101:'请只选择一个存活、未隐藏的英雄',1102:'英雄经典背包空位不足，未创建物品',1103:'当前地图未能创建指定物品',1104:'物品未确认放入英雄背包',1010:'单位数量超过保护上限，未冻结'}.get(error,'')
        raise RuntimeError(f'扩展未完成：操作{action}，error={error}，已完成{changed}项；{hint}；可能已部分生效，请核对后操作，不自动重试')
    rows=[dict(zip(ROW_KEYS,struct.unpack_from(ROW_FMT,p,ROWS+i*ROW))) for i in range(count if action<4 else 0)]
    return dict(action=action,changed=changed,rows=rows,owner=v[11],player=v[12],target=v[10],full=v[18],x=v[16],y=v[17])
