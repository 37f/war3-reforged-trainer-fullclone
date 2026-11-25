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
    ('GetPlayerNeutralAggressive','()I'), ('GetBJPlayerNeutralVictim','()I'),
    ('GetBJPlayerNeutralExtra','()I'), ('GetPlayerNeutralPassive','()I'),
)
# R31.2 retires slots34/35; surviving native slots retain their original ABI.
INDEX = {name:i if i<34 else i+2 for i,(name,_) in enumerate(SIGNATURES)}
SIGNATURE_BY_NAME = dict(SIGNATURES)
COMMON = ('GetOwningPlayer','GetPlayerId','Player','GetPlayerTeam')
PLAYERS = COMMON+('GetPlayerNeutralAggressive','GetBJPlayerNeutralVictim',
                  'GetBJPlayerNeutralExtra','GetPlayerNeutralPassive')
DIPLOMACY = PLAYERS+('ConvertAllianceType','GetPlayerAlliance')
ACTIONS = {
    0: COMMON, 1: COMMON+('GetPlayerSlotState','ConvertPlayerSlotState','SetUnitOwner'),
    2: ('GetUnitState','SetUnitState','ConvertUnitState'),
    3: ('SetUnitColor','ConvertPlayerColor'), 4: ('GetOwningPlayer','SetPlayerColor','ConvertPlayerColor'),
    5: COMMON+('GroupEnumUnitsOfPlayer','IsUnitType','ConvertUnitType','ReviveHero','GetWidgetLife'),
    6: ('SetHeroLevel','SuspendHeroXP','IsSuspendedXP','UnitStripHeroLevel'), 7: ('GetHeroStr','GetHeroAgi','GetHeroInt','SetHeroStr','SetHeroAgi','SetHeroInt'),
    8: DIPLOMACY,
    9: DIPLOMACY+('SetPlayerAlliance',),
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
    19: DIPLOMACY,
    20: DIPLOMACY+('SetPlayerAlliance',),
    21: DIPLOMACY+('SetPlayerAlliance',),
    22: PLAYERS+('GetPlayerSlotState','ConvertPlayerSlotState'),
    23: PLAYERS+('GetPlayerSlotState','ConvertPlayerSlotState','SetUnitOwner'),
}
SLOTS=64
ROW_SIZE=48
HEADER=1088
MATRIX=HEADER+24*ROW_SIZE
WORK_SIZE=MATRIX+28*20*4+28*4
ABI=struct.pack('<3I',0x46333105,216,WORK_SIZE)
TEAM_PLAYERS=(*range(24),24,27)
TEAM_MASK=sum(1<<p for p in TEAM_PLAYERS)
ALL_TEAM_SLOTS=(1<<28)-1
TEAM_ORDER=MATRIX+28*20*4


def action_signatures(action,target=0):
    return ACTIONS[action]+PLAYERS[len(COMMON):] if action==10 and target else ACTIONS[action]


def build_work(entries,tls,action,*,value=0,rawcode=0,x=0.,y=0.,target=0,expected_owner=0,units=(),matrix=(),resolver=0,restore_records=(),owner_moves=()):
    if type(action) is not int or action not in ACTIONS:raise ValueError('未知扩展操作')
    if not (math.isfinite(x) and math.isfinite(y) and abs(x)<=1e6 and abs(y)<=1e6):raise ValueError('扩展坐标无效')
    if type(value) is not int or not -1<=value<=1000000000:raise ValueError('扩展数值无效')
    if len(units)>24 or any(type(u) is not int or u<=0 for u in units) or len(set(units))!=len(units):raise ValueError('扩展对象身份无效')
    if action==21:
        value=len(restore_records)
    p=bytearray(WORK_SIZE);p[:480]=selection_work(entries)
    for name in action_signatures(action,target):
        e=entries[name]
        if e.name!=name or e.signature!=SIGNATURE_BY_NAME[name]:raise ValueError('扩展接口签名不同：'+name)
        struct.pack_into('<Q',p,480+INDEX[name]*8,e.handler)
    if action in (16,17,18,22,23):struct.pack_into('<Q',p,480+63*8,resolver)
    count=len(owner_moves) if action==23 else len(units)
    struct.pack_into('<QIiIff4I4x2Q',p,992,tls,action,value,rawcode,x,y,count,0,0,0,target,expected_owner)
    if action==23:
        if units or matrix or not 1<=count<=24:raise ValueError('归属修改数量无效')
        for i,(unit,full,current,code,slot,destination,alternate) in enumerate(owner_moves):
            struct.pack_into('<3QI5i',p,HEADER+i*ROW_SIZE,unit,full,current,code,0,slot,0,0,0)
            struct.pack_into('<2Q',p,MATRIX+i*16,destination,alternate)
    # Header has an independent input/output layout; keep rows/matrix outside it.
    for i,u in enumerate(units):struct.pack_into('<Q',p,HEADER+i*ROW_SIZE,u)
    if matrix:
        if len(matrix)!=560 or any(v not in (0,1) for v in matrix):raise ValueError('联盟快照无效')
        struct.pack_into('<560I',p,MATRIX,*matrix)
    if action==21:
        if not 1<=value<=len(TEAM_PLAYERS):raise ValueError('原队伍记录数量无效')
        for i,(slot,owner,flags,present) in enumerate(restore_records):
            if type(slot) is not int or slot not in TEAM_PLAYERS or type(owner) is not int or not 0<owner<2**64:
                raise ValueError('原队伍记录的玩家无效，未执行批量恢复')
            if len(flags)!=560 or any(v not in (0,1) for v in flags):
                raise ValueError('原队伍记录不完整，未执行批量恢复')
            if type(present) is not int or not 0<=present<=ALL_TEAM_SLOTS or not present&(1<<slot):
                raise ValueError('原队伍记录的槽位范围无效')
            # Flags 6 and 7 are shared control and are never restored here.
            diplomacy=(v for bit,v in enumerate(flags) if bit%10 not in (6,7))
            packed=sum(v<<bit for bit,v in enumerate(diplomacy))
            offset=MATRIX+slot*80
            struct.pack_into('<QI',p,offset,owner,present)
            p[offset+12:offset+68]=packed.to_bytes(56,'little')
            struct.pack_into('<i',p,TEAM_ORDER+4*i,slot)
    validate_work(bytes(p));return bytes(p)


def validate_work(p):
    if len(p)!=WORK_SIZE:raise ValueError('FullClone 扩展数据长度不同')
    selection_validate(p[:480])
    tls,action,value,rawcode,x,y,n,error,done,changed,target,owner=struct.unpack_from('<QIiIff4I4x2Q',p,992)
    if action not in ACTIONS or not 0x10000<=tls<0x800000000000 or tls%8 or n>24 or error or done or changed:raise ValueError('FullClone 扩展请求无效')
    for name in action_signatures(action,target):
        ptr=struct.unpack_from('<Q',p,480+INDEX[name]*8)[0]
        if not 0x10000<=ptr<0x800000000000:raise ValueError('FullClone 扩展接口无效')
    if action in (1,11) and value not in (*range(24),24,27,-1):raise ValueError('目标玩家无效')
    if action in (3,4) and not 0<=value<24:raise ValueError('颜色必须是1至24')
    if action in (11,12) and not rawcode:raise ValueError('请填写四字符单位ID')
    if action==6 and not 0<=value<=100000:raise ValueError('英雄等级超出范围')
    if action==10 and (value not in (-1,0,1,2,3) or
            (target and (target-1 not in TEAM_PLAYERS or n or (value>=0 and not owner)))):
        raise ValueError('指定玩家控制请求无效')
    if action in (9,20) and any(v not in (0,1) for v in struct.unpack_from('<560I',p,MATRIX)):raise ValueError('联盟快照无效')
    if action in (19,20) and (target not in range(28) or n):raise ValueError('指定玩家外交请求无效')
    if action==20 and (target not in TEAM_PLAYERS or not owner):raise ValueError('指定玩家身份无效')
    if action==21:
        if not 1<=value<=len(TEAM_PLAYERS) or target or owner or n:
            raise ValueError('原队伍恢复请求无效')
        order=struct.unpack_from(f'<{value}i',p,TEAM_ORDER)
        if len(set(order))!=value or any(slot not in TEAM_PLAYERS or
                not struct.unpack_from('<Q',p,MATRIX+slot*80)[0] for slot in order):
            raise ValueError('原队伍记录的玩家无效，未执行批量恢复')
    if action in (22,23):
        resolver=struct.unpack_from('<Q',p,480+63*8)[0]
        if not 0x10000<=resolver<0x800000000000 or target or owner:raise ValueError('归属请求未绑定游戏对象解析')
    if action==22 and (value not in (-1,*TEAM_PLAYERS) or n):raise ValueError('目标玩家无效')
    if action==23:
        if value not in (0,1) or not n:raise ValueError('归属修改请求无效')
        seen=set()
        for i in range(n):
            unit,full,current,code,level,slot,status,c,team=struct.unpack_from('<3QI5i',p,HEADER+i*ROW_SIZE)
            destination,alternate=struct.unpack_from('<2Q',p,MATRIX+i*16)
            if not all((unit,full,current,code,destination)) or full in seen or any((level,status,c,team)) or not 0<=slot<28 or (not value and alternate):
                raise ValueError('单位或玩家的归属身份无效')
            seen.add(full)


class DiplomacySlotUnavailable(ValueError):
    """The requested player could not be bound before any diplomacy write."""

    def __init__(self,slot):
        super().__init__(f'无法确认玩家 {slot+1} 的槽位，未修改外交模板。请重新读取玩家信息')


def decode_work(p,count=None):
    if len(p)!=WORK_SIZE:raise ValueError('FullClone 扩展结果不完整')
    tls,action,value,rawcode,x,y,n,error,done,changed,target,owner=struct.unpack_from('<QIiIff4I4x2Q',p,992)
    if action in (19,20) and error in (1168,1237):
        raise DiplomacySlotUnavailable(target)
    if action in (9,20) and error==1238:
        raise ValueError('玩家槽位在套用前发生变化，未修改外交模板。请重新读取玩家信息')
    if error==1168:raise ValueError('没有所属玩家：该地图未启用目标玩家槽位')
    if error or not done or n>24:raise RuntimeError(f'扩展操作未完成：action={action}, error={error}, 已修改={changed}')
    if action==21:
        if ((target|owner)&~TEAM_MASK or target&owner or target.bit_count()!=changed
                or (target|owner).bit_count()!=value):
            raise RuntimeError('批量恢复回执不完整，原记录保留')
        return dict(changed=changed,total=value,
                    restored=tuple(p for p in TEAM_PLAYERS if target&(1<<p)),
                    skipped=tuple(p for p in TEAM_PLAYERS if owner&(1<<p)))
    destination=owner
    rows=[]
    for i in range(n):
        handle,created,owner,code,level,a,b,c,team=struct.unpack_from('<3QI5i',p,HEADER+i*ROW_SIZE)
        rows.append(dict(handle=handle,created=created,owner=owner,rawcode=code,level=level,values=(a,b,c),a=a,b=b,c=c,team=team))
    if action==10 and target and (len(rows)!=1 or rows[0]['a']!=target-1 or
            not rows[0]['owner'] or not rows[0]['created'] or (destination and rows[0]['owner']!=destination)):
        raise RuntimeError('指定玩家控制回执无效，原记录保留')
    if action==22 and (changed or any(r['b'] not in (1,2) for r in rows) or (value>=0 and n and (not destination or rawcode!=value))):
        raise RuntimeError('选中单位的归属读回不完整')
    if action==23 and (changed>n or any(r['b'] not in (1,2,3,4,5) for r in rows)):
        raise RuntimeError('归属修改回执不完整，原玩家记录保留')
    if action==22:
        identified=[r for r in rows if r['b']==1]
        if len({r['created'] for r in identified})!=len(identified) or any(
                not all((r['handle'],r['created'],r['owner'],r['rawcode'])) or not 0<=r['a']<28 for r in identified):
            raise RuntimeError('选中单位的归属读回身份无效')
        return dict(rows=rows,destination=destination)
    verified_faults,last_fault=struct.unpack_from('<2I',p,1056)
    return dict(action=action,count=n,changed=changed,rows=rows,target=target,owner=owner,
                verified_faults=verified_faults,last_fault=last_fault,
                matrix=struct.unpack_from('<560I',p,MATRIX) if action in (8,9,19,20) else (),
                teams=struct.unpack_from('<28i',p,MATRIX+2240) if action in (8,9,19,20) else ())
