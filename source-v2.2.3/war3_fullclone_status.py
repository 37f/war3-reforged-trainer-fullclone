"""Match current quest globals by symbol name; titles alone are never identities."""
import struct
import time
from war3_fullclone_runtime import read_context
from war3_fullclone_source import _string,check_source
from war3_quest_status import status_plan


def _globals(trainer,proof,names):
    found={};visited=set();start=time.monotonic();table=proof['metadata']['symbols']
    with read_context(trainer) as (engine,memory,registry,mode,natives):
        mask=memory.read_u32(table+0x40);array=memory.read_u64(table+0x30)
        if mask>65535 or (mask+1)&mask:raise ValueError('脚本符号表布局不同')
        buckets=memory.read(array,(mask+1)*24)
        for b in range(mask+1):
            offset=struct.unpack_from('<i',buckets,b*24)[0];node=struct.unpack_from('<Q',buckets,b*24+16)[0]
            if offset< -256 or offset>256 or offset%8:raise ValueError('脚本符号链偏移无效')
            chain=set()
            while node and not node&1:
                if node in chain or len(visited)>100000 or time.monotonic()-start>3:raise ValueError('脚本符号表查询超出保护上限')
                chain.add(node)
                if node not in visited:
                    visited.add(node)
                    try:
                        name=_string(memory,memory.read_u64(node+0x28),128)
                        if name in names:
                            types=memory.read(node+0x30,8)
                            if types!=struct.pack('<2I',7,7):raise ValueError('任务变量类型不同')
                            handle=memory.read_u64(node+0x38)
                            if name in found:raise ValueError('任务变量重复，无法唯一绑定')
                            found[name]=(node,handle)
                    except OSError:pass
                node=memory.read_u64(node+offset+8)
    return found


def query_states(trainer,report,proof):
    plan=status_plan(report);names={n for _,aliases in plan.bindings for n in aliases}
    result={key:dict(state='状态未确认',reason=reason) for key,reason in plan.unavailable}
    if not names:return result
    engine=trainer._engine_instance_24268()
    with engine.session.lock:
        if not check_source(trainer,proof):raise ValueError('任务来源已变化')
        found=_globals(trainer,proof,names);requests=[];keys=[]
        for key,aliases in plan.bindings:
            rows=[found[n] for n in aliases if n in found and found[n][1]]
            if not rows:result[key]=dict(state='状态未确认',reason='任务尚未创建或未找到当前变量');continue
            if len({h for _,h in rows})!=1:result[key]=dict(state='状态未确认',reason='任务别名当前指向不同实例');continue
            requests.append(rows[0]);keys.append(key)
        if requests:
            from war3_fullclone_status_protocol import SIGNATURES,build_work,decode_work
            meta=proof['metadata']
            rows=engine._execute('fullclone_status',tuple(n for n,_ in SIGNATURES),
                lambda entries,tls:build_work(entries,tls,**{k:meta[k] for k in ('vm','symbols','host')},rows=requests),decode_work,{})
            if not check_source(trainer,proof):raise ValueError('任务状态读取期间地图已变化')
            for key,row in zip(keys,rows):
                if row['error']:result[key]=dict(state='状态未确认',reason='任务实例在读取期间变化')
                else:result[key]=dict(state='已失败' if row['failed'] else '已完成' if row['completed'] else '进行中' if row['discovered'] else '未触发',reason='当前地图唯一任务变量的原生状态')
        return result
