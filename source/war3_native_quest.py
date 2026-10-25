"""R23 typed quest runtime boundary and conservative client-side dispatch state.

The transport is deliberately separate from Tk and the source reader. A paired
game-side handler must independently revalidate every proof and persist dedup
before executing; this client's cache cannot replace that handler's ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import threading
import time

from war3_current_map_script import GameSourceFile
from war3_quest_execution import CompletionPlan

QUEST_PROTOCOL=79
PROOF_SECONDS=2.
MAX_ATTEMPTS=128
_IDENTIFIER=re.compile(r'[A-Za-z_][A-Za-z_0-9]{0,126}\Z')
_NONCE=re.compile(r'[0-9a-f]{32}\Z')


@dataclass(frozen=True)
class QuestRuntimeProof:
    connection_identity:object
    plan_id:str
    session_token:int
    helper_epoch:str
    proof_id:str
    vm:int
    quest_handle:int
    quest_object:int
    quest_full:int
    trigger_handle:int
    trigger_object:int
    trigger_full:int
    bindings_fingerprint:int
    completed:bool
    failed:bool
    discovered:bool
    checked_at:float


@dataclass(frozen=True)
class QuestRuntimeRequest:
    operation:str
    plan_id:str
    session_token:int
    quest_key:str
    quest_alias:str
    entry_trigger:str
    entry_function:str
    trigger_bindings:tuple
    chain_functions:tuple[str,...]
    script_sha256:str
    strings_sha256:str
    source:GameSourceFile
    proof:QuestRuntimeProof|None=None
    request_id:str=''


@dataclass(frozen=True)
class QuestExecutionResult:
    status:str
    request_id:str
    message:str
    may_have_run:bool
    completed:bool|None=None
    dispatch_id:str=''
    error:int=0
    already_dispatched:bool=False


def _integer(value,bits=64,minimum=0):
    if type(value) is not int or not minimum<=value<2**bits:
        raise ValueError('任务运行时返回的整数范围无效')
    return value


def _pointer(value):
    _integer(value,64,0x10000)
    if value>=0x7fffffffffff or value&7:raise ValueError('任务运行时对象地址无效')
    return value


def _nonce(value):
    if not isinstance(value,str) or not _NONCE.fullmatch(value) or value=='0'*32:
        raise ValueError('任务运行时证明标识无效')
    return value


def _source(plan):
    stamp=plan.source_snapshot.stamp
    source=stamp[1] if len(stamp)==2 else stamp[6] if len(stamp)==7 and stamp[0]=='official-casc' else None
    if not isinstance(source,GameSourceFile):raise RuntimeError('任务没有已验证的游戏来源文件')
    if (type(source.handle) is not int or not 0<source.handle<2**64 or
        len(source.file_id)!=2 or any(type(n) is not int or n<0 for n in source.file_id) or
        not source.file_id[1] or source.size<=0 or source.process_created<=0 or
        source.modified>source.process_created):
        raise RuntimeError('任务来源没有可在游戏侧复核的实际持有文件句柄')
    return source


def _request(plan,operation,proof=None,request_id=''):
    if not isinstance(plan,CompletionPlan) or not plan.eligible:
        raise RuntimeError('该任务尚未通过原完成流程的静态资格检查')
    names=(plan.quest_alias,plan.entry_trigger,plan.entry_function,*plan.chain_functions)
    if any(not isinstance(name,str) or not _IDENTIFIER.fullmatch(name) for name in names):
        raise RuntimeError('任务标识符超出当前执行桥支持范围')
    if not 1<=len(plan.trigger_bindings)<=32 or len(plan.chain_functions)>256:
        raise RuntimeError('任务原完成流程超出当前执行桥规模上限')
    for trigger,actions in plan.trigger_bindings:
        if (not _IDENTIFIER.fullmatch(trigger) or not 1<=len(actions)<=16 or
            any(not _IDENTIFIER.fullmatch(action) for action in actions)):
            raise RuntimeError('原触发器动作绑定超出支持范围')
    if dict(plan.trigger_bindings).get(plan.entry_trigger)!=(plan.entry_function,):
        raise RuntimeError('原入口与触发器动作绑定不一致')
    source=_source(plan)
    identity=(plan.snapshot_token,plan.quest_key,plan.quest_alias,plan.entry_trigger,
        plan.entry_function,plan.trigger_bindings,plan.chain_functions,plan.script_sha256,
        plan.strings_sha256,source.file_id,source.size,source.modified,source.process_created,source.handle)
    plan_id=hashlib.sha256(json.dumps(identity,ensure_ascii=True,separators=(',',':')).encode('ascii')).hexdigest()
    return QuestRuntimeRequest(operation,plan_id,plan.snapshot_token,plan.quest_key,
        plan.quest_alias,plan.entry_trigger,plan.entry_function,plan.trigger_bindings,
        plan.chain_functions,plan.script_sha256,plan.strings_sha256,source,proof,request_id)


class QuestRuntimeClient:
    def __init__(self,query,identity,source_validator,clock=time.monotonic):
        self.query,self.identity,self.source_validator=query,identity,source_validator
        self.clock=clock;self._lock=threading.Lock();self._attempts={};self._requests={}

    def inspect(self,plan:CompletionPlan)->QuestRuntimeProof:
        request=_request(plan,'inspect');identity=self.identity()
        if identity!=plan.snapshot_identity:raise RuntimeError('游戏连接与任务快照不一致')
        if not self.source_validator(plan):raise RuntimeError('任务脚本来源或地图会话已变化')
        value=self.query(request);checked=self.clock()
        if not isinstance(value,dict):raise ValueError('任务运行时证明类型无效')
        required={'protocol','kind','plan_id','session_token','helper_epoch','proof_id','vm',
            'quest_handle','quest_object','quest_full','trigger_handle','trigger_object',
            'trigger_full','bindings_fingerprint','source_file_id','completed','failed','discovered'}
        if set(value)!=required:raise ValueError('任务运行时证明字段不完整或版本不匹配')
        if (value['protocol']!=QUEST_PROTOCOL or type(value['protocol']) is not int or
            value['kind']!='inspected' or value['plan_id']!=request.plan_id or
            value['session_token']!=request.session_token or value['source_file_id']!=request.source.file_id):
            raise ValueError('任务运行时证明不属于当前计划、来源或会话')
        for key in ('completed','failed','discovered'):
            if type(value[key]) is not bool:raise ValueError('任务状态返回类型不是 boolean')
        if value['completed'] or value['failed']:raise RuntimeError('该运行中任务已完成或已失败，不能再次派发')
        proof=QuestRuntimeProof(identity,request.plan_id,_integer(value['session_token'],minimum=1),
            _nonce(value['helper_epoch']),_nonce(value['proof_id']),_pointer(value['vm']),
            _integer(value['quest_handle'],32,1),_pointer(value['quest_object']),
            _integer(value['quest_full'],minimum=1),_integer(value['trigger_handle'],32,1),
            _pointer(value['trigger_object']),_integer(value['trigger_full'],minimum=1),
            _integer(value['bindings_fingerprint'],minimum=1),value['completed'],value['failed'],
            value['discovered'],checked)
        if self.identity()!=identity or not self.source_validator(plan):
            raise RuntimeError('读取任务证明时游戏连接、会话或来源已变化')
        if self.clock()-checked>PROOF_SECONDS:raise RuntimeError('任务运行时证明已过期，请重新检查')
        return proof

    @staticmethod
    def _rejected(request_id,message):
        return QuestExecutionResult('rejected-before-dispatch',request_id,message,False)

    @staticmethod
    def _unknown(request_id,message):
        return QuestExecutionResult('unknown',request_id,message,True)

    def execute(self,plan:CompletionPlan,proof:QuestRuntimeProof,request_id:str)->QuestExecutionResult:
        if not isinstance(proof,QuestRuntimeProof):return self._rejected(request_id,'缺少类型化的运行时证明')
        try:_nonce(request_id)
        except ValueError as exc:return self._rejected(request_id,str(exc))
        key=(proof.session_token,proof.vm,proof.quest_full,proof.quest_object)
        # Look up in-flight requests before transport or expiry checks. A second
        # click/reinspection cannot make a possibly dispatched instance retryable.
        with self._lock:
            if request_id in self._requests:
                original_key,result=self._requests[request_id]
                return result if original_key==key else self._rejected(request_id,'请求标识已绑定另一个任务实例')
            if key in self._attempts:return self._requests[self._attempts[key]][1]
        try:
            request=_request(plan,'execute',proof,request_id)
            if (proof.plan_id!=request.plan_id or proof.session_token!=request.session_token or
                proof.connection_identity!=self.identity() or plan.snapshot_identity!=self.identity()):
                return self._rejected(request_id,'任务证明不属于当前计划或游戏连接')
            if not 0<=self.clock()-proof.checked_at<=PROOF_SECONDS:
                return self._rejected(request_id,'任务运行时证明已过期，请重新检查')
            if not self.source_validator(plan):return self._rejected(request_id,'任务脚本来源或地图会话已变化')
        except Exception as exc:return self._rejected(request_id,str(exc))
        pending=self._unknown(request_id,'请求正在处理；可能已派发，不会重复提交')
        with self._lock:
            if request_id in self._requests:
                original_key,result=self._requests[request_id]
                return result if original_key==key else self._rejected(request_id,'请求标识已绑定另一个任务实例')
            if key in self._attempts:return self._requests[self._attempts[key]][1]
            if len(self._requests)>=MAX_ATTEMPTS:return self._rejected(request_id,'本连接任务请求记录已满')
            self._attempts[key]=request_id;self._requests[request_id]=(key,pending)
        try:
            value=self.query(request)
            result=self._parse_execution(request,value)
            if self.identity()!=proof.connection_identity:
                result=self._unknown(request_id,'派发期间游戏连接发生变化，执行结果未知；不会重试')
        except Exception as exc:
            result=self._unknown(request_id,'派发回包无法确认，执行结果未知；不会重试：'+str(exc))
        with self._lock:
            self._requests[request_id]=(key,result)
            if result.status=='rejected-before-dispatch':self._attempts.pop(key,None)
        return result

    def _parse_execution(self,request,value):
        required={'protocol','kind','plan_id','session_token','helper_epoch','request_id',
            'dispatch_id','status','dispatched','completed','message','error','already_dispatched'}
        if not isinstance(value,dict) or set(value)!=required:raise ValueError('任务执行回包字段无效')
        if (type(value['protocol']) is not int or value['protocol']!=QUEST_PROTOCOL or
            value['kind']!='execution-result' or value['plan_id']!=request.plan_id or
            value['session_token']!=request.session_token or value['request_id']!=request.request_id or
            value['helper_epoch']!=request.proof.helper_epoch):
            raise ValueError('任务执行回包不属于当前请求或原 helper 状态')
        status=value['status'];completed=value['completed'];dispatched=value['dispatched']
        if status not in ('rejected-before-dispatch','dispatched','observed-completed','unknown'):
            raise ValueError('未知任务执行状态')
        if type(dispatched) is not bool or completed is not None and type(completed) is not bool:
            raise ValueError('任务执行状态的类型无效')
        if ((status=='observed-completed' and (not dispatched or completed is not True)) or
            (status=='dispatched' and not dispatched) or
            (status=='rejected-before-dispatch' and dispatched)):
            raise ValueError('任务派发与完成读回状态不一致')
        if not isinstance(value['message'],str) or len(value['message'])>4096:
            raise ValueError('任务执行说明无效')
        if type(value['already_dispatched']) is not bool:raise ValueError('任务去重标记类型无效')
        error=_integer(value['error'],32)
        dispatch_id=_nonce(value['dispatch_id']) if dispatched or value['already_dispatched'] else ''
        return QuestExecutionResult(status,request.request_id,value['message'],
            dispatched or status=='unknown',completed,dispatch_id,error,value['already_dispatched'])
