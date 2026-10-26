"""The exact controlled-game fixture must qualify without bypassing any guard."""
from pathlib import Path
from war3_quest_execution import build_completion_plan
from test_quest_execution import _report

def test_runtime_fixture_has_two_complete_original_flows_and_no_dynamic_fallback():
    report=_report((Path(__file__).parent/'test_fixtures/r23_original_flow.j').read_text(encoding='utf8'))
    assert len(report.quests)==2
    plans=[build_completion_plan(report,q.key) for q in report.quests]
    assert all(p.eligible for p in plans),[(p.quest_title,p.reasons) for p in plans]
    sync=next(p for p in plans if p.quest_alias=='udg_R23SyncQuest')
    delay=next(p for p in plans if p.quest_alias=='udg_R23DelayQuest')
    assert sync.chain_functions==('R23CompleteSync','R23Followup')
    assert 'UnitAddItemById' in sync.recognized_calls and 'CreateUnit' in sync.recognized_calls
    assert any('udg_R23SyncCount' in e.source for e in sync.evidence)
    assert 'TriggerSleepAction' in delay.recognized_calls
    assert any('50' in e.source and 'SetPlayerState' in e.source for e in delay.evidence)
