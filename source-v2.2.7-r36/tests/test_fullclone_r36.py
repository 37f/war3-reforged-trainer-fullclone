from pathlib import Path
from threading import RLock
from types import SimpleNamespace

from war3_fullclone_quests import ScriptSnapshot, _members, render
from war3_quest_analysis import analyze_quests
from war3_quest_status import QuestStatusPlan


def test_localized_map_text_keeps_original_objectives_and_base_fallback():
    script = b'''
globals
    quest q = null
    questitem objective = null
endglobals
function main takes nothing returns nothing
    set q = CreateQuestBJ(bj_QUESTTYPE_REQ_DISCOVERED, "TRIGSTR_1", "TRIGSTR_2", "")
    set objective = QuestCreateItem(q)
    call QuestItemSetDescription(objective, "TRIGSTR_3")
endfunction
'''
    base = 'STRING 1\n{\nTitle\n}\nSTRING 2\n{\nDescription\n}\nSTRING 3\n{\nOriginal objective\n}'
    chinese = 'STRING 1\n{\n守卫城门\n}\nSTRING 2\n{\n救出村民。\n}'
    members = {'war3map.j':script, 'war3map.wts':base.encode(),
               r'_Locales\zhCN.w3mod\war3map.wts':chinese.encode()}
    archive = SimpleNamespace(read=lambda member, **kw: members.get(member))
    data, strings, language = _members(archive, text_locale='zhCN')
    rows, _, _ = render(analyze_quests(ScriptSnapshot(script=data, strings_data=strings, language=language)))
    assert rows[0]['title'] == '守卫城门'
    assert rows[0]['description'] == '救出村民。'
    assert 'Original objective' in rows[0]['text']
    assert 'Objectives' in rows[0]['textEn']
    assert '救出村民。' in rows[0]['textEn']
    assert 'Completion conditions' in rows[0]['textEn']


def test_enabled_override_without_matching_file_still_checks_current_map(tmp_path, monkeypatch):
    import war3_fullclone_casc as casc
    from war3_fullclone_source import _official_override
    root = tmp_path/'game'
    registered = tmp_path/'registered'
    monkeypatch.setattr(casc, '_local_file_override_configuration', lambda: (True, (registered,), 0))
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    name = r'Campaign\Classic\TFT\UndeadX07b.w3x'
    other = root/'Campaign'/'Classic'/'TFT'/'UndeadX06.w3x'
    other.parent.mkdir(parents=True)
    other.touch()
    assert not _official_override(root, name, 'zhCN')
    matching = registered/'_retail_'/'war3.w3mod'/'Campaign'/'Classic'/'TFT'/'UndeadX07b.w3x'
    matching.parent.mkdir(parents=True)
    matching.touch()
    assert str(matching) in _official_override(root, name, 'zhCN')


def test_status_keeps_unambiguous_matches_and_marks_only_missing_or_duplicate(monkeypatch):
    import war3_fullclone_status as status
    plan = QuestStatusPlan(tuple((k, (k,)) for k in ('main','side','missing','duplicate1','duplicate2')), ())
    monkeypatch.setattr(status, 'status_plan', lambda report: plan)
    monkeypatch.setattr(status, 'check_source', lambda *args: True)
    monkeypatch.setattr(status, '_globals', lambda *args: {
        'main': (0x20000, 1), 'side': (0x20010, 2),
        'duplicate1': (0x20020, 3), 'duplicate2': (0x20030, 3)
    })
    progress = {'main': (True, False), 'side': (False, False)}
    def execute(*args):
        return [dict(node=node,handle=handle,completed=progress[k][0],failed=progress[k][1],discovered=True,error=0)
                for k,node,handle in [('main',0x20000,1),('side',0x20010,2)]]
    engine = SimpleNamespace(session=SimpleNamespace(lock=RLock(), cache={}), _execute=execute)
    trainer = SimpleNamespace(_engine_instance_24268=lambda: engine)
    report = object()
    proof = {'metadata': {}}
    assert {k:v['state'] for k,v in status.query_states(trainer,report,proof).items()} == {
        'main':'已完成','side':'进行中','missing':'状态未确认','duplicate1':'状态未确认','duplicate2':'状态未确认'
    }
    progress['side'] = False, True
    assert status.query_states(trainer,report,proof)['side']['state'] == '已失败'


def test_elephant_hotkeys_use_current_army_scope_and_selected_skill(monkeypatch):
    from war3_fullclone_application import DEFAULTS, FullCloneApplication
    from war3_fullclone_hotkeys import specs
    class Base:
        def hotkey_actions(self):return {}
    class App(FullCloneApplication, Base):
        def elephant_trainer(self):return trainer
        def fc_settings(self):return options
    calls = []
    options = dict(DEFAULTS, army_scope='heroes', point_spell='AHbz')
    def fill(scope):
        calls.append(('army', scope))
        return dict(player=0, eligible=3, changed=2)
    trainer = SimpleNamespace(fullclone_fill_owner=fill)
    monkeypatch.setattr('war3_fullclone_extras.point_spell', lambda t, code: calls.append(('point', code)))
    actions = App().hotkey_actions()
    keys = {(s.modifiers,s.virtual_key):s.name for s in specs(()) if not s.hold_keys}
    actions[keys[2,0x20]]()
    actions[keys[2,0x71]]()
    options.update(army_scope='all', point_spell='ANrf')
    actions[keys[2,0x20]]()
    actions[keys[2,0x71]]()
    assert calls == [('army',1),('point','AHbz'),('army',0),('point','ANrf')]
