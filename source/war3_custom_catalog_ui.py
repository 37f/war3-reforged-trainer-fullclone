"""R20 shared offline UI; workers never access Tk or the game process."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
import threading
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
    def __init__(self, root, on_change, language):
        self.root,self.on_change,self.language=root,on_change,language
        self.selection=CatalogSelection()
        self.modes={kind:tk.StringVar(root,'general') for kind in ('item','unit','ability')}
        self.path_label=tk.StringVar(root,'')
        self.chapter_label=tk.StringVar(root,'')
        self.status=tk.StringVar(root,'')
        self._labels=[]; self._combos=[]; self._file_buttons=[]; self._detect_buttons=[]
        self._queue=queue.Queue(); self._busy=False; self._operation=''; self._error=''
        root.after(80,self._poll)
        self.update_display()

    def text(self, zh, en):
        return zh if self.language()=='zh' else en

    def _label(self, widget, zh, en):
        self._labels.append((widget,zh,en)); widget.configure(text=self.text(zh,en))
        return widget

    def add_controls(self, tab, kind):
        panel=ttk.Frame(tab); panel.grid(row=0,column=0,sticky='ew',pady=(0,8))
        for column,(value,zh,en) in enumerate((('general','通用目录','General catalog'),('custom','战役与所选章节','Campaign and selected chapter'))):
            self._label(ttk.Radiobutton(panel,variable=self.modes[kind],value=value,
                command=self.on_change),zh,en).grid(row=0,column=column,sticky='w',padx=(0,10))
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
        ttk.Label(panel,textvariable=self.status,wraplength=1050).grid(row=3,column=0,columnspan=4,sticky='w',pady=(5,0))
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
                if token==self.selection.generation:
                    self._error=error
                    if not error:
                        if operation=='list': self.selection.accept_info(token,payload)
                        else: self.selection.accept_result(token,payload)
                self.update_display(); self.on_change()
        except queue.Empty:
            pass
        self.root.after(80,self._poll)

    def update_display(self):
        state=self.selection
        values=[] if state.info is None else [f'{i+1}. {x.title} [{x.path}]' for i,x in enumerate(state.info.chapters)]
        self.chapter_label.set(values[state.chapter_index] if state.chapter_index>=0 and values else '')
        for combo in self._combos: combo.configure(values=values,state='readonly' if values else 'disabled')
        for button in self._file_buttons: button.configure(state='disabled' if self._busy else 'normal')
        for button in self._detect_buttons: button.configure(state='normal' if values and state.chapter_index>=0 and not self._busy else 'disabled')
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
        return self.modes[kind].get()=='custom'

    def rows(self,kind,query):
        result=self.selection.result
        if result is None: return []
        query=query.strip().casefold()
        return [row for row in result.entries.get(kind,()) if query in ' '.join((row.rawcode,row.name,row.base_id,row.object_type,row.source,row.note)).casefold()]

    def can_copy(self,rawcode):
        result=self.selection.result
        return result is not None and any(row.rawcode==rawcode and row.copyable for rows in result.entries.values() for row in rows)

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
            source=row.source if self.language()=='zh' else row.source.replace('战役公共','Campaign').replace('所选章节','Selected chapter')
            tree.insert('','end',iid=row.rawcode,values=(row.rawcode,row.name,row.base_id,object_type,source,row.note))
        return True
