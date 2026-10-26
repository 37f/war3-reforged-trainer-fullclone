"""R22 analysis plus explicit R23 completion. Workers never access Tk objects."""
from __future__ import annotations

from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from war3_quest_analysis import analyze_quests
from war3_quest_completion_ui import QuestCompletionController
from war3_ui_i18n import translate_ui_text

VALIDATION_SECONDS=2.


class QuestAnalysisController:
    def __init__(self,source_client_provider,analyzer=analyze_quests,clock=time.monotonic):
        self.provider=source_client_provider;self.analyzer=analyzer;self.clock=clock
        self.replies=queue.Queue();self.report=None;self.state='idle';self.error=''
        self.checked_at=0.;self.detected_at='';self.generation=0;self.busy=False
        self._visible=False;self._closed=False;self._auto=True;self._next_poll=0.
        self._stop=threading.Event();self._job=0;self._identity=None

    def invalidate(self,reason=''):
        self._stop.set();self.generation+=1;self.report=None;self.checked_at=0.
        self.error=reason;self.state='changed' if reason else 'idle';self._next_poll=0.;self._identity=None

    def detect(self):
        if self._closed:return
        self.invalidate();self._auto=True

    def cancel(self):
        self.invalidate();self._auto=False;self.state='cancelled'

    def close(self):
        self.invalidate();self._closed=True;self._auto=False;self.state='closed'

    def _client(self):
        return self.provider() if callable(self.provider) else self.provider

    def _identity_now(self):
        try:
            client=self._client()
            return client.identity() if client is not None else None
        except Exception:return None

    def tick(self,visible):
        if self._closed:
            self._drain();return
        if visible!=self._visible:
            self.invalidate();self._visible=visible;self._auto=True
        if visible and self._identity is not None and self._identity_now()!=self._identity:
            self.invalidate('游戏连接已变化')
        self._drain()
        # Expiry also applies to an already published report while a helper
        # check is pending; queue delivery is not the only way time advances.
        if visible and self.report is not None and self.clock()-self.checked_at>VALIDATION_SECONDS:
            self.report=None;self.checked_at=0.;self.state='changed'
            self.error='会话验证已过期，正在重新检索';self._next_poll=self.clock()
        if not visible or self.busy or not self._auto or self.clock()<self._next_poll:return
        try:client=self._client()
        except Exception as exc:
            self.error=str(exc);self.state='unavailable';self._next_poll=self.clock()+3;return
        if client is None:
            self.state='disconnected';self.error='';self._next_poll=self.clock()+2;return
        self._launch(client,'check' if self.report is not None else 'read')

    def _launch(self,client,operation):
        self._job+=1;job=self._job;generation=self.generation
        self._stop=threading.Event();stop=self._stop
        self._identity=client.identity();identity=self._identity;snapshot=self.report.snapshot if self.report else None
        self.busy=True;self._next_poll=self.clock()+1
        if operation=='read':self.state='reading';self.error=''
        def work():
            try:
                if operation=='read':
                    source=client.read(stop.is_set)
                    if stop.is_set():return
                    self.replies.put((job,generation,'analyzing',None,'',0.,identity))
                    value=self.analyzer(source,stop.is_set)
                    if stop.is_set():return
                    valid=client.check(source)
                else:
                    value=None;valid=client.check(snapshot)
                # This is the actual worker validation time, never the Tk dequeue time.
                checked=self.clock()
                self.replies.put((job,generation,'result' if operation=='read' else 'checked',
                    value,'' if valid else '地图会话或来源已变化',checked,identity))
            except Exception as exc:
                self.replies.put((job,generation,'error',None,str(exc),0.,identity))
            finally:self.replies.put((job,generation,'finished',None,'',0.,identity))
        threading.Thread(target=work,name='war3-current-map-quests',daemon=True).start()

    def _drain(self):
        while True:
            try:job,generation,phase,value,error,checked,identity=self.replies.get_nowait()
            except queue.Empty:break
            if phase=='finished':
                if job==self._job:self.busy=False
                continue
            if self._closed or not self._visible or generation!=self.generation or job!=self._job:continue
            if phase=='analyzing':self.state='analyzing';continue
            if error:
                self.report=None;self.checked_at=0.;self.error=error
                self.state='changed' if phase!='error' else 'unavailable'
                self._next_poll=self.clock()+(3 if phase=='error' else 0);continue
            if self._identity_now()!=identity:
                self.invalidate('游戏连接已变化');continue
            if self.clock()-checked>VALIDATION_SECONDS:
                self.report=None;self.state='changed';self.error='会话验证已过期，正在重新检索'
                self._next_poll=self.clock()+.1;continue
            if phase=='result':
                if value.snapshot.identity!=identity:
                    self.invalidate('游戏连接已变化');continue
                self.report=value;self.detected_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elif self.report is None:
                # A fresh check cannot resurrect the report that expired while
                # it ran. Complete the worker, then request a new source read.
                self.state='changed';self._next_poll=self.clock();continue
            self.checked_at=checked;self.state='partial' if self.report and self.report.partial else 'ready'
            self.error='';self._next_poll=self.clock()+1


_STATES={
    'idle':('打开本页后自动只读检索当前地图。','Open this page to scan the active map (read only).'),
    'reading':('正在确认当前章节并读取脚本…','Confirming active chapter and reading script…'),
    'analyzing':('正在分析任务、完成与失败条件…','Analyzing quests and completion/failure rules…'),
    'disconnected':('未连接游戏，请先连接并进入地图。','Not connected. Connect and enter a map first.'),
    'ready':('脚本静态分析完成','Static script analysis complete'),
    'partial':('脚本部分解析：请查看覆盖缺口和条件证据','Static script analysis is partial: see coverage gaps and evidence'),
    'changed':('地图会话、连接或来源已变化，旧报告已清除','Map session, connection or source changed; previous report cleared'),
    'unavailable':('无法分析当前脚本','Current script analysis unavailable'),
    'cancelled':('检索已取消，点击重新检索可继续。','Scan cancelled. Click Scan again to resume.'),
    'closed':('任务页已关闭','Quest page closed'),
}
_KINDS={'quest':('任务定义','Quest definition'),'coverage':('覆盖情况','Coverage'),
    'victory':('关卡直接胜利','Direct victory'),'defeat':('关卡直接失败','Direct defeat'),
    'unknown-result':('未确认结算','Unresolved result'),'unassociated':('未关联条件','Unassociated rule')}


class QuestAnalysisUI:
    def __init__(self,root,language,source_client_provider,runtime_client_provider=lambda:None):
        self.root,self.language=root,language
        self.controller=QuestAnalysisController(source_client_provider)
        self.completion=QuestCompletionController(runtime_client_provider)
        self.execution_status=tk.StringVar(root,'')
        self._preview_key=None;self._preview_complete=False
        self.source=tk.StringVar(root,'');self.status=tk.StringVar(root,'');self.search=tk.StringVar(root,'')
        self.panel=None;self._labels=[];self._rows={};self._render_key=None;self._after=None;self._closed=False
        self._after=root.after(80,self._poll)

    def text(self,zh,en):return zh if self.language()=='zh' else en

    def _label(self,widget,zh,en):
        self._labels.append((widget,zh,en));widget.configure(text=self.text(zh,en));return widget

    def add_controls(self,tab):
        self.panel=tab
        toolbar=ttk.Frame(tab);toolbar.pack(fill='x',pady=(0,6))
        self.refresh_button=self._label(ttk.Button(toolbar,command=self.detect),'重新检索','Scan again')
        self.refresh_button.pack(side='left')
        self.cancel_button=self._label(ttk.Button(toolbar,command=self.cancel),'取消检索','Cancel scan')
        self.cancel_button.pack(side='left',padx=6)
        self._label(ttk.Label(toolbar),'搜索任务、变量或条件','Search quest, variable or condition').pack(side='left',padx=(12,4))
        ttk.Entry(toolbar,textvariable=self.search,width=38).pack(side='left',fill='x',expand=True)
        self.notice=self._label(ttk.Label(tab,wraplength=1120),
            '任务列表是脚本静态定义，并非任务当前进度。检查完成入口后，仅对已核对的运行中任务开放原流程执行；不支持的上下文明确拒绝。',
            'The list contains static definitions, not live progress. Original-flow execution requires a verified live quest and entry; unsupported contexts are refused.')
        self.notice.pack(fill='x',pady=(0,5))
        ttk.Label(tab,textvariable=self.status,wraplength=1120).pack(fill='x',pady=(0,5))
        ttk.Label(tab,textvariable=self.source,wraplength=1120).pack(fill='x',pady=(0,8))
        execution=ttk.Frame(tab);execution.pack(fill='x',pady=(0,5))
        self.inspect_button=self._label(ttk.Button(execution,command=self.inspect_completion),
            '检查完成入口','Check completion entry')
        self.inspect_button.pack(side='left')
        self.execute_button=self._label(ttk.Button(execution,command=self.execute_completion),
            '完成此任务（原流程）','Complete quest (original flow)')
        self.execute_button.pack(side='left',padx=6)
        self.observe_button=self._label(ttk.Button(execution,command=self.observe_completion),
            '读取执行状态','Read dispatch status')
        self.observe_button.pack(side='left')
        ttk.Label(tab,textvariable=self.execution_status,wraplength=1120).pack(fill='x',pady=(0,6))
        panes=ttk.Panedwindow(tab,orient='horizontal');panes.pack(fill='both',expand=True)
        left=ttk.Frame(panes);right=ttk.Frame(panes);panes.add(left,weight=1);panes.add(right,weight=3)
        self.tree=ttk.Treeview(left,columns=('kind','title'),show='headings',height=18,selectmode='browse')
        self.tree.column('kind',width=110,stretch=False);self.tree.column('title',width=240)
        self.tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview);scroll.grid(row=0,column=1,sticky='ns')
        self.tree.configure(yscrollcommand=scroll.set);left.rowconfigure(0,weight=1);left.columnconfigure(0,weight=1)
        self.detail=tk.Text(right,wrap='word',state='disabled',width=75,height=22)
        self.detail.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(right,orient='vertical',command=self.detail.yview);scroll.grid(row=0,column=1,sticky='ns')
        self.detail.configure(yscrollcommand=scroll.set);right.rowconfigure(0,weight=1);right.columnconfigure(0,weight=1)
        self.tree.bind('<<TreeviewSelect>>',lambda _event:self.show_selected())
        self.search.trace_add('write',lambda *_args:self.render_rows())
        self.refresh_language()

    def detect(self):self.controller.detect();self.render()
    def cancel(self):self.controller.cancel();self.render()
    def invalidate(self,reason=''):self.controller.invalidate(reason);self.render()

    def close(self):
        self._closed=True;self.controller.close();self.completion.close()
        if self._after is not None:
            try:self.root.after_cancel(self._after)
            except tk.TclError:pass
        self._after=None

    def _poll(self):
        if self._closed:return
        visible=bool(self.panel is not None and self.panel.winfo_ismapped())
        self.controller.tick(visible);self.completion.tick();self.render()
        self._after=self.root.after(80,self._poll)

    def refresh_language(self):
        for widget,zh,en in self._labels:widget.configure(text=self.text(zh,en))
        if self.panel is not None:
            self.tree.heading('kind',text=self.text('类别','Type'));self.tree.heading('title',text=self.text('任务／条件','Quest / rule'))
        self._render_key=None;self.render()

    def render(self):
        c=self.controller
        zh,en=_STATES[c.state];message=self.text(zh,en)
        if c.error:message+='：'+translate_ui_text(c.error,self.language())
        if c.report:
            message+=self.text('；任务 {0}，关卡结算点 {1}，未关联 {2}。','; quests {0}, result sites {1}, unassociated {2}.').format(
                len(c.report.quests),len(c.report.outcomes),len(c.report.unassociated))
            s=c.report.snapshot
            if s.stamp and s.stamp[0]=='official-casc':
                message+='\n'+self.text('当前为官方安装基础脚本分析；语言／模组覆盖层尚未核对，不开放原流程执行。',
                    'Official installed base script analysis; effective locale/mod overlays remain unverified, so execution is disabled.')
            self.source.set(self.text('来源：','Source: ')+s.origin+'\n'+self.text('会话：','Session: ')+str(s.session_token)+
                ' | '+self.text('检测时间：','Detected: ')+c.detected_at+'\nJASS SHA-256: '+s.script_sha256+'\nWTS SHA-256: '+s.strings_sha256)
        else:self.source.set('')
        self.status.set(message)
        if self.panel is None:return
        self.cancel_button.configure(state='normal' if c.busy else 'disabled')
        key=(id(c.report),self.language())
        if key!=self._render_key:self._render_key=key;self.render_rows()
        self.render_completion()

    def inspect_completion(self):self.completion.inspect();self.render_completion()
    def execute_completion(self):
        if self._preview_complete:self.completion.execute()
        self.render_completion()
    def observe_completion(self):self.completion.observe();self.render_completion()

    def render_completion(self):
        if self.panel is None:return
        c=self.completion
        selected=self.tree.selection();selected=selected[0] if selected else None
        preview_key=(selected,id(c.plan),self.language(),id(c.report))
        if preview_key!=self._preview_key:
            self._preview_key=preview_key;self._preview_complete=False
            detail=self._rows.get(selected,'')
            if c.plan is not None and c.plan.quest_key==selected:
                preview,self._preview_complete=self.completion_details(c.plan)
                detail+='\n\n'+preview
            self._set_detail(detail)
        self.inspect_button.configure(state='normal' if c.can_inspect else 'disabled')
        self.execute_button.configure(state='normal' if c.can_execute and self._preview_complete else 'disabled')
        self.observe_button.configure(state='normal' if c.can_observe else 'disabled')
        message=translate_ui_text(c.message,self.language())
        if c.plan and c.plan.entry_function:
            message=self.text('原入口：','Original entry: ')+str(c.plan.entry_trigger)+' → '+c.plan.entry_function+'\n'+message
        if c.plan and not self._preview_complete:
            message+='\n'+self.text('原流程证据未完整显示，暂不开放执行。','Original-flow evidence is not fully displayed; execution is disabled.')
        if c.result:
            statuses={'rejected-before-dispatch':('派发前拒绝','Rejected before dispatch'),
                'dispatched':('原流程已派发，尚待核对','Dispatched; verification pending'),
                'observed-completed':('已读回任务完成状态','Quest completion flag observed'),
                'unknown':('先前执行结果未知，禁止自动重试','Previous outcome unknown; no automatic retry')}
            message+='\n'+self.text('上次请求：','Previous request: ')+c.result.request_id+' | '+self.text(*statuses[c.result.status])
        self.execution_status.set(message)

    def completion_details(self,plan):
        lines=[self.text('原流程预览（静态识别的效果与证据）','Original-flow preview (statically identified effects and evidence)'),
            self.text('来源：','Source: ')+plan.origin,
            self.text('完整调用链：','Full call chain: ')+' → '.join(plan.chain_functions),
            self.text('涉及的标准调用：','Recognized calls: ')+', '.join(plan.recognized_calls),
            self.text('以下是将要运行的原脚本语句，奖励和后续仍需游戏内核对：',
                'These are the original script statements to run; verify actual rewards and continuation in the game:')]
        size=sum(len(line) for line in lines);complete=True
        for n,e in enumerate(plan.evidence):
            line=f'{e.function}:{e.line} [{translate_ui_text(e.role,self.language())}] {e.source}'
            if n>=1000 or size+len(line)>200000:
                complete=False;break
            lines.append(line);size+=len(line)
        if size>200000:complete=False;lines=lines[:2]
        if not complete:lines.append(self.text('证据过长，预览已截断；暂不开放执行。',
            'Evidence exceeds the preview limit; preview truncated and execution disabled.'))
        if plan.reasons:lines.extend(translate_ui_text(reason,self.language()) for reason in plan.reasons)
        return '\n'.join(lines),complete

    def rule_details(self,rule):
        label={'created':('创建定义','Creation definition'),'completed':('设置完成','Set completed'),
            'failed':('设置失败','Set failed'),'resets':('重置为未完成／未失败','Reset to incomplete / not failed'),
            **_KINDS}.get(rule.kind,(rule.kind,rule.kind))
        lines=[self.text(*label)+' — '+rule.target]
        if not rule.paths:lines.append(self.text('此静态设置点没有可确认的可达路径。','No confirmed reachable path for this static setter.'))
        for i,p in enumerate(rule.paths,1):
            lines.append(self.text('\n路径 {0}（各路径为备选）','\nPath {0} (alternative paths)').format(i))
            lines.append(self.text('事件／入口：','Event / entry: ')+'; '.join(p.events))
            lines.append(self.text('布尔条件原文：','Boolean condition: ')+p.guard)
            if p.explanation:lines.append(self.text('条件说明：','Meaning: ')+p.explanation[0 if self.language()=='zh' else 1])
            lines.append(self.text('调用链：','Call chain: ')+' → '.join(p.callers))
            if p.issues:lines.append(self.text('解析缺口：','Coverage gaps: ')+'; '.join(translate_ui_text(x,self.language()) for x in p.issues))
            lines.append(self.text('证据（变量是静态来源，并非当前值）：','Evidence (variable definitions, not current values):'))
            for e in p.evidence:
                lines.append(f'  {e.function}:{e.line} [{translate_ui_text(e.role,self.language())}] {e.source}')
        return '\n'.join(lines)

    def quest_details(self,q):
        flag=lambda value:self.text('未知','Unknown') if value is None else str(value).lower()
        lines=[q.title,q.description,self.text('脚本标识：','Script key: ')+q.key,
            self.text('静态别名：','Static aliases: ')+', '.join(q.aliases),
            self.text('必需任务：','Required quest: ')+flag(q.required)+'; '+self.text('发现设置：','Discovery setting: ')+flag(q.discovered)]
        for kind in ('created','completed','failed','resets'):
            rules=getattr(q,kind)
            for rule in rules:lines.extend(('',self.rule_details(rule)))
        if not q.completed:lines.append(self.text('\n未识别到此任务的明确完成设置点。','\nNo explicit completion setter identified for this definition.'))
        if not q.failed:lines.append(self.text('未识别到此任务的明确失败设置点；关卡直接判负另列。','No explicit quest failure setter identified; direct game defeat is listed separately.'))
        for item in q.items:
            lines.extend(('',self.text('任务条目：','Quest item: ')+item.description+' ['+item.key+']'))
            for rule in item.completed+item.resets:lines.append(self.rule_details(rule))
        return '\n'.join(lines)

    def coverage_details(self,r):
        lines=[self.text('覆盖范围：当前 JASS 的静态任务定义、状态设置与关卡结算。','Scope: static JASS quest definitions, setters and game result calls.'),
            self.text('函数数：','Functions: ')+str(r.functions)]
        issues=list(r.issues)
        rules=list(r.outcomes)+list(r.unassociated)
        for q in r.quests:
            rules.extend(q.created+q.completed+q.failed+q.resets)
            for item in q.items:rules.extend(item.completed+item.resets)
        for rule in rules:
            for p in rule.paths:
                for issue in p.issues:
                    value=f'{rule.evidence.function}:{rule.evidence.line} — '+issue
                    if value not in issues:issues.append(value)
        lines.extend(translate_ui_text(i,self.language()) for i in issues)
        if not issues:lines.append(self.text('在当前支持的分析范围内未发现缺口；这不是运行时任务进度。','No gaps found within the supported analysis domain; this is not live quest progress.'))
        lines.extend(('',self.text('来源校验：','Source proof: '),*r.snapshot.provenance))
        return '\n'.join(lines)

    def render_rows(self):
        if self.panel is None:return
        selection=self.tree.selection();old=selection[0] if selection else None
        self.tree.delete(*self.tree.get_children());self._rows={}
        r=self.controller.report
        if r is None:
            self.completion.select(None,None);self._set_detail('');return
        rows=[]
        for q in r.quests:rows.append((q.key,'quest',q.title,self.quest_details(q)))
        for i,rule in enumerate(r.outcomes):rows.append((f'outcome:{i}',rule.kind,rule.target,self.rule_details(rule)))
        for i,rule in enumerate(r.unassociated):rows.append((f'unassociated:{i}','unassociated',rule.target,self.rule_details(rule)))
        rows.append(('coverage','coverage',self.text('解析缺口与来源证据','Coverage gaps and source proof'),self.coverage_details(r)))
        search=self.search.get().casefold().strip()
        for key,kind,title,detail in rows:
            if search and search not in (title+' '+detail).casefold():continue
            self._rows[key]=detail;self.tree.insert('', 'end',iid=key,values=(self.text(*_KINDS[kind]),title))
        children=self.tree.get_children()
        if children:self.tree.selection_set(old if old in children else children[0]);self.show_selected()
        else:
            self.completion.select(None,None);self.render_completion()
            self._set_detail(self.text('没有匹配结果。','No matching results.'))

    def _set_detail(self,value):
        self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',value);self.detail.configure(state='disabled')

    def show_selected(self):
        selected=self.tree.selection()
        self._preview_key=None
        self._set_detail(self._rows.get(selected[0],'') if selected else '')
        self.completion.select(self.controller.report,selected[0] if selected else None)
        self.render_completion()
