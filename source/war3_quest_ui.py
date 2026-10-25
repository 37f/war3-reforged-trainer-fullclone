"""R22 read-only quest page. Background workers never access Tk objects."""
from __future__ import annotations

from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from war3_quest_analysis import analyze_quests
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
    def __init__(self,root,language,source_client_provider):
        self.root,self.language=root,language
        self.controller=QuestAnalysisController(source_client_provider)
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
            '只读脚本静态分析；列出尚未执行的任务定义。没有读取任务当前进度；解析缺口会明确列出。',
            'Read-only static script analysis, including definitions not yet executed. Current quest progress is not read; coverage gaps are listed.')
        self.notice.pack(fill='x',pady=(0,5))
        ttk.Label(tab,textvariable=self.status,wraplength=1120).pack(fill='x',pady=(0,5))
        ttk.Label(tab,textvariable=self.source,wraplength=1120).pack(fill='x',pady=(0,8))
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
        self._closed=True;self.controller.close()
        if self._after is not None:
            try:self.root.after_cancel(self._after)
            except tk.TclError:pass
        self._after=None

    def _poll(self):
        if self._closed:return
        visible=bool(self.panel is not None and self.panel.winfo_ismapped())
        self.controller.tick(visible);self.render()
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
            self.source.set(self.text('来源：','Source: ')+s.origin+'\n'+self.text('会话：','Session: ')+str(s.session_token)+
                ' | '+self.text('检测时间：','Detected: ')+c.detected_at+'\nJASS SHA-256: '+s.script_sha256+'\nWTS SHA-256: '+s.strings_sha256)
        else:self.source.set('')
        self.status.set(message)
        if self.panel is None:return
        self.cancel_button.configure(state='normal' if c.busy else 'disabled')
        key=(id(c.report),self.language())
        if key!=self._render_key:self._render_key=key;self.render_rows()

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
        if r is None:self._set_detail('');return
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
        else:self._set_detail(self.text('没有匹配结果。','No matching results.'))

    def _set_detail(self,value):
        self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',value);self.detail.configure(state='disabled')

    def show_selected(self):
        selected=self.tree.selection()
        self._set_detail(self._rows.get(selected[0],'') if selected else '')
