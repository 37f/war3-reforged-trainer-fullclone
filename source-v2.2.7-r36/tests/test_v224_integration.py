"""New author catalogue actions share the existing RPC/extension application."""
import pytest
from test_fullclone_desktop_dispatch import desktop


def test_v224_version_and_catalogue_maximum_survive_migration(desktop):
    from war3_metadata import APP_VERSION,WIN10_COMPAT_REVISION,FULLCLONE_EDITION
    assert APP_VERSION=='2.2.7' and WIN10_COMPAT_REVISION=='2.2.7-resource-lock-and-errors-20261122'
    assert FULLCLONE_EDITION=='FullClone R36'
    api,calls=desktop
    result=api.search_id_catalog('upgrade','Rhme')
    row=next(r for r in result['rows'] if r['rawcode']=='Rhme')
    assert isinstance(row['maxLevel'],int) and row['maxLevel']>0
    assert calls==[]


@pytest.mark.parametrize('action,params,method,fields',[
    ('add_item',dict(rawcode='ratf'),'elephant_add_item',('elephant_item_rawcode',)),
    ('add_ability',dict(rawcode='AHbz',level='2'),'elephant_add_ability',('elephant_ability_rawcode','elephant_ability_level')),
    ('set_tech',dict(rawcode='Rhme',level='3'),'elephant_set_tech',('elephant_tech_rawcode','elephant_tech_level')),
])
def test_author_direct_catalogue_actions_keep_parameters(desktop,monkeypatch,action,params,method,fields):
    api,calls=desktop
    monkeypatch.setattr(api.app,method,lambda:calls.append(tuple(api.port.value(field).get() for field in fields)))
    monkeypatch.setattr(api,'_mark_units_changed',lambda:None)
    result=type(api).execute_elephant_action.__wrapped__(api,action,params)
    assert result['success'] and result['action']==action
    assert calls==[tuple(params[key] for key in ('rawcode','level')[:len(fields)])]


@pytest.mark.parametrize('mode,player,expected',[
    ('self',0,-1),('selected',0,2),('player',24,24),('player',27,27),
])
def test_catalogue_spawn_follows_enabled_panel_ownership(desktop,monkeypatch,mode,player,expected):
    api,calls=desktop;trainer=api.app.elephant_trainer()
    trainer.query_mouse_world_position=lambda:(128.,256.)
    trainer.fullclone_owner=lambda:dict(a=2)
    api.app.fc_settings().update(owner_enabled=True,owner_mode=mode,owner_player=player)
    monkeypatch.setattr(api,'_mark_units_changed',lambda:None)
    result=type(api).execute_elephant_action.__wrapped__(api,'create_unit',dict(rawcode='hfoo',to_self=False))
    assert result['success']
    assert calls==[('native',11,dict(value=expected,rawcode=int.from_bytes(b'hfoo','big'),x=128.,y=256.))]


def test_catalogue_spawn_with_panel_switch_off_keeps_author_local_creation(desktop,monkeypatch):
    api,calls=desktop;trainer=api.app.elephant_trainer()
    def create(code,**kw):calls.append(('author_local',code,kw));return int.from_bytes(b'hfoo','big'),123
    trainer.create_local_unit=create
    api.app.fc_settings().update(owner_enabled=False,owner_mode='player',owner_player=27)
    monkeypatch.setattr(api,'_mark_units_changed',lambda:None)
    result=type(api).execute_elephant_action.__wrapped__(api,'create_unit',dict(rawcode='hfoo',to_self=False))
    assert result['success'] and calls==[('author_local','hfoo',dict(use_selected_lookup=True))]
