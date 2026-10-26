"""R23 completion controller. Workers own no Tk objects; selection never runs a quest."""
from __future__ import annotations
import queue
import threading
import time
import uuid
from war3_native_quest import PROOF_SECONDS,QuestExecutionResult
from war3_quest_execution import build_completion_plan


class QuestCompletionController:
    def __init__(self,runtime_provider,clock=time.monotonic,builder=build_completion_plan):
        self.provider,self.clock,self.builder=runtime_provider,clock,builder
        self.report=None;self.quest_key=None;self.plan=None;self.proof=None;self.client=None
        self.state='idle';self.message='';self.result=None;self.busy=False
        self.generation=0;self._selection=None;self._job=0;self._closed=False
        self._replies=queue.Queue();self._attempt=None

    @property
    def can_inspect(self):
        return not self.busy and not self._closed and self.report is not None and any(
            quest.key==self.quest_key for quest in self.report.quests)

    @property
    def can_execute(self):
        return bool(not self.busy and not self._closed and self.state=='ready' and self.proof and
            0<=self.clock()-self.proof.checked_at<=PROOF_SECONDS)

    @property
    def can_observe(self):
        return bool(not self.busy and not self._closed and self._attempt and self.result and self.result.may_have_run)

    def select(self,report,quest_key):
        selection=(id(report),quest_key)
        if selection==self._selection:return
        self._selection=selection;self.generation+=1;self.report=report;self.quest_key=quest_key
        self.plan=self.proof=self.client=None;self.state='idle';self.message=''

    def inspect(self):
        if not self.can_inspect:return
        report,key=self.report,self.quest_key
        def work():
            plan=self.builder(report,key)
            if not plan.eligible:return plan,None,None,'；'.join(plan.reasons)
            client=self.provider()
            if client is None:return plan,None,None,'游戏尚未连接'
            return plan,client.inspect(plan),client,''
        self.proof=None;self.state='checking';self.message='正在校验原完成入口与运行中任务实例'
        self._launch('inspect',work)

    def execute(self):
        if not self.can_execute:return
        self._attempt=(self.plan,self.proof,self.client,uuid.uuid4().hex)
        plan,proof,client,request_id=self._attempt
        self.state='executing';self.message='原完成流程正在处理；不要重复提交'
        self._launch('execute',lambda:client.execute(plan,proof,request_id))

    def observe(self):
        if not self.can_observe:return
        plan,proof,client,request_id=self._attempt
        self.message='正在只读查询上次派发状态'
        self._launch('observe',lambda:client.observe(plan,proof,request_id))

    def _launch(self,operation,work):
        self._job+=1;job,generation=self._job,self.generation;self.busy=True
        def run():
            try:value,error=work(),''
            except Exception as exc:value,error=None,str(exc)
            self._replies.put((job,generation,operation,value,error))
        threading.Thread(target=run,name='war3-quest-'+operation,daemon=True).start()

    def tick(self):
        while True:
            try:job,generation,operation,value,error=self._replies.get_nowait()
            except queue.Empty:break
            if job!=self._job:continue
            self.busy=False
            if self._closed:continue
            if generation!=self.generation:
                if operation in ('execute','observe'):
                    request_id=self._attempt[3]
                    self.result=QuestExecutionResult('unknown',request_id,
                        '派发期间所选任务或来源已变化；先前流程可能已执行，不会重试',True)
                    self.message=self.result.message;self.state='unknown'
                continue
            if error:
                self.proof=None;self.state='unavailable';self.message=error
                if operation in ('execute','observe'):
                    self.result=QuestExecutionResult('unknown',self._attempt[3],
                        '执行回包无法确认；不会重复提交：'+error,True)
                    self.message=self.result.message;self.state='unknown'
                continue
            if operation=='inspect':
                self.plan,self.proof,self.client,self.message=value
                self.state='ready' if self.proof else 'unsupported'
                if self.proof:self.message='当前原入口与任务实例已核对；证明有效期2秒，过期请重新检查'
            else:
                self.result=value;self.proof=None;self.state=value.status;self.message=value.message
        if self.state=='ready' and not self.can_execute:
            self.proof=None;self.state='expired';self.message='运行时证明已过期，请重新检查完成入口'

    def close(self):
        self.generation+=1;self._closed=True;self.proof=None
