"""Shared file/current-map catalogs; workers never access Tk widgets."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from war3_campaign_catalog import CampaignInfo, CatalogResult, list_campaign, detect_campaign


@dataclass
class CatalogSelection:
    generation: int = 0
    info: CampaignInfo | None = None
    chapter_index: int = -1
    result: CatalogResult | None = None

    def reset(self):
        self.generation += 1
        self.info=None; self.chapter_index=-1; self.result=None
        return self.generation

    def accept_info(self, token, info):
        if token != self.generation: return False
        self.info=info; self.chapter_index=-1; self.result=None
        return True

    def select_chapter(self, index):
        if self.info is None or not 0 <= index < len(self.info.chapters):
            raise ValueError('请选择有效章节')
        self.generation += 1
        self.chapter_index=index; self.result=None
        return self.generation

    def accept_result(self, token, result):
        if token != self.generation: return False
        self.result=result
        return True


class CampaignCatalogUI:
    def __init__(self, root, on_change, language, runtime_client=None):
        self.root,self.on_change,self.language=root,on_change,language
        self.selection=CatalogSelection()
        self.modes={kind:tk.StringVar(root,'general') for kind in ('item','unit','ability')}
        self.path_label=tk.StringVar(root,'')
        self.chapter_label=tk.StringVar(root,'')
        self.status=tk.StringVar(root,'')
        self._labels=[]; self._combos=[]; self._file_buttons=[]; self._detect_buttons=[]
        self._queue=queue.Queue(); self._busy=False; self._operation=''; self._error=''
        # R21 keeps runtime generations separate from the user's file selection.
        self._runtime_provider=runtime_client; self.runtime_snapshot=None
        self._runtime_generation=0; self._runtime_cancel=threading.Event()
        self._runtime_error=''; self._runtime_checked_at=0.; self._last_runtime_poll=0.
        self._panels={}; self._runtime_buttons=[]
        root.after(80,self._poll)
        self.update_display()

    def text(self, zh, en):
        return zh if self.language()=='zh' else en

    def _label(self, widget, zh, en):
        self._labels.append((widget,zh,en)); widget.configure(text=self.text(zh,en))
        return widget

    def add_controls(self, tab, kind):
        panel=ttk.Frame(tab); panel.grid(row=0,column=0,sticky='ew',pady=(0,8))
        self._panels[kind]=panel
        for column,(value,zh,en) in enumerate((('general','通用目录','General catalog'),('custom','战役与所选章节','Campaign and selected chapter'),('runtime','当前地图','Current map'))):
            self._label(ttk.Radiobutton(panel,variable=self.modes[kind],value=value,
                command=lambda k=kind:self._source_changed(k)),zh,en).grid(row=0,column=column,sticky='w',padx=(0,10))
        button=self._label(ttk.Button(panel,command=self.choose_file),'选择战役','Choose campaign')
        button.grid(row=1,column=0,sticky='w',pady=(5,0)); self._file_buttons.append(button)
        ttk.Label(panel,textvariable=self.path_label).grid(row=1,column=1,columnspan=3,sticky='w',padx=(6,0))
        self._label(ttk.Label(panel),'所选章节','Selected chapter').grid(row=2,column=0,sticky='w',pady=(5,0))
        combo=ttk.Combobox(panel,textvariable=self.chapter_label,state='disabled',width=65)
        combo.grid(row=2,column=1,sticky='ew',padx=(6,6),pady=(5,0))
        combo.bind('<<ComboboxSelected>>',lambda _event,control=combo:self.choose_chapter(control.current()))
        self._combos.append(combo)
        button=self._label(ttk.Button(panel,command=self.detect),'检测自定义对象','Detect custom objects')
        button.grid(row=2,column=2,pady=(5,0)); self._detect_buttons.append(button)
        self._label(ttk.Button(panel,command=self.show_details),'读取详情','Read details').grid(row=2,column=3,padx=(6,0),pady=(5,0))
        runtime=self._label(ttk.Button(panel,command=self.detect_runtime),'读取当前地图 ID','Read current map IDs')
        runtime.grid(row=3,column=0,columnspan=2,sticky='w',pady=(5,0));self._runtime_buttons.append(runtime)
        ttk.Label(panel,textvariable=self.status,wraplength=1050).grid(row=4,column=0,columnspan=4,sticky='w',pady=(5,0))
        panel.columnconfigure(1,weight=1)
        self.update_display()

    def choose_file(self):
        if self._busy: return
        path=filedialog.askopenfilename(parent=self.root,title=self.text('选择战役文件','Choose campaign file'),
            filetypes=[('Warcraft III campaign','*.w3n')])
        if not path: return
        self.selection.reset(); self._error=''; self.path_label.set(path)
        self._launch('list',lambda:list_campaign(Path(path)))
        self.on_change()

    def choose_chapter(self,index):
        self.selection.select_chapter(index); self._error=''
        self.update_display(); self.on_change()

    def detect(self):
        state=self.selection
        if self._busy or state.info is None or state.chapter_index<0: return
        info,chapter=state.info,state.info.chapters[state.chapter_index]
        state.result=None; self._error=''
        self._launch('detect',lambda:detect_campaign(info,chapter))
        self.on_change()

    def _launch(self,operation,fn):
        token=self.selection.generation
        self._busy=True; self._operation=operation
        self.update_display()
        def work():
            try: payload,error=fn(),''
            except Exception as exc: payload,error=None,str(exc)
            self._queue.put((token,operation,payload,error))
        threading.Thread(target=work,name='war3-offline-catalog',daemon=True).start()

    def _poll(self):
        try:
            while True:
                token,operation,payload,error=self._queue.get_nowait()
                self._busy=False
                if operation.startswith('runtime'):
                    if token==self._runtime_generation:
                        if error:
                            self.invalidate_runtime(error)
                        else:
                            payload,validated_at=payload
                            if operation=='runtime-check':
                                if payload: self._runtime_checked_at=validated_at
                                else: self.invalidate_runtime(self.text('地图会话或游戏连接已变化，请重新检测','Map session or connection changed; read again'))
                            else:
                                client=self._get_runtime_client()
                                if client is not None and client.identity()==payload.identity:
                                    self.runtime_snapshot=payload;self._runtime_checked_at=validated_at
                                else: self.invalidate_runtime(self.text('游戏连接已变化','Game connection changed'))
                elif token==self.selection.generation:
                    self._error=error
                    if not error:
                        if operation=='list': self.selection.accept_info(token,payload)
                        else: self.selection.accept_result(token,payload)
                self.update_display(); self.on_change()
        except queue.Empty:
            pass
        if self.runtime_snapshot is not None:
            # A delayed Tk tick is not evidence of a changed map. Keep the
            # labelled snapshot, disable copy while stale, then revalidate.
            if (not self._busy and time.monotonic()-self._last_runtime_poll>=1 and
                  any(self.modes[k].get()=='runtime' and p.winfo_ismapped() for k,p in self._panels.items())):
                self.check_runtime()
        self.root.after(80,self._poll)

    def _get_runtime_client(self):
        provider=self._runtime_provider
        return provider if provider is None or hasattr(provider,'read') else provider()

    def set_runtime_client(self,provider):
        self._runtime_provider=provider;self.invalidate_runtime('')

    def _source_changed(self,kind):
        mode=self.modes[kind].get()
        if mode=='runtime' or any(v.get()=='runtime' for v in self.modes.values()):
            # A current-map read is shared across all three pages.
            for variable in self.modes.values(): variable.set(mode)
        self.selection.result=None
        self.invalidate_runtime('')

    def invalidate_runtime(self,reason):
        self._runtime_cancel.set();self._runtime_generation+=1
        self.runtime_snapshot=None;self._runtime_checked_at=0.;self._runtime_error=reason
        self.update_display();self.on_change()

    def detect_runtime(self):
        if self._busy: return
        self.invalidate_runtime('')
        client=self._get_runtime_client()
        if client is None:
            self._runtime_error=self.text('请先连接游戏','Please connect to the game first')
            self.update_display();return
        self._runtime_cancel=threading.Event()
        stop=self._runtime_cancel
        self._launch_runtime('runtime-read',lambda:client.read(stop.is_set))

    def check_runtime(self):
        if self._busy or self.runtime_snapshot is None: return
        snapshot=self.runtime_snapshot;client=self._get_runtime_client()
        self._last_runtime_poll=time.monotonic()
        self._launch_runtime('runtime-check',lambda:client is not None and client.check(snapshot))

    def _launch_runtime(self,operation,fn):
        token=self._runtime_generation;self._busy=True;self._operation=operation;self.update_display()
        def work():
            try:
                value=fn()
                # Carry worker validation time; dequeuing must never renew it.
                checked_at=value.validated_at if operation=='runtime-read' else time.monotonic()
                payload,error=(value,checked_at),''
            except Exception as exc: payload,error=None,str(exc)
            self._queue.put((token,operation,payload,error))
        threading.Thread(target=work,name='war3-current-map-catalog',daemon=True).start()

    def update_display(self):
        state=self.selection
        values=[] if state.info is None else [f'{i+1}. {x.title} [{x.path}]' for i,x in enumerate(state.info.chapters)]
        self.chapter_label.set(values[state.chapter_index] if state.chapter_index>=0 and values else '')
        for combo in self._combos: combo.configure(values=values,state='readonly' if values else 'disabled')
        for button in self._file_buttons: button.configure(state='disabled' if self._busy else 'normal')
        for button in self._detect_buttons: button.configure(state='normal' if values and state.chapter_index>=0 and not self._busy else 'disabled')
        runtime=any(v.get()=='runtime' for v in self.modes.values())
        for button in self._runtime_buttons:
            button.configure(state='disabled' if self._busy else 'normal')
            if runtime: button.grid()
            else: button.grid_remove()
        if runtime:
            for control in self._file_buttons+self._detect_buttons+self._combos: control.configure(state='disabled')
            if self._busy and self._operation=='runtime-read':
                text=self.text('正在只读检测当前地图…','Reading current map (read only)…')
            elif self._runtime_error: text=self._runtime_error
            elif self.runtime_snapshot is not None:
                snapshot=self.runtime_snapshot;result=snapshot.result
                text=self.text('部分读取' if result.partial else '完整读取','Partial read' if result.partial else 'Read complete')
                text+=self.text('：物品 {0}，技能 {1}，单位 {2}；检测时快照 {3}。',' — Items {0}, abilities {1}, units {2}; snapshot at {3}.').format(
                    *(len(result.entries.get(k,())) for k in ('item','ability','unit')),datetime.fromtimestamp(snapshot.timestamp).strftime('%H:%M:%S'))
                if time.monotonic()-self._runtime_checked_at>2:
                    text+=self.text(' 等待会话复核，暂不可复制。',' Waiting for session validation; copy is disabled.')
            else: text=self.text('尚未检测当前地图，请连接游戏并读取。','Connect to the game and read current map IDs.')
            self.status.set(text);return
        if self._busy:
            text=self.text('正在只读列出章节…' if self._operation=='list' else '正在只读检测所选章节…',
                'Listing chapters (read only)…' if self._operation=='list' else 'Detecting selected chapter (read only)…')
        elif self._error:
            text=self.text('检测失败：','Detection failed: ')+self._error
        elif state.result is not None:
            result=state.result
            text=self.text('部分读取' if result.partial else '完整读取','Partial read' if result.partial else 'Read complete')
            text+=self.text('：物品 {0}，技能 {1}，单位 {2}（定义数）；问题 {3}。',' — Items {0}, abilities {1}, units {2} (definitions); issues {3}.').format(
                *(len(result.entries.get(k,())) for k in ('item','ability','unit')),len(result.issues))
        elif state.info is None:
            text=self.text('未选择战役。此模块无需连接游戏。','Choose a campaign; no game connection is required.')
        else:
            text=self.text('请选择正在玩的章节并点击检测；这里不会自动识别游戏当前章节。','Select the chapter you are playing and click Detect; the running chapter is not identified automatically.')
            if state.info.issues: text+=self.text(' 章节清单有读取提示，详见读取详情。',' Chapter-list warnings: see Read details.')
        self.status.set(text)

    def refresh_language(self):
        for widget,zh,en in self._labels: widget.configure(text=self.text(zh,en))
        self.update_display()

    def details(self):
        if any(v.get()=='runtime' for v in self.modes.values()):
            if self.runtime_snapshot is None: return self.status.get()
            value=self.runtime_snapshot
            return '\n'.join((self.status.get(),f'Session: {value.token:016x}',f'Read: {value.elapsed_ms:.2f} ms',*value.result.statuses,*value.result.issues))
        state=self.selection
        lines=[str(state.info.path)] if state.info else []
        if state.info and state.chapter_index>=0:
            chapter=state.info.chapters[state.chapter_index]
            lines.extend((chapter.title,chapter.path,f'SHA-256: {state.info.sha256}'))
        if state.result: lines.extend(state.result.statuses+state.result.issues)
        elif state.info: lines.extend(state.info.issues)
        if self._error: lines.append(self._error)
        return '\n'.join(lines) or self.status.get()

    def show_details(self):
        window=tk.Toplevel(self.root); window.title(self.text('只读检测详情','Read-only detection details'))
        text=tk.Text(window,width=100,height=25,wrap='word'); text.pack(fill='both',expand=True)
        text.insert('1.0',self.details()); text.configure(state='disabled')

    def is_custom(self,kind):
        return self.modes[kind].get() in ('custom','runtime')

    def _result(self,kind):
        return (self.runtime_snapshot.result if self.runtime_snapshot is not None else None) if self.modes[kind].get()=='runtime' else self.selection.result

    def rows(self,kind,query):
        result=self._result(kind)
        if result is None: return []
        query=query.strip().casefold()
        return [row for row in result.entries.get(kind,()) if query in ' '.join((row.rawcode,row.name,row.base_id,row.object_type,row.source,row.note)).casefold()]

    def can_copy(self,rawcode,kind):
        if self.modes[kind].get()=='runtime':
            client=self._get_runtime_client()
            if (self.runtime_snapshot is None or client is None or
                client.identity()!=self.runtime_snapshot.identity or time.monotonic()-self._runtime_checked_at>2): return False
        result=self._result(kind)
        return result is not None and any(row.rawcode==rawcode and row.copyable for row in result.entries.get(kind,()))

    def render_custom(self,tree,kind,query):
        if not self.is_custom(kind): return False
        columns=('rawcode','name','base_id','object_type','source','note')
        tree.configure(columns=columns)
        for key,zh,en,width in zip(columns,('ID','名称','基础 ID','对象类型','数据来源','备注'),
                ('ID','Name','Base ID','Object type','Source','Notes'),(115,230,90,90,170,240)):
            tree.heading(key,text=self.text(zh,en)); tree.column(key,width=width,minwidth=60,stretch=True,anchor='w')
        tree.delete(*tree.get_children())
        for row in self.rows(kind,query):
            object_type=row.object_type if self.language()=='zh' else {'新增':'New','原版改动':'Modified vanilla'}.get(row.object_type,row.object_type)
            source=row.source if self.language()=='zh' else row.source.replace('战役公共','Campaign').replace('所选章节','Selected chapter').replace('当前地图','Current map')
            tree.insert('','end',iid=row.rawcode,values=(row.rawcode,row.name,row.base_id,object_type,source,row.note))
        return True
