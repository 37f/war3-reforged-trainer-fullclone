"""Requested ownership around the unchanged current full-state clone ABI."""
import struct
import war3_clone_state_protocol as original
WORK_SIZE=original.WORK_SIZE+40
ABI=struct.pack('<3I',0x46333104,216,WORK_SIZE)
SIGNATURES=(('Player','(I)Hplayer;'),('GetPlayerSlotState','(Hplayer;)Hplayerslotstate;'),('ConvertPlayerSlotState','(I)Hplayerslotstate;'))


def build_work(entries,tls,*,player,**options):
    ptr=[]
    for name,sig in SIGNATURES:
        e=entries[name]
        if e.signature!=sig:raise ValueError('复制归属接口签名不同')
        ptr.append(e.handler)
    p=original.build_work(entries,tls,**options)+struct.pack('<3Q2IQ',*ptr,player,0,0)
    validate_work(p);return p


def validate_work(p):
    if len(p)!=WORK_SIZE:raise ValueError('指定归属复制事务长度不同')
    original.validate_work(p[:original.WORK_SIZE])
    ptr=struct.unpack_from('<3Q',p,original.WORK_SIZE);player,error,owner=struct.unpack_from('<2IQ',p,original.WORK_SIZE+24)
    if any(not 0x10000<=v<0x800000000000 for v in ptr) or player not in (*range(24),24,27) or error or owner:raise ValueError('指定复制归属参数无效')


def decode_work(p,count,*,expected_sources):
    player,error,owner=struct.unpack_from('<2IQ',p,original.WORK_SIZE+24)
    if error==1168:raise ValueError('没有所属玩家：该地图未启用目标玩家槽位')
    if error or not owner:raise ValueError(f'指定复制归属不可用：{error}')
    result=original.decode_work(p[:original.WORK_SIZE],count,expected_sources=expected_sources)
    if any(r['owner']!=owner for r in result['rows']):raise ValueError('复制归属读回不同')
    return result
