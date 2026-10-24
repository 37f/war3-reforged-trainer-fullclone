import tkinter as tk
from tkinter import ttk
import pytest

from war3_campaign_catalog import CampaignInfo, Chapter, CatalogResult
from war3_custom_objects import CustomObjectEntry
from war3_custom_catalog_ui import CatalogSelection, CampaignCatalogUI


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
