"""Real async controller and Tk rendering; fake only the external game transport."""
from dataclasses import replace
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
import pytest

from test_quest_analysis import snapshot
from war3_quest_analysis import analyze_quests
from war3_quest_ui import QuestAnalysisController,QuestAnalysisUI


SCRIPT='''globals
quest q=null
integer count=0
endglobals
function main takes nothing returns nothing
 set q=CreateQuest()
 call QuestSetTitle(q,"Hidden relic")
 if count >= 4 then
  call QuestSetCompleted(q,true)
 endif
 call CustomDefeatBJ(Player(0),"Time up")
endfunction
'''


class Client:
    def __init__(self):
        self.token=1;self.connection='test';self.reads=0;self.checks=0
        self.reading=None;self.release=None
    def identity(self):return self.connection
    def read(self,cancelled):
        self.reads+=1;s=replace(snapshot(SCRIPT),session_token=self.token,identity=self.connection)
        if self.reading:self.reading.set()
        if self.release:self.release.wait(2)
        return s
    def check(self,snapshot):
        self.checks+=1;return snapshot.identity==self.connection and snapshot.session_token==self.token


def pump(controller,finished,visible=True):
    end=time.monotonic()+3
    while time.monotonic()<end:
        controller.tick(visible)
        if finished():return
        time.sleep(.005)
    assert finished(),(controller.state,controller.error)


def test_first_visible_page_reads_and_analyzes_but_hidden_page_does_no_game_work():
    client=Client();c=QuestAnalysisController(lambda:client)
    try:
        for _ in range(3):c.tick(False)
        assert client.reads==0 and client.checks==0
        pump(c,lambda:c.report is not None)
        assert c.report.quests[0].title=='Hidden relic' and client.reads==1
        c.tick(False)
        assert c.report is None
        old=(client.reads,client.checks)
        for _ in range(10):c.tick(False)
        assert (client.reads,client.checks)==old
    finally:c.close()


def test_map_change_clears_report_and_requires_new_source():
    clock=[100.];client=Client();c=QuestAnalysisController(lambda:client,clock=lambda:clock[0])
    try:
        pump(c,lambda:c.report is not None)
        client.token=2;clock[0]+=2
        pump(c,lambda:c.report is None)
        assert c.state in ('changed','reading','analyzing')
        pump(c,lambda:c.report is not None)
        assert c.report.snapshot.session_token==2
    finally:c.close()


@pytest.mark.parametrize('change',['hide','close','reconnect'])
def test_old_read_reply_never_publishes_after_invalidation(change):
    client=Client();client.reading=threading.Event();client.release=threading.Event()
    c=QuestAnalysisController(lambda:client)
    c.tick(True);assert client.reading.wait(1)
    if change=='hide':c.tick(False)
    elif change=='close':c.close()
    else:client.connection='other';c.invalidate('connection changed')
    client.release.set()
    try:
        pump(c,lambda:not c.busy,visible=False)
        assert c.report is None
    finally:c.close()


def test_delayed_queue_delivery_cannot_renew_worker_validation_time():
    clock=[100.];client=Client();ready=threading.Event()
    c=QuestAnalysisController(lambda:client,clock=lambda:clock[0])
    class Replies(queue.Queue):
        def put(self,item):
            super().put(item)
            if item[2]=='result':ready.set()
    c.replies=Replies();c.tick(True);assert ready.wait(2)
    clock[0]=120.;client.token=2
    c.tick(True)
    try:
        assert c.report is None and c.checked_at!=clock[0]
    finally:c.close()


def test_connection_change_is_rejected_before_publish_even_without_map_tick():
    client=Client();ready=threading.Event();c=QuestAnalysisController(lambda:client)
    class Replies(queue.Queue):
        def put(self,item):
            super().put(item)
            if item[2]=='result':ready.set()
    c.replies=Replies();c.tick(True);assert ready.wait(2)
    client.connection='replaced'
    c.tick(True)
    try:assert c.report is None
    finally:c.close()


def test_analysis_stage_is_visible_and_cancelled_without_touching_tk():
    entered=threading.Event();release=threading.Event();worker_ids=[];main=threading.get_ident()
    def delayed(s,cancelled):
        worker_ids.append(threading.get_ident());entered.set();release.wait(2)
        return analyze_quests(s,cancelled)
    c=QuestAnalysisController(lambda:Client(),analyzer=delayed)
    c.tick(True);assert entered.wait(1);c.tick(True)
    assert c.state=='analyzing' and worker_ids[0]!=main
    c.cancel();release.set()
    try:
        pump(c,lambda:not c.busy)
        assert c.report is None and c.state=='cancelled'
    finally:c.close()


def test_unconnected_and_unsupported_script_are_not_success_states():
    c=QuestAnalysisController(lambda:None);c.tick(True)
    try:assert c.report is None and c.state=='disconnected'
    finally:c.close()
    class LuaClient(Client):
        def read(self,cancelled):return replace(super().read(cancelled),language='lua')
    c=QuestAnalysisController(lambda:LuaClient())
    try:
        pump(c,lambda:c.state=='unavailable')
        assert c.report is None and 'lua' in c.error
    finally:c.close()


@pytest.fixture(scope='module')
def tk_root():
    root=tk.Tk();root.withdraw()
    yield root
    root.destroy()


def test_actual_task_widgets_search_details_unknowns_source_and_language(tk_root):
    language=['zh'];client=Client();ui=QuestAnalysisUI(tk_root,lambda:language[0],lambda:client)
    panel=ttk.Frame(tk_root);ui.add_controls(panel)
    try:
        pump(ui.controller,lambda:ui.controller.report is not None)
        ui.render()
        assert 'owned.w3n' in ui.source.get() and ui.controller.report.snapshot.script_sha256 in ui.source.get()
        rows=ui.tree.get_children()
        assert len(rows)>=3
        target=next(i for i in rows if 'Hidden relic' in str(ui.tree.item(i,'values')))
        ui.tree.selection_set(target);ui.show_selected()
        detail=ui.detail.get('1.0','end')
        assert '不少于 4' in detail and 'QuestSetCompleted' not in detail
        assert '脚本' in ui.status.get() and '只读任务信息' in ui.notice.cget('text')
        ui.evidence.set(True);ui.render_rows()
        ui.search.set('CustomDefeatBJ');ui.render_rows()
        assert ui.tree.get_children() and all('Hidden relic' not in str(ui.tree.item(i,'values')) for i in ui.tree.get_children())
        language[0]='en';ui.refresh_language()
        assert ui.refresh_button.cget('text')=='Scan again' and 'Static' in ui.status.get()
        assert ui.tree.heading('kind','text')=='Type'
    finally:ui.close();panel.destroy()


def test_trainer_script_bridge_uses_existing_catalog_and_read_only_memory_factory(monkeypatch):
    import war3_reforged_trainer as module
    import war3_current_map_script as script_module
    trainer=object.__new__(module.War3Trainer);trainer.pid=456
    catalog=object();trainer.current_map_catalog_client=lambda:catalog
    sentinel=object();calls=[]
    def factory(pid,current,memory_factory,*,source_policy):
        calls.append((pid,current,memory_factory,source_policy));return sentinel
    monkeypatch.setattr(script_module,'create_current_map_script_client',factory)
    assert trainer.current_map_script_client() is sentinel
    assert calls[0][:2]==(456,catalog) and callable(calls[0][2]) and callable(calls[0][3])


def test_review_existing_report_expires_while_map_check_worker_is_blocked():
    clock=[100.];client=Client();entered=threading.Event();release=threading.Event()
    c=QuestAnalysisController(lambda:client,clock=lambda:clock[0])
    try:
        pump(c,lambda:c.report is not None)
        original=client.check
        def blocked(s):entered.set();release.wait(2);return original(s)
        client.check=blocked;client.token=2;clock[0]=101.1
        c.tick(True);assert entered.wait(1)
        clock[0]=120.;c.tick(True)
        assert c.report is None and c.state not in ('ready','partial')
        release.set();pump(c,lambda:not c.busy)
    finally:release.set();c.close()


def test_review_existing_report_expires_on_delayed_visible_tick():
    clock=[100.];client=Client();c=QuestAnalysisController(lambda:client,clock=lambda:clock[0])
    try:
        pump(c,lambda:c.report is not None)
        clock[0]=120.;c.tick(True)
        assert c.report is None and c.state not in ('ready','partial')
    finally:c.close()


def test_readonly_page_has_no_completion_controls_and_evidence_is_opt_in(tk_root):
    ui=QuestAnalysisUI(tk_root,lambda:'zh',lambda:None)
    panel=ttk.Frame(tk_root);ui.add_controls(panel)
    try:
        ui.controller.report=analyze_quests(snapshot(SCRIPT));ui.controller.state='ready';ui.render()
        buttons=[]
        def collect(widget):
            for child in widget.winfo_children():
                if isinstance(child,ttk.Button):buttons.append(str(child.cget('text')))
                collect(child)
        collect(panel)
        assert set(buttons)=={'重新检索','取消检索'}
        text=ui.detail.get('1.0','end')
        assert '完成条件' in text and '不少于 4' in text and 'QuestSetCompleted' not in text
        ui.evidence.set(True);ui.render_rows()
        text=ui.detail.get('1.0','end')
        assert 'count >= 4' in text and 'QuestSetCompleted' in text
        ui.evidence.set(False);ui.render_rows()
        assert 'QuestSetCompleted' not in ui.detail.get('1.0','end')
    finally:ui.close();panel.destroy()
