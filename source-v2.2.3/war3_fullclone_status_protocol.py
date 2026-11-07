"""Read-only quest getters bound to exact current scalar global variables."""
import struct
ABI=struct.pack('<3I',0x46333103,216,0)
SIGNATURES=(('IsQuestCompleted','(Hquest;)B'),('IsQuestFailed','(Hquest;)B'),('IsQuestDiscovered','(Hquest;)B'))


def build_work(entries,tls,*,vm,symbols,host,rows):
    ptr=[]
    for name,sig in SIGNATURES:
        e=entries[name]
        if e.signature!=sig:raise ValueError('任务状态接口签名不同')
        ptr.append(e.handler)
    p=struct.pack('<7Q6I',*ptr,tls,vm,symbols,host,len(rows),0,0,0,0,0)
    p+=b''.join(struct.pack('<2Q4I',node,handle,0,0,0,0) for node,handle in rows)
    validate_work(p);return p


def validate_work(p):
    if len(p)<80 or (len(p)-80)%32:raise ValueError('任务状态数据长度不同')
    ptrs=struct.unpack_from('<7Q',p);count,error,done,*reserved=struct.unpack_from('<6I',p,56)
    if any(not 0x10000<=v<0x800000000000 for v in ptrs) or not 1<=count<=128 or len(p)!=80+count*32 or error or done or any(reserved):raise ValueError('任务状态上下文无效')
    for i in range(count):
        node,handle=struct.unpack_from('<2Q',p,80+32*i)
        if not 0x10000<=node<0x800000000000 or not 0<handle<=0xffffffff or any(p[80+32*i+16:80+32*(i+1)]):raise ValueError('任务状态身份无效')


def decode_work(p,_count=None):
    count,error,done,*_=struct.unpack_from('<6I',p,56)
    if error or done!=1 or count>128 or len(p)!=80+count*32:raise ValueError(f'任务状态上下文已改变：{error}')
    rows=[]
    for i in range(count):
        node,handle,completed,failed,discovered,error=struct.unpack_from('<2Q4I',p,80+32*i)
        rows.append(dict(node=node,handle=handle,completed=bool(completed),failed=bool(failed),discovered=bool(discovered),error=error))
    return rows
