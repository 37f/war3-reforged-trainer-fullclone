"""Use the real desktop/application composition; never connect to the game."""
from types import SimpleNamespace
import pytest

from war3_desktop_bridge import DesktopBridgeApi
from war3_fullclone_hotkeys import specs


@pytest.fixture
def desktop(monkeypatch):
    api=DesktopBridgeApi(initialize=False,offline=True);calls=[]
    def action(number,**options):
        calls.append(('native',number,options));return dict(changed=1)
    def clone(count,**options):
        calls.append(('clone',count,options));return dict(count=count,ability_issues=[])
    def control():
        calls.append(('control',));return dict(changed=1,restored=False)
    def gold(scope,amount):
        calls.append(('gold',scope,amount));return dict(changed=1)
    def infernal():calls.append(('infernal',));return '地狱火'
    def gather():calls.append(('gather',));return dict(changed=5)
    def progress(level):
        calls.append(('custom_level',level));return dict(rows=[{}],changed=1,skipped=0)
    def attributes(value):calls.append(('custom_attributes',value));return 1
    def cheat(command):calls.append(('cheat',command))
    trainer=SimpleNamespace(_native_selection_unavailable=True,fullclone_action=action,
        fullclone_clone=clone,fullclone_toggle_control=control,gold_mines=gold,
        fullclone_infernal=infernal,fullclone_gather_items=gather,
        hero_progress_24268=progress,set_selected_group_hero_attributes=attributes,
        CHEATS={'直接胜利':'allyourbasearebelongtous'},send_cheat=cheat)
    monkeypatch.setattr(api.app,'elephant_trainer',lambda:trainer)
    monkeypatch.setattr(api.app,'trainer',lambda:trainer)
    monkeypatch.setattr(api.app,'call_async',lambda fn,*args,**kwargs:fn())
    monkeypatch.setattr(api.port.value('root'),'after',lambda delay,fn,*args:fn(*args))
    try:yield api,calls
    finally:api.close()


def test_real_desktop_binds_every_extension_and_registers_enabled_keys(desktop):
    api,calls=desktop;active=api.port.value('hotkey_callbacks')
    assert len(active)==77 and all(s.name in active for s in specs(()))
    captured={}
    class Manager:
        registered_names=();fallback_names=()
        def start(self,items,on_trigger):
            self.registered_names=tuple(s.name for s in items)
            captured['trigger']=on_trigger;return {}
        def stop(self):pass
    manager=Manager();api.port.bind('hotkey_manager',manager)
    api.app.set_all_elephant_hotkeys(True)
    api.port.value('elephant_hotkeys_enabled').set(True)
    api.app.refresh_elephant_hotkeys()
    assert len(manager.registered_names)==77
    captured['trigger']('infernal')
    assert calls==[('infernal',)]


@pytest.mark.parametrize('name,expected',[
    ('clone_unit',('clone',1,dict(owner_mode='player',player=24))),
    ('clone_to_self',('clone',1,dict(owner_mode='self',player=24))),
    ('mass_clone',('clone',3,dict(owner_mode='player',player=24))),
    ('toggle_owner_control',('control',)),('gold_mine',('gold','selected','250000')),
    ('infernal',('infernal',)),('gather_ground_items',('gather',)),
])
def test_keyboard_dispatch_reaches_same_commands_as_extension_buttons(desktop,name,expected):
    api,calls=desktop
    api.app.fc_settings().update(owner_enabled=True,owner_mode='player',owner_player=24,mine_amount='250000')
    api.port.value('elephant_mass_clone_count').set('3')
    api.app.trigger_elephant_hotkey(name)
    assert calls==[expected]
    if name!='clone_to_self':
        calls.clear()
        api.app.fc_action('clone' if name=='clone_unit' else name)
        assert calls==[expected]


@pytest.mark.parametrize('name,mode,count',[
    ('clone_unit','author',1),('mass_clone','author',3),('clone_to_self','self',1),
])
def test_copy_hotkeys_with_owner_switch_off_keep_their_ownership_contract(desktop,name,mode,count):
    api,calls=desktop
    api.port.value('elephant_mass_clone_count').set('3')
    api.app.trigger_elephant_hotkey(name)
    assert calls==[('clone',count,dict(owner_mode=mode,player=0))]


@pytest.mark.parametrize('name,custom,expected',[
    ('hero_level',False,('native',6,{})),
    ('hero_attributes',False,('native',7,dict(value=-1))),
    ('hero_level',True,('custom_level',12)),
    ('hero_attributes',True,('custom_attributes',50)),
])
def test_increment_and_custom_modes_through_real_bound_callbacks(desktop,name,custom,expected):
    api,calls=desktop
    api.app.fc_settings().update(hero_custom=custom,attributes_custom=custom)
    api.port.value('elephant_hero_level').set('12');api.port.value('elephant_hero_attributes').set('50')
    api.app.trigger_elephant_hotkey(name)
    assert calls==[expected]


def test_alt_b_uses_only_author_cheat_and_removed_mode_cannot_be_set(desktop):
    from war3_fullclone_desktop import set_option
    api,calls=desktop
    assert 'victory_mode' not in api.app.fc_settings()
    with pytest.raises(ValueError):set_option(api,'victory_mode','player')
    api.app.trigger_elephant_hotkey('instant_victory')
    assert calls==[('cheat','allyourbasearebelongtous')]


def test_original_level_panel_keeps_using_its_input_without_custom_checkbox(desktop):
    api,calls=desktop
    api.port.value('elephant_hero_level').set('12')
    api.app.elephant_set_hero_level()
    assert calls==[('custom_level',12)]


@pytest.mark.parametrize('total',[0,3])
def test_bulk_restore_generic_action_keeps_unit_snapshot_unchanged(desktop,monkeypatch,total):
    api,calls=desktop
    trainer=api.app.elephant_trainer()
    trainer.fullclone_restore_all_teams=lambda:(calls.append(('restore_all',)) or dict(changed=total,total=total))
    monkeypatch.setattr(api,'_run_action',lambda fn,key:fn())
    monkeypatch.setattr(api,'_mark_units_changed',lambda:pytest.fail('alliance-only command must not mark units changed'))
    # Bypass only the offline transport gate; the real application dispatch and
    # action wrapper still run against the injected fixture trainer.
    result=type(api).fullclone_action.__wrapped__(api,'restore_all_teams')
    assert result['success'] and calls==[('restore_all',)]
    assert ('没有可恢复' if not total else '3 个玩家') in result['message']
