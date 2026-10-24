import tkinter as tk
from tkinter import ttk
import pytest

from war3_campaign_catalog import CampaignInfo, Chapter, CatalogResult
from war3_custom_objects import CustomObjectEntry
from war3_custom_catalog_ui import CatalogSelection, CampaignCatalogUI
from war3_current_map_catalog import CurrentMapCatalogClient,MAGIC
import struct
import threading
import time
from types import SimpleNamespace


@pytest.fixture(scope='module')
def shared_tk_root():
    # A desktop app has one interpreter. Reuse one here rather than repeatedly
    # bootstrap Tcl while the Windows test runner also loads native libraries.
    root=tk.Tk(); root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def gui_root(shared_tk_root):
    yield shared_tk_root
    for job in shared_tk_root.tk.call('after','info'):
        shared_tk_root.after_cancel(job)
    for child in shared_tk_root.winfo_children():
        child.destroy()


def test_new_selection_rejects_stale_result_and_clears_old_chapter(tmp_path):
    state=CatalogSelection()
    old=state.reset()
    info=CampaignInfo(tmp_path/'a.w3n','hash',(Chapter('一','a.w3x'),Chapter('二','b.w3x')))
    assert state.accept_info(old,info)
    token=state.select_chapter(0)
    result=CatalogResult({'unit':()},(),())
    assert state.accept_result(token,result)
    state.select_chapter(1)
    assert state.result is None
    assert not state.accept_result(token,result)
    state.reset()
    assert not state.accept_info(old,info)


def test_copy_permission_is_scoped_to_object_category():
    ui=object.__new__(CampaignCatalogUI)
    ui.modes={k:SimpleNamespace(get=lambda:'custom') for k in ('unit','item','ability')}
    ui.selection=CatalogSelection(result=CatalogResult({
        'unit':(CustomObjectEntry('X001','冲突','hfoo','新增','两层','冲突',False),),
        'item':(CustomObjectEntry('X001','正常','ckng','新增','战役公共'),)},(),()))
    assert not ui.can_copy('X001','unit')
    assert ui.can_copy('X001','item')


def test_real_widgets_search_mode_columns_and_copy_guard(tmp_path,gui_root):
    root=gui_root
    try:
        changed=[]
        ui=CampaignCatalogUI(root,lambda:changed.append(1),lambda:'zh')
        panel=ttk.Frame(root); ui.add_controls(panel,'unit')
        tree=ttk.Treeview(root)
        row=CustomObjectEntry('X001','战役队长','hfoo','新增','战役公共')
        invalid=CustomObjectEntry('<0x80414243>','名字','hfoo','新增','所选章节','不可复制',False)
        ui.selection.result=CatalogResult({'unit':(row,invalid),'item':(),'ability':()},(),())
        ui.modes['unit'].set('custom')
        assert ui.render_custom(tree,'unit','队长')
        assert tree.get_children()==('X001',)
        assert tree.item('X001','values')[1]=='战役队长'
        assert ui.can_copy('X001','unit') and not ui.can_copy(invalid.rawcode,'unit')
        assert ui.rows('unit','hfoo')==[row,invalid]
        ui.modes['unit'].set('general')
        assert not ui.render_custom(tree,'unit','')
        ui.refresh_language()
    finally:
        pass


def test_shared_selection_and_partial_diagnostics(tmp_path,gui_root):
    root=gui_root
    try:
        language=['zh']
        ui=CampaignCatalogUI(root,lambda:None,lambda:language[0])
        for kind in ('unit','item','ability'): ui.add_controls(ttk.Frame(root),kind)
        info=CampaignInfo(tmp_path/'test.w3n','hash',(Chapter('第一章','a.w3x'),))
        ui.selection.accept_info(ui.selection.generation,info)
        ui.selection.select_chapter(0)
        ui.selection.result=CatalogResult({'unit':(),'item':(),'ability':()},('damaged',),('read',))
        ui.update_display()
        assert '部分读取' in ui.status.get()
        assert '第一章' in ui.chapter_label.get()
        assert 'damaged' in ui.details()
        language[0]='en'; ui.refresh_language()
        assert 'Partial' in ui.status.get()
    finally:
        pass


def runtime_client(token):
    def query(op,kind=0,start=0,token=0):
        if op==318: return (MAGIC,1,state[0],1,0,0)
        name='当前队长'.encode();words=struct.unpack('<2Q',name+b'\0'*4)
        return (MAGIC,1,state[0],0,1,0,1,int.from_bytes(b'hfoo','little'),
            int.from_bytes(b'H600','little'),1,1,0,0,0,len(name),*words)
    state=[token]
    return CurrentMapCatalogClient(query,lambda:'game'),state


def pump(root,finished):
    deadline=time.monotonic()+3
    while not finished() and time.monotonic()<deadline:
        root.update();time.sleep(.01)
    assert finished()


def test_current_map_shared_search_copy_and_expiration(gui_root):
    client,state=runtime_client(42)
    ui=CampaignCatalogUI(gui_root,lambda:None,lambda:'zh',runtime_client=lambda:client)
    for kind in ('unit','item','ability'):
        ui.add_controls(ttk.Frame(gui_root),kind);ui.modes[kind].set('runtime')
    ui.detect_runtime();pump(gui_root,lambda:not ui._busy)
    assert ui.runtime_snapshot is not None
    assert ui.rows('unit','队长')[0].rawcode=='H600'
    assert ui.can_copy('H600','unit') and not ui.can_copy('H600','item')
    assert '检测时快照' in ui.status.get()
    state[0]=43;ui.check_runtime();pump(gui_root,lambda:not ui._busy)
    assert ui.runtime_snapshot is None and not ui.can_copy('H600','unit')
    assert not ui.rows('unit','') and '变化' in ui.status.get()


def test_current_map_old_worker_does_not_publish_after_source_change(gui_root):
    client,_=runtime_client(42);original=client.read;ready=threading.Event();release=threading.Event()
    def delayed(cancelled):
        ready.set();release.wait(2)
        return original()  # Simulate a worker finishing despite cancellation.
    client.read=delayed
    ui=CampaignCatalogUI(gui_root,lambda:None,lambda:'zh',runtime_client=client)
    ui.modes['unit'].set('runtime');ui.detect_runtime();assert ready.wait(1)
    ui.invalidate_runtime('地图会话已变化');release.set();pump(gui_root,lambda:not ui._busy)
    assert ui.runtime_snapshot is None and not ui.rows('unit','')


def test_current_map_disconnected_state_language_and_hidden_no_monitor(gui_root):
    ui=CampaignCatalogUI(gui_root,lambda:None,lambda:'en',runtime_client=lambda:None)
    ui.add_controls(ttk.Frame(gui_root),'unit');ui.modes['unit'].set('runtime')
    ui.detect_runtime()
    assert not ui._busy and 'connect' in ui.status.get().lower()
    ui.refresh_language();assert ui.runtime_snapshot is None


def test_current_map_hidden_page_does_not_start_periodic_query(gui_root):
    from unittest.mock import Mock
    client,_=runtime_client(42)
    ui=CampaignCatalogUI(gui_root,lambda:None,lambda:'zh',runtime_client=client)
    ui.add_controls(ttk.Frame(gui_root),'unit');ui.modes['unit'].set('runtime')
    ui.detect_runtime();pump(gui_root,lambda:not ui._busy)
    client.check=Mock(side_effect=AssertionError('hidden page must not query'))
    until=time.monotonic()+.25
    while time.monotonic()<until: gui_root.update();time.sleep(.01)
    client.check.assert_not_called()


def test_delayed_tk_tick_keeps_snapshot_but_requires_fresh_validation_for_copy(gui_root):
    client,_=runtime_client(42)
    ui=CampaignCatalogUI(gui_root,lambda:None,lambda:'zh',runtime_client=client)
    ui.modes['unit'].set('runtime');ui.detect_runtime();pump(gui_root,lambda:not ui._busy)
    ui._runtime_checked_at=time.monotonic()-3
    ui._poll()
    assert ui.runtime_snapshot is not None
    assert not ui.can_copy('H600','unit')
    ui.check_runtime();pump(gui_root,lambda:not ui._busy)
    assert ui.can_copy('H600','unit')
