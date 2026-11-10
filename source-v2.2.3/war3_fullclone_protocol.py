"""R31 independent, typed extension ABI. Never loads the old 2.0.4 helper."""
import math
import struct

from war3_selection_protocol import build_work as selection_work, validate_work as selection_validate

# These are native registrations, not executable addresses. The author's engine
# resolves and checks them in the current game exactly as its other operations.
SIGNATURES = (
    ('GetOwningPlayer','(Hunit;)Hplayer;'), ('GetPlayerId','(Hplayer;)I'),
    ('Player','(I)Hplayer;'), ('GetPlayerTeam','(Hplayer;)I'),
    ('GetPlayerSlotState','(Hplayer;)Hplayerslotstate;'),
    ('ConvertPlayerSlotState','(I)Hplayerslotstate;'), ('SetUnitOwner','(Hunit;Hplayer;B)V'),
    ('GetUnitState','(Hunit;Hunitstate;)R'), ('SetUnitState','(Hunit;Hunitstate;R)V'),
    ('ConvertUnitState','(I)Hunitstate;'), ('ConvertPlayerColor','(I)Hplayercolor;'),
    ('SetUnitColor','(Hunit;Hplayercolor;)V'), ('SetPlayerColor','(Hplayer;Hplayercolor;)V'),
    ('GroupEnumUnitsOfPlayer','(Hgroup;Hplayer;Hboolexpr;)V'),
    ('IsUnitType','(Hunit;Hunittype;)B'), ('ConvertUnitType','(I)Hunittype;'),
    ('ReviveHero','(Hunit;RRB)B'), ('GetWidgetLife','(Hwidget;)R'),
    ('GetHeroStr','(Hunit;B)I'), ('GetHeroAgi','(Hunit;B)I'), ('GetHeroInt','(Hunit;B)I'),
    ('SetHeroStr','(Hunit;IB)V'), ('SetHeroAgi','(Hunit;IB)V'), ('SetHeroInt','(Hunit;IB)V'),
    ('SetHeroLevel','(Hunit;IB)V'), ('ConvertAllianceType','(I)Halliancetype;'),
    ('GetPlayerAlliance','(Hplayer;Hplayer;Halliancetype;)B'),
    ('SetPlayerAlliance','(Hplayer;Hplayer;Halliancetype;B)V'),
    ('SetPlayerTeam','(Hplayer;I)V'), ('GetUnitX','(Hunit;)R'), ('GetUnitY','(Hunit;)R'),
    ('GetUnitFacing','(Hunit;)R'), ('CreateUnit','(Hplayer;IRRR)Hunit;'),
    ('RemoveUnit','(Hunit;)V'),
    ('PanCameraToTimed','(RRR)V'), ('SetUnitPathing','(Hunit;B)V'),
    ('GetPlayerName','(Hplayer;)S'),
    ('UnitAddAbility','(Hunit;I)B'),
    ('BlzSetUnitMaxMana','(Hunit;I)V'),
    ('SetUnitVertexColor','(Hunit;IIII)V'),
    ('IssuePointOrderById','(Hunit;IRR)B'),
    ('SuspendHeroXP','(Hunit;B)V'), ('IsSuspendedXP','(Hunit;)B'),
    ('UnitStripHeroLevel','(Hunit;I)B'),
    # R30 replacement semantics: preserve ratios, mine gold and hero inventory.
    ('CreateBlightedGoldmine','(Hplayer;RRR)Hunit;'),
    ('GetHeroXP','(Hunit;)I'), ('SetHeroXP','(Hunit;IB)V'),
    ('GetResourceAmount','(Hunit;)I'), ('SetResourceAmount','(Hunit;I)V'),
    ('UnitItemInSlot','(Hunit;I)Hitem;'), ('UnitRemoveItem','(Hunit;Hitem;)V'),
    ('UnitAddItem','(Hunit;Hitem;)B'), ('IsUnitHidden','(Hunit;)B'),
    ('ShowUnit','(Hunit;B)V'), ('KillUnit','(Hunit;)V'),
)
# R31.2 retires slots34/35; surviving native slots retain their original ABI.
INDEX = {name:i if i<34 else i+2 for i,(name,_) in enumerate(SIGNATURES)}
SIGNATURE_BY_NAME = dict(SIGNATURES)
COMMON = ('GetOwningPlayer','GetPlayerId','Player','GetPlayerTeam')
ACTIONS = {
    0: COMMON, 1: COMMON+('GetPlayerSlotState','ConvertPlayerSlotState','SetUnitOwner'),
    2: ('GetUnitState','SetUnitState','ConvertUnitState'),
    3: ('SetUnitColor','ConvertPlayerColor'), 4: ('GetOwningPlayer','SetPlayerColor','ConvertPlayerColor'),
    5: COMMON+('GroupEnumUnitsOfPlayer','IsUnitType','ConvertUnitType','ReviveHero','GetWidgetLife'),
    6: ('SetHeroLevel','SuspendHeroXP','IsSuspendedXP','UnitStripHeroLevel'), 7: ('GetHeroStr','GetHeroAgi','GetHeroInt','SetHeroStr','SetHeroAgi','SetHeroInt'),
    8: COMMON+('ConvertAllianceType','GetPlayerAlliance'),
    9: COMMON+('ConvertAllianceType','GetPlayerAlliance','SetPlayerAlliance'),
    10: COMMON+('ConvertAllianceType','GetPlayerAlliance','SetPlayerAlliance'),
    11: ('Player','GetPlayerSlotState','ConvertPlayerSlotState','CreateUnit','GetOwningPlayer'),
    12: COMMON+('GetUnitX','GetUnitY','GetUnitFacing','CreateUnit','RemoveUnit',
        'GetUnitState','SetUnitState','ConvertUnitState','IsUnitType','ConvertUnitType',
        'CreateBlightedGoldmine','GetHeroXP','SetHeroXP','GetResourceAmount','SetResourceAmount',
        'UnitItemInSlot','UnitRemoveItem','UnitAddItem','IsUnitHidden','ShowUnit','KillUnit'),
    14: ('SetUnitPathing',),
    15: ('PanCameraToTimed',),
    16: ('CreateUnit','RemoveUnit','GetOwningPlayer','UnitAddAbility','BlzSetUnitMaxMana','SetUnitState','ConvertUnitState','SetUnitVertexColor','SetUnitPathing'),
    17: ('IssuePointOrderById','GetOwningPlayer'),
    18: ('RemoveUnit','GetOwningPlayer'),
    19: COMMON+('ConvertAllianceType','GetPlayerAlliance'),
    20: COMMON+('GetPlayerSlotState','ConvertPlayerSlotState','ConvertAllianceType','GetPlayerAlliance','SetPlayerAlliance'),
}
SLOTS=64
ROW_SIZE=48
HEADER=1088
MATRIX=HEADER+24*ROW_SIZE
WORK_SIZE=MATRIX+28*20*4+28*4
ABI=struct.pack('<3I',0x46333101,216,WORK_SIZE)


def build_work(entries,tls,action,*,value=0,rawcode=0,x=0.,y=0.,target=0,expected_owner=0,units=(),matrix=(),resolver=0):
    if type(action) is not int or action not in ACTIONS:raise ValueError('未知扩展操作')
    if not (math.isfinite(x) and math.isfinite(y) and abs(x)<=1e6 and abs(y)<=1e6):raise ValueError('扩展坐标无效')
    if type(value) is not int or not -1<=value<=1000000000:raise ValueError('扩展数值无效')
    if len(units)>24 or any(type(u) is not int or u<=0 for u in units) or len(set(units))!=len(units):raise ValueError('扩展对象身份无效')
    p=bytearray(WORK_SIZE);p[:480]=selection_work(entries)
    for name in ACTIONS[action]:
        e=entries[name]
        if e.name!=name or e.signature!=SIGNATURE_BY_NAME[name]:raise ValueError('扩展接口签名不同：'+name)
        struct.pack_into('<Q',p,480+INDEX[name]*8,e.handler)
    if action in (16,17,18):struct.pack_into('<Q',p,480+63*8,resolver)
    struct.pack_into('<QIiIff4I4x2Q',p,992,tls,action,value,rawcode,x,y,len(units),0,0,0,target,expected_owner)
    # Header has an independent input/output layout; keep rows/matrix outside it.
    for i,u in enumerate(units):struct.pack_into('<Q',p,HEADER+i*ROW_SIZE,u)
    if matrix:
        if len(matrix)!=560 or any(v not in (0,1) for v in matrix):raise ValueError('联盟快照无效')
        struct.pack_into('<560I',p,MATRIX,*matrix)
    validate_work(bytes(p));return bytes(p)


def validate_work(p):
    if len(p)!=WORK_SIZE:raise ValueError('FullClone 扩展数据长度不同')
    selection_validate(p[:480])
    tls,action,value,rawcode,x,y,n,error,done,changed,target,owner=struct.unpack_from('<QIiIff4I4x2Q',p,992)
    if action not in ACTIONS or not 0x10000<=tls<0x800000000000 or tls%8 or n>24 or error or done or changed:raise ValueError('FullClone 扩展请求无效')
    for name in ACTIONS[action]:
        ptr=struct.unpack_from('<Q',p,480+INDEX[name]*8)[0]
        if not 0x10000<=ptr<0x800000000000:raise ValueError('FullClone 扩展接口无效')
    if action in (1,11) and value not in (*range(24),24,27,-1):raise ValueError('目标玩家无效')
    if action in (3,4) and not 0<=value<24:raise ValueError('颜色必须是1至24')
    if action in (11,12) and not rawcode:raise ValueError('请填写四字符单位ID')
    if action==6 and not 0<=value<=100000:raise ValueError('英雄等级超出范围')
    if action in (9,20) and any(v not in (0,1) for v in struct.unpack_from('<560I',p,MATRIX)):raise ValueError('联盟快照无效')
    if action in (19,20) and (target not in range(28) or n):raise ValueError('指定玩家外交请求无效')
    if action==20 and (target not in (*range(24),24,27) or not owner):raise ValueError('指定玩家身份无效')


def decode_work(p,count=None):
    if len(p)!=WORK_SIZE:raise ValueError('FullClone 扩展结果不完整')
    tls,action,value,rawcode,x,y,n,error,done,changed,target,owner=struct.unpack_from('<QIiIff4I4x2Q',p,992)
    if error==1168:raise ValueError('没有所属玩家：该地图未启用目标玩家槽位')
    if error or not done or n>24:raise RuntimeError(f'扩展操作未完成：action={action}, error={error}, 已修改={changed}')
    rows=[]
    for i in range(n):
        handle,created,owner,code,level,a,b,c,team=struct.unpack_from('<3QI5i',p,HEADER+i*ROW_SIZE)
        rows.append(dict(handle=handle,created=created,owner=owner,rawcode=code,level=level,values=(a,b,c),a=a,b=b,c=c,team=team))
    verified_faults,last_fault=struct.unpack_from('<2I',p,1056)
    return dict(action=action,count=n,changed=changed,rows=rows,target=target,owner=owner,
                verified_faults=verified_faults,last_fault=last_fault,
                matrix=struct.unpack_from('<560I',p,MATRIX) if action in (8,9,19,20) else (),
                teams=struct.unpack_from('<28i',p,MATRIX+2240) if action in (8,9,19,20) else ())
