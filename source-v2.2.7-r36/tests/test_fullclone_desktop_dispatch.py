"""Use the real desktop/application composition; never connect to the game."""
from types import SimpleNamespace
import pytest

from war3_desktop_bridge import DesktopBridgeApi
from war3_fullclone_hotkeys import specs


@pytest.fixture
def desktop(monkeypatch,tmp_path):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
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
        fullclone_give_owner=lambda player:(calls.append(('give',player)) or dict(selected=1,changed=1,skipped=0)),
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
    captured['trigger']('point_spell')
    assert calls==[('infernal',)]


@pytest.mark.parametrize('name,expected',[
    ('clone_unit',('clone',1,dict(owner_mode='player',player=24))),
    ('clone_to_self',('clone',1,dict(owner_mode='self',player=24))),
    ('mass_clone',('clone',3,dict(owner_mode='player',player=24))),
    ('toggle_owner_control',('control',)),('gold_mine',('gold','selected','250000')),
    ('give_owner',('give',1)),
    ('point_spell',('infernal',)),('gather_ground_items',('gather',)),
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


def test_hero_skill_swap_desktop_routes(desktop, monkeypatch):
    from war3_services import hero_skill_swap
    api, _ = desktop
    requested = []
    monkeypatch.setattr(hero_skill_swap, 'exchange_hero_skills',
                        lambda host, slot: requested.append(slot) or 2)
    monkeypatch.setattr(hero_skill_swap, 'restore_hero_skills',
                        lambda host: {'restored':2, 'pending':1, 'issues':[]})
    action = type(api).fullclone_action.__wrapped__
    for suffix in ('1','2','3','4','all'):
        assert '已交换' in action(api, 'swap_hero_skill_'+suffix)['message']
    assert requested == [0,1,2,3,None]
    assert '还有 1 名待还原' in action(api, 'restore_hero_skills')['message']


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


@pytest.mark.parametrize('scope,mode',[('all',0),('heroes',1),('nonheroes',2)])
def test_army_button_reaches_its_independent_operation(desktop,monkeypatch,scope,mode):
    from war3_fullclone_desktop import set_option
    api,calls=desktop
    def heal(value):
        calls.append(('army',value));return dict(player=24,eligible=3,changed=2)
    api.app.elephant_trainer().fullclone_fill_owner=heal
    set_option(api,'army_scope',scope)
    monkeypatch.setattr(api,'_run_action',lambda fn,key:fn())
    result=type(api).fullclone_action.__wrapped__(api,'fill_owner_life_mana')
    assert calls==[('army',mode)] and result['success']
    assert '中立敌对' in result['message'] and '2 个单位' in result['message']


@pytest.mark.parametrize('mode',['include','exclude'])
def test_alt_f2_and_button_share_the_same_item_filter(desktop,mode):
    from war3_fullclone_desktop import set_option
    api,calls=desktop
    def gather(**options):calls.append(options);return dict(changed=0)
    api.app.elephant_trainer().fullclone_gather_items=gather
    set_option(api,'item_filter_ids','I000 ratf');set_option(api,'item_filter_mode',mode)
    api.app.trigger_elephant_hotkey('gather_ground_items')
    message=api.app.fc_action('gather_ground_items')
    assert calls==[dict(filter_mode=mode,filter_ids='I000 ratf')]*2
    assert '0 个地面物品' in message
    set_option(api,'item_filter_mode','all');api.app.fc_action('gather_ground_items')
    assert calls[-1]=={} and api.app.fc_settings()['item_filter_ids']=='I000 ratf'


@pytest.mark.parametrize('key,value',[('army_scope','invalid'),('item_filter_mode','invalid'),('item_filter_ids','x'*129)])
def test_r34_bad_settings_never_reach_game_dispatch(desktop,key,value):
    from war3_fullclone_desktop import set_option
    api,calls=desktop
    before=dict(api.app.fc_settings())
    with pytest.raises(ValueError):set_option(api,key,value)
    assert calls==[] and api.app.fc_settings()==before


def test_ctrl_n_uses_formation_but_ctrl_b_keeps_single_copy(desktop,monkeypatch):
    from war3_fullclone_desktop import set_option
    api,calls=desktop
    def form(trainer,count,kind,gap,**options):
        calls.append(('formation',count,kind,gap,options));return dict(count=count,ability_issues=[])
    monkeypatch.setattr('war3_fullclone_extras.clone_formation',form)
    set_option(api,'formation','ring');set_option(api,'formation_gap','64')
    api.app.fc_settings().update(owner_enabled=True,owner_mode='player',owner_player=27)
    api.port.value('elephant_mass_clone_count').set('3')
    api.app.trigger_elephant_hotkey('mass_clone');api.app.trigger_elephant_hotkey('clone_unit')
    assert calls==[('formation',3,'ring','64',dict(owner_mode='player',player=27)),('clone',1,dict(owner_mode='player',player=27))]


def test_local_supply_save_works_offline_without_game_access(desktop):
    api,calls=desktop
    api.fullclone_set_option('supply_text_2','stwp 1 1')
    assert api.fullclone_save_supplies()['success']
    from war3_fullclone_supplies import load
    assert load()['supply_text_2']=='stwp 1 1' and calls==[]


@pytest.mark.parametrize('name,method,args',[
    ('freeze_owner','war3_fullclone_extras.toggle_frozen',('heroes',True)),
    ('supply_deliver','war3_fullclone_supplies.deliver',('phea 2 1','hero')),
    ('point_spell','war3_fullclone_extras.point_spell',('AHfs',)),
])
def test_r35_buttons_dispatch_to_their_selected_options(desktop,monkeypatch,name,method,args):
    api,calls=desktop
    api.app.fc_settings().update(freeze_scope='heroes',freeze_buildings=True,supply_slot='3',supply_text_3='phea 2 1',point_spell='AHfs')
    def action(trainer,*actual):
        calls.append(actual)
        return '已接受命令' if name=='point_spell' else dict(changed=2,skipped=0,restored=False)
    monkeypatch.setattr(method,action);monkeypatch.setattr(api,'_run_action',lambda fn,key:fn())
    assert type(api).fullclone_action.__wrapped__(api,name)['success'] and calls==[args]



@pytest.mark.parametrize('hotkey,expected_count', [('all_debuffs', 8), ('all_buffs', 15)])
def test_standard_effect_hotkeys_reach_bound_facade(desktop, monkeypatch, hotkey, expected_count):
    from contextlib import nullcontext
    from war3_backend import War3Trainer

    api, calls = desktop
    trainer = War3Trainer.__new__(War3Trainer)
    trainer._native_selection_unavailable = True

    def direct_effect(code, action, x_bits=0, y_bits=0, **options):
        rawcode = code.to_bytes(4, 'big').decode('ascii') if isinstance(code, int) else code
        calls.append((rawcode, action, options))
        return {'changed': 1}

    def unexpected(*args, **kwargs):
        pytest.fail('This bundle must use the indexed effect path')

    monkeypatch.setattr(trainer, '_native_helper_transaction', nullcontext)
    monkeypatch.setattr(trainer, 'effect_batch_24268', direct_effect)
    monkeypatch.setattr(trainer, 'apply_direct_roar_buff_to_selected_unit', unexpected)
    monkeypatch.setattr(trainer, 'get_selected_unit_position', unexpected)
    monkeypatch.setattr(trainer, '_run_selected_ability_effect',
                        lambda code, mode, **kw: (calls.append((code, mode, kw)) or (1, 1)))
    monkeypatch.setattr(trainer, 'enable_selected_toggle_ability',
                        lambda code, order: (calls.append((code, order, {})) or 1))
    monkeypatch.setattr(api.app, 'elephant_trainer', lambda: trainer)

    result = type(api).trigger_hotkey.__wrapped__(api, hotkey)
    assert result['success'], result
    assert f'{expected_count}/{expected_count}' in result['message']
    assert len(calls) == expected_count
    if hotkey == 'all_buffs':
        assert ('Ahwd', 3, {'use_unit_position': True}) in calls
        assert ('AEtq', 'immediate', {'hold_seconds': 12.0}) in calls
        assert ('ANms', 852589, {}) in calls
        assert any(code == 'AIsa' for code, _, _ in calls)
    else:
        assert 'ANht' in result['message']
        assert [code for code, _, _ in calls] == [
            'Acrs', 'Aply', 'Aslo', 'Acri', 'Afae', 'ANso', 'AEer', 'ANdo',
        ]


def test_standard_debuff_bundle_retains_the_legacy_anht_route(monkeypatch):
    from war3_backend import War3Trainer

    trainer = War3Trainer.__new__(War3Trainer)
    trainer._native_selection_unavailable = False
    calls = []
    monkeypatch.setattr(trainer, 'apply_direct_ability_to_selected_unit', lambda code: 1)
    monkeypatch.setattr(trainer, 'apply_direct_roar_buff_to_selected_unit',
                        lambda code: (calls.append(code) or 1))
    result = trainer.apply_standard_debuffs_to_selected_unit()
    assert result == (9, 9)
    assert not result.skipped
    assert calls == ['ANht']
