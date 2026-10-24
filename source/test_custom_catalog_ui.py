import tkinter as tk
from tkinter import ttk

from war3_campaign_catalog import CampaignInfo, Chapter, CatalogResult
from war3_custom_objects import CustomObjectEntry
from war3_custom_catalog_ui import CatalogSelection, CampaignCatalogUI


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


def test_real_widgets_search_mode_columns_and_copy_guard(tmp_path):
    root=tk.Tk(); root.withdraw()
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
        assert ui.can_copy('X001') and not ui.can_copy(invalid.rawcode)
        assert ui.rows('unit','hfoo')==[row,invalid]
        ui.modes['unit'].set('general')
        assert not ui.render_custom(tree,'unit','')
        ui.refresh_language()
    finally:
        root.destroy()


def test_shared_selection_and_partial_diagnostics(tmp_path):
    root=tk.Tk(); root.withdraw()
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
        root.destroy()
