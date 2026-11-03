"""R25 read-only task information and live state. Workers never access Tk objects."""
from __future__ import annotations

from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from dataclasses import replace

from war3_quest_analysis import analyze_quests
from war3_quest_text import QuestText,quest_kind,clean_text
from war3_ui_i18n import translate_ui_text
from war3_quest_status import QuestState,status_plan
from war3_quest_locations import QuestLocations

VALIDATION_SECONDS=2.


class QuestAnalysisController:
    def __init__(self,source_client_provider,analyzer=analyze_quests,clock=time.monotonic,status_provider=None,locations_factory=None):
        self.provider=source_client_provider;self.analyzer=analyzer;self.clock=clock
        self.replies=queue.Queue();self.report=None;self.state='idle';self.error=''
        self.checked_at=0.;self.detected_at='';self.generation=0;self.busy=False
        self._visible=False;self._closed=False;self._auto=True;self._next_poll=0.
        self._stop=threading.Event();self._job=0;self._identity=None
        self.status_provider=status_provider;self.live_states={};self.live_error='';self.live_revision=0
        self._status_plan=None
        self.locations_factory=locations_factory;self.location_data=None;self.location_revision=0

    def _clear_live(self):
        self.live_states={};self.live_error='';self._status_plan=None;self.live_revision+=1
        self.location_data=None;self.location_revision+=1

    def invalidate(self,reason=''):
        self._stop.set();self.generation+=1;self.report=None;self.checked_at=0.
        self.error=reason;self.state='changed' if reason else 'idle';self._next_poll=0.;self._identity=None
        self._clear_live()

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
            self._clear_live()
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
        self._identity=client.identity();identity=self._identity;report=self.report;plan=self._status_plan
        snapshot=report.snapshot if report else None
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
                    try:locations=self.locations_factory(value,stop.is_set) if self.locations_factory else None
                    except (ValueError,RuntimeError,UnicodeError):locations=None
                    if stop.is_set():return
                    valid=client.check(source)
                else:
                    value=None;valid=client.check(snapshot)
                # R25: query live flags only after source qualification. A getter
                # error preserves the static report and marks its state unknown.
                states={};live_error='';live_plan=plan
                if valid and self.status_provider is not None:
                    current=value if operation=='read' else report
                    try:
                        if live_plan is None:live_plan=status_plan(current,stop.is_set)
                        states=self.status_provider(current,live_plan,stop.is_set)
                    except Exception as exc:live_error=str(exc)
                    if stop.is_set():return
                    valid=client.check(current.snapshot)
                # This is the actual worker validation time, never the Tk dequeue time.
                checked=self.clock()
                self.replies.put((job,generation,'result' if operation=='read' else 'checked',
                    value,'' if valid else '地图会话或来源已变化',checked,identity))
                if valid and operation=='read' and self.locations_factory:
                    self.replies.put((job,generation,'locations',locations,'',checked,identity))
                if valid and self.status_provider is not None:
                    self.replies.put((job,generation,'live',(states,live_plan),live_error,checked,identity))
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
            if phase=='locations':
                if self.report is not None and self._identity_now()==identity and self.clock()-checked<=VALIDATION_SECONDS:
                    self.location_data=value;self.location_revision+=1
                continue
            if phase=='live':
                if self.report is not None and self._identity_now()==identity and self.clock()-checked<=VALIDATION_SECONDS:
                    self.live_states,self._status_plan=value;self.live_error=error;self.live_revision+=1
                continue
            if error:
                self.report=None;self.checked_at=0.;self.error=error
                self._clear_live()
                self.state='changed' if phase!='error' else 'unavailable'
                self._next_poll=self.clock()+(3 if phase=='error' else 0);continue
            if self._identity_now()!=identity:
                self.invalidate('游戏连接已变化');continue
            if self.clock()-checked>VALIDATION_SECONDS:
                self.report=None;self.state='changed';self.error='会话验证已过期，正在重新检索'
                self._clear_live()
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
_KINDS={'main':('主线任务','Main quest'),'side':('支线任务','Side quest'),'unknown':('类型未确认','Unconfirmed type'),'coverage':('覆盖情况','Coverage'),
    'victory':('整关胜利条件','Map victory'),'defeat':('整关失败条件','Map defeat'),
    'unknown-result':('未确认结算','Unresolved result'),'unassociated':('未关联条件','Unassociated rule')}
_LIVE_STATES={'active':('进行中','In progress'),'completed':('已完成','Completed'),
    'failed':('已失败','Failed'),'unconfirmed':('状态未确认','Unconfirmed')}


class QuestAnalysisUI:
    def __init__(self,root,language,source_client_provider,status_provider=None,location_navigator=None):
        self.root,self.language=root,language
        self.controller=QuestAnalysisController(source_client_provider,status_provider=status_provider,locations_factory=QuestLocations)
        self.location_navigator=location_navigator;self._navigation=queue.Queue();self._nav_busy=False
        self._row_locations={};self.location_status=tk.StringVar(root,'')
        self.evidence=tk.BooleanVar(root,False);self._reader_key=None;self._reader=None
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
        self._label(ttk.Checkbutton(toolbar,variable=self.evidence,command=self.render_rows),'查看脚本依据','Show script evidence').pack(side='left',padx=8)
        self.notice=self._label(ttk.Label(tab,wraplength=1120),
            '只读任务信息：解释主线／支线的目标、完成与失败条件；本页打开时每秒同步任务状态，无法唯一匹配时显示“状态未确认”。',
            'Read-only main/side quest rules. Refreshes live state every second while visible; ambiguous matches remain Unconfirmed.')
        self.notice.pack(fill='x',pady=(0,5))
        ttk.Label(tab,textvariable=self.status,wraplength=1120).pack(fill='x',pady=(0,5))
        ttk.Label(tab,textvariable=self.source,wraplength=1120).pack(fill='x',pady=(0,8))
        ttk.Label(tab,textvariable=self.location_status,wraplength=1120).pack(fill='x',pady=(0,5))
        panes=ttk.Panedwindow(tab,orient='horizontal');panes.pack(fill='both',expand=True)
        left=ttk.Frame(panes);right=ttk.Frame(panes);panes.add(left,weight=1);panes.add(right,weight=3)
        self.tree=ttk.Treeview(left,columns=('kind','title','live'),show='tree headings',height=18,selectmode='browse')
        self.tree.column('#0',width=26,stretch=False)
        self.tree.column('kind',width=110,stretch=False);self.tree.column('title',width=240)
        self.tree.column('live',width=100,stretch=False)
        self.tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview);scroll.grid(row=0,column=1,sticky='ns')
        self.tree.configure(yscrollcommand=scroll.set);left.rowconfigure(0,weight=1);left.columnconfigure(0,weight=1)
        self.detail=tk.Text(right,wrap='word',state='disabled',width=75,height=22)
        self.detail.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(right,orient='vertical',command=self.detail.yview);scroll.grid(row=0,column=1,sticky='ns')
        self.detail.configure(yscrollcommand=scroll.set);right.rowconfigure(0,weight=1);right.columnconfigure(0,weight=1)
        self.tree.bind('<<TreeviewSelect>>',lambda _event:self.show_selected())
        self.tree.bind('<ButtonRelease-1>',self._click_row)
        self.tree.bind('<Return>',lambda _event:self._jump_row())
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
        while True:
            try:generation,report,error=self._navigation.get_nowait()
            except queue.Empty:break
            self._nav_busy=False
            if visible and generation==self.controller.generation and report is self.controller.report:
                self.location_status.set(error or self.text('视角已定位。','Camera positioned.'))
        self._after=self.root.after(80,self._poll)

    def refresh_language(self):
        for widget,zh,en in self._labels:widget.configure(text=self.text(zh,en))
        if self.panel is not None:
            self.tree.heading('kind',text=self.text('类别','Type'));self.tree.heading('title',text=self.text('任务／条件','Quest / rule'))
            self.tree.heading('live',text=self.text('当前状态','Current state'))
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
                message+='\n'+self.text('官方安装基础脚本：语言／模组覆盖层尚未核对，可能与实际显示文本不同。',
                    'Official installed base script; unverified locale/mod overlays may change displayed text.')
            self.source.set(self.text('来源：','Source: ')+s.origin+'\n'+self.text('会话：','Session: ')+str(s.session_token)+
                ' | '+self.text('检测时间：','Detected: ')+c.detected_at+'\nJASS SHA-256: '+s.script_sha256+'\nWTS SHA-256: '+s.strings_sha256)
        else:self.source.set('')
        self.status.set(message)
        if self.panel is None:return
        self.cancel_button.configure(state='normal' if c.busy else 'disabled')
        key=(id(c.report),self.language(),c.live_revision,c.location_revision)
        if key!=self._render_key:self._render_key=key;self.render_rows()
    def rule_evidence(self,rule):
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

    def quest_evidence(self,q):
        flag=lambda value:self.text('未知','Unknown') if value is None else str(value).lower()
        lines=[q.title,q.description,self.text('脚本标识：','Script key: ')+q.key,
            self.text('静态别名：','Static aliases: ')+', '.join(q.aliases),
            self.text('必需任务：','Required quest: ')+flag(q.required)+'; '+self.text('发现设置：','Discovery setting: ')+flag(q.discovered)]
        for kind in ('created','completed','failed','resets'):
            rules=getattr(q,kind)
            for rule in rules:lines.extend(('',self.rule_evidence(rule)))
        if not q.completed:lines.append(self.text('\n未识别到此任务的明确完成设置点。','\nNo explicit completion setter identified for this definition.'))
        if not q.failed:lines.append(self.text('未识别到此任务的明确失败设置点；关卡直接判负另列。','No explicit quest failure setter identified; direct game defeat is listed separately.'))
        for item in q.items:
            lines.extend(('',self.text('任务条目：','Quest item: ')+item.description+' ['+item.key+']'))
            for rule in item.completed+item.resets:lines.append(self.rule_evidence(rule))
        return '\n'.join(lines)

    def reader(self):
        report=self.controller.report;locations=getattr(self.controller,'location_data',None);key=(id(report),self.language(),id(locations))
        if getattr(self,'_reader_key',None)!=key:
            self._reader_key=key;self._reader=QuestText(report,self.language()=='en',locations)
        return self._reader

    def quest_details(self,q):
        state=self.quest_state(q.key)
        text=self.text('当前状态：','Current state: ')+self.text(*_LIVE_STATES[state.state])
        if state.read_at:text+='\n'+self.text('最近读取：','Last read: ')+datetime.fromtimestamp(state.read_at).strftime('%Y-%m-%d %H:%M:%S')
        if state.reason:text+='\n'+translate_ui_text(state.reason,self.language())
        text+='\n\n'+self.reader().quest(q)
        if getattr(self,'evidence',None) is not None and self.evidence.get():
            text+='\n\n'+self.text('脚本依据（供核对）','Script evidence')+'\n'+self.quest_evidence(q)
        return text

    def quest_state(self,key):
        c=self.controller
        if c.live_error:return QuestState(reason=c.live_error)
        return c.live_states.get(key,QuestState())

    def rule_details(self,rule):
        reader=self.reader();lines=[]
        if rule.kind in ('victory','defeat'):
            try:target=reader.expr(reader.parse(rule.target))
            except ValueError:target=self.text('尚未确认的玩家','unconfirmed player')
            lines.append(self.text('影响对象：','Affected player: ')+target)
            lines.append(self.text('这是整关结算规则，不等同于某一个任务单独完成或失败。','This ends the map for the player; it is separate from an individual quest state.'))
        text='\n'.join(lines+reader.rule(rule))
        if self.evidence.get():text+='\n\n'+self.rule_evidence(rule)
        return text

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
        tree_scroll=self.tree.yview();detail_scroll=self.detail.yview()
        expanded={i for i in self._rows if self.tree.exists(i) and self.tree.item(i,'open')}
        self.tree.delete(*self.tree.get_children());self._rows={};self._row_locations={}
        r=self.controller.report
        if r is None:
            self.location_status.set('');self._set_detail('');return
        rows=[]
        for q in sorted(r.quests,key=lambda q:0 if q.required is True else 1 if q.required is False else 2):
            kind='main' if q.required is True else 'side' if q.required is False else 'unknown'
            rows.append((q.key,kind,clean_text(q.title),self.quest_details(q)))
        for i,rule in enumerate(r.outcomes):
            try:title=self.reader().expr(self.reader().parse(rule.target))
            except ValueError:title=self.text('影响对象未确认','Unconfirmed player')
            rows.append((f'outcome:{i}',rule.kind,title,self.rule_details(rule)))
        for i,rule in enumerate(r.unassociated):rows.append((f'unassociated:{i}','unassociated',rule.target,self.rule_details(rule)))
        rows.append(('coverage','coverage',self.text('解析缺口与来源证据','Coverage gaps and source proof'),self.coverage_details(r)))
        search=self.search.get().casefold().strip()
        quest_keys={q.key for q in r.quests}
        quests={q.key:q for q in r.quests};locations=self.controller.location_data
        for key,kind,title,detail in rows:
            if search and search not in (title+' '+detail).casefold():continue
            live=self.text(*_LIVE_STATES[self.quest_state(key).state]) if key in quest_keys else ''
            self._rows[key]=detail;self.tree.insert('', 'end',iid=key,values=(self.text(*_KINDS[kind]),title,live))
            if key in quests:
                q=quests[key];all_places=[]
                rules=[(key,self.text('完成条件','Completion'),rule) for rule in q.completed]
                rules += [(key,self.text('失败条件','Failure'),rule) for rule in q.failed]
                for item_index,item in enumerate(q.items):
                    item_key=f'{key}:objective:{item_index}'
                    places=tuple(dict.fromkeys(p for rule in item.completed for p in locations.rule(rule))) if locations else ()
                    self.tree.insert(key,'end',iid=item_key,values=(self.text('子目标','Objective'),clean_text(item.description),''))
                    detail=clean_text(item.description)+'\n'+('\n'.join(p.describe(self.language()=='en') for p in places)
                        if places else self.text('关联地点：无位置','Locations: No location'))
                    self._rows[item_key]=detail;self._row_locations[item_key]=places
                    rules += [(item_key,self.text('完成条件','Completion'),rule) for rule in item.completed]
                for index,(parent,label,rule) in enumerate(rules):
                    for path_index,p in enumerate(rule.paths or (None,)):
                        shown=replace(rule,paths=(p,)) if p is not None else rule
                        places=locations.paths(shown.paths) if locations else ()
                        child=f'{key}:condition:{index}:{path_index}'
                        summary=self.reader().event(p.events[0]) if p is not None and p.events else self.text('条件详情','Condition details')
                        self.tree.insert(parent,'end',iid=child,values=(label,summary,''))
                        self._rows[child]='\n'.join(self.reader().rule(shown));self._row_locations[child]=places
                        if not places and '无位置' not in self._rows[child]:self._rows[child]+='\n'+self.text('关联地点：无位置','Locations: No location')
                        for j,place in enumerate(places):
                            leaf=f'{child}:place:{j}';description=place.describe(self.language()=='en')
                            self.tree.insert(child,'end',iid=leaf,values=(self.text('位置','Location'),description,''))
                            self._rows[leaf]=description;self._row_locations[leaf]=(place,)
                        all_places.extend(places)
                self._row_locations[key]=tuple(dict.fromkeys(all_places))
            elif locations:
                rule=r.outcomes[int(key.split(':')[1])] if key.startswith('outcome:') else r.unassociated[int(key.split(':')[1])] if key.startswith('unassociated:') else None
                if rule is not None:self._row_locations[key]=locations.rule(rule)
        for key in expanded:
            if self.tree.exists(key):self.tree.item(key,open=True)
        children=self.tree.get_children()
        if children:
            keep=old is not None and self.tree.exists(old)
            self.tree.selection_set(old if keep else children[0]);self.show_selected()
            if keep:
                if tree_scroll:self.tree.yview_moveto(tree_scroll[0])
                if detail_scroll:self.detail.yview_moveto(detail_scroll[0])
        else:
            self._set_detail(self.text('没有匹配结果。','No matching results.'))

    def _set_detail(self,value):
        self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',value);self.detail.configure(state='disabled')
        self.detail.tag_configure('no-location',foreground='#888888')
        offset=self.detail.search(self.text('无位置','No location'),'1.0',stopindex='end')
        if offset:self.detail.tag_add('no-location',offset,f'{offset}+{len(self.text("无位置","No location"))}c')

    def show_selected(self):
        selected=self.tree.selection()
        self._set_detail(self._rows.get(selected[0],'') if selected else '')
        places=self._row_locations.get(selected[0],()) if selected else ()
        for n,place in enumerate(places):
            text=place.describe(self.language()=='en');tag=f'location:{n}'
            start='1.0'
            while True:
                at=self.detail.search(text,start,stopindex='end')
                if not at:break
                self.detail.tag_add(tag,at,f'{at}+{len(text)}c');start=f'{at}+{len(text)}c'
            self.detail.tag_configure(tag,foreground='#1669b2' if self.location_navigator else '#888888',underline=bool(self.location_navigator))
            if self.location_navigator:self.detail.tag_bind(tag,'<Button-1>',lambda _event,p=place:self.jump_to(p))

    def _click_row(self,event):
        row=self.tree.identify_row(event.y)
        if row and self.tree.identify_region(event.x,event.y) in ('tree','cell') and 'indicator' not in self.tree.identify_element(event.x,event.y):
            self._jump_row()

    def _jump_row(self):
        selected=self.tree.selection();places=self._row_locations.get(selected[0],()) if selected else ()
        if len(places)==1:self.jump_to(places[0])
        elif places:self.location_status.set(self.text('该条件关联多个地点，请点击具体位置行或详情中的蓝色地点。','Multiple locations: click a location row or a blue location in the details.'))
        else:self.location_status.set(self.text('无位置','No location'))

    def jump_to(self,place):
        c=self.controller;report=c.report
        if report is None or c.clock()-c.checked_at>VALIDATION_SECONDS:
            self.location_status.set(self.text('地图信息已变化，请等待重新检索。','Map information changed; wait for a fresh scan.'));return
        if self.location_navigator is None:
            self.location_status.set(self.text('位置已显示；相机定位尚未启用。','Location displayed; camera navigation is unavailable.'));return
        if self._nav_busy:return
        self._nav_busy=True;generation=c.generation
        self.location_status.set(self.text('正在定位视角…','Positioning camera…'))
        failure_prefix=self.text('定位未完成：','Could not position camera: ')
        def work():
            error=''
            try:
                if generation==c.generation and report is c.report:self.location_navigator(report,place)
            except Exception as exc:error=failure_prefix+str(exc)
            self._navigation.put((generation,report,error))
        threading.Thread(target=work,name='war3-quest-camera',daemon=True).start()
