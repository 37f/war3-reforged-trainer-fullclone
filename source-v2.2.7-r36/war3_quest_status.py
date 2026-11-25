"""R25 read-only quest binding and a bounded, name-only native query codec."""
from __future__ import annotations

from dataclasses import dataclass
import re
import struct
import time

from war3_jass import parse_jass

MAGIC=0x31535152
MAX_NAMES=128
MAX_BATCH_NAMES=16
MAX_WORDS=28
UNKNOWN='unconfirmed'


@dataclass(frozen=True)
class QuestState:
    state:str=UNKNOWN
    reason:str='尚未读取当前任务状态'
    read_at:float=0.


@dataclass(frozen=True)
class QuestStatusPlan:
    bindings:tuple[tuple[str,tuple[str,...]],...]
    unavailable:tuple[tuple[str,str],...]


def status_plan(report,cancelled=lambda:False):
    """Only unique scalar quest globals qualify; titles and BJ scratch globals do not."""
    program=parse_jass(report.snapshot.script.decode('utf-8-sig'),cancelled)
    globals_={g.name for g in program.globals if g.type_name=='quest' and not g.array}
    candidates={q.key:tuple(dict.fromkeys(n for n in q.aliases if n in globals_ and
        not n.startswith('bj_') and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,126}',n))) for q in report.quests}
    owners={}
    for key,names in candidates.items():
        for name in names:owners.setdefault(name,set()).add(key)
    bindings=[];unavailable=[];used=set()
    for key,names in candidates.items():
        if not names:reason='没有可唯一绑定的标量任务全局变量（数组、局部变量及动态任务暂不支持）'
        elif any(len(owners[n])!=1 for n in names):reason='同一任务变量关联多个定义，无法唯一匹配'
        elif len(used|set(names))>MAX_NAMES:reason='超出本轮任务变量查询上限'
        else:
            bindings.append((key,names));used.update(names);continue
        unavailable.append((key,reason))
    return QuestStatusPlan(tuple(bindings),tuple(unavailable))


def batches(names):
    batch=[];words=[0]
    for name in names:
        data=name.encode('ascii')
        if not re.fullmatch(rb'[A-Za-z_][A-Za-z_0-9]{0,126}',data):raise ValueError('任务变量名无效')
        padded=data+b'\0'*((-len(data))%8)
        record=[len(data),*struct.unpack('<'+'Q'*(len(padded)//8),padded)]
        if len(words)+len(record)>MAX_WORDS or len(batch)>=MAX_BATCH_NAMES:
            words[0]=len(batch);yield tuple(batch),tuple(words);batch=[];words=[0]
        batch.append(name);words.extend(record)
    if batch:
        words[0]=len(batch);yield tuple(batch),tuple(words)


def parse_reply(values,token,count):
    values=tuple(values)
    if len(values)!=4+5*count or values[:4]!=(MAGIC,1,token,count):
        raise RuntimeError('任务状态返回的会话、数量或协议不一致')
    rows=[]
    for i in range(count):
        error,handle,address,full,flags=values[4+i*5:9+i*5]
        if error:
            if any((handle,address,full,flags)):raise RuntimeError('无效任务状态错误记录')
        elif not 0<handle<=0xffffffff or not 0x10000<=address<0x800000000000 or not full or flags>3:
            raise RuntimeError('任务状态对象身份或布尔值无效')
        rows.append((error,handle,address,full,flags))
    return tuple(rows)


def read_states(plan,token,query,cancelled=lambda:False,clock=time.time):
    result={key:QuestState(reason=reason) for key,reason in plan.unavailable}
    names=tuple(dict.fromkeys(n for _key,aliases in plan.bindings for n in aliases));runtime={}
    for batch,words in batches(names):
        if cancelled():raise RuntimeError('任务状态读取已取消')
        runtime.update(zip(batch,parse_reply(query(token,words),token,len(batch))))
    handles={};confirmed={}
    for key,aliases in plan.bindings:
        rows=[runtime[n] for n in aliases]
        errors=[r[0] for r in rows if r[0]]
        identities={r[1:4] for r in rows if not r[0]}
        if errors:
            result[key]=QuestState(reason='运行时任务尚未创建、已销毁或变量无法读取（错误 '+str(errors[0])+'）')
        elif len(identities)!=1 or len({r[4] for r in rows})!=1:
            result[key]=QuestState(reason='任务别名指向不同实例或本轮状态发生变化，等待下次读取')
        else:
            identity=next(iter(identities));handles.setdefault(identity,[]).append(key)
            confirmed[key]=rows[0][4]
    for identity,keys in handles.items():
        for key in keys:
            flags=confirmed[key]
            if len(keys)>1:result[key]=QuestState(reason='多个任务定义匹配同一运行时实例，无法唯一匹配')
            elif flags==3:result[key]=QuestState(reason='游戏同时标记了完成和失败，状态未确认')
            else:result[key]=QuestState({0:'active',1:'completed',2:'failed'}[flags],'',clock())
    return result
