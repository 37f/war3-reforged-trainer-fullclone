"""User-visible meanings: do not confuse static rules with live progress."""
from types import SimpleNamespace
from dataclasses import replace
import pytest
from test_quest_analysis import analyze
from war3_quest_ui import QuestAnalysisUI

def details(script):
    report=analyze(script)
    ui=object.__new__(QuestAnalysisUI);ui.language=lambda:'zh'
    ui.controller=SimpleNamespace(report=report)
    return ui,report,ui.quest_details(report.quests[0])

def script(condition='count >= 3',required='true'):
    return '''globals
quest q=null
integer count=0
unit hero=null
trigger t=null
endglobals
function Win takes nothing returns nothing
 if CONDITION then
  call QuestSetCompleted(q,true)
 endif
endfunction
function Lose takes nothing returns nothing
 if IsUnitDeadBJ(hero) then
  call QuestSetFailed(q,true)
 endif
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 call QuestSetTitle(q,"收集碎片")
 call QuestSetDescription(q,"收集三块碎片，英雄必须存活。")
 call QuestSetRequired(q,REQUIRED)
 set t=CreateTrigger()
 call TriggerRegisterAnyUnitEventBJ(t,EVENT_PLAYER_UNIT_DEATH)
 call TriggerAddAction(t,function Win)
 call TriggerAddAction(t,function Lose)
endfunction
'''.replace('CONDITION',condition).replace('REQUIRED',required)

def test_player_first_summary_classifies_main_and_explains_counter_and_death():
    ui,r,text=details(script())
    assert '主线任务' in text and '任务目标' in text
    assert '完成条件' in text and '失败条件' in text
    assert '不少于 3' in text and '死亡' in text
    assert '计数' in text and '当前' in text
    assert '有单位死亡时' in text
    assert 'QuestSetCompleted' not in text and '调用链' not in text

@pytest.mark.parametrize('required,label',[('false','支线任务'),('unknownFlag','类型未确认')])
def test_optional_and_unknown_required_flags_are_not_assumed_main(required,label):
    _,_,text=details(script(required=required))
    assert label in text

def test_and_or_and_player_number_are_explained_without_changing_logic():
    _,_,text=details(script('(count >= 3 and GetPlayerState(Player(0),PLAYER_STATE_RESOURCE_GOLD) >= 500) or IsUnitDeadBJ(hero)'))
    assert '任一' in text and '全部' in text
    assert '玩家 1的金币' in text and '不少于 500' in text

def test_unknown_function_and_missing_failure_are_honestly_explained():
    text=script('MysteryPredicate()').replace('call QuestSetFailed(q,true)','call DisplayTextToPlayer(Player(0),0,0,"lost")')
    _,_,rendered=details(text)
    assert '尚无法解释' in rendered and 'MysteryPredicate' in rendered
    assert '未找到明确的任务失败条件' in rendered
    assert '这不表示' in rendered

def test_alternative_completion_paths_and_map_defeat_are_not_conflated():
    text=script().replace('call QuestSetFailed(q,true)','call CustomDefeatBJ(Player(0),"英雄已阵亡")')
    _,r,rendered=details(text)
    assert '未找到明确的任务失败条件' in rendered
    assert len(r.outcomes)==1 and not r.quests[0].failed

def test_presentation_strips_warcraft_format_codes_but_retains_actual_text():
    _,_,text=details(script().replace('收集三块碎片，英雄必须存活。','|cffffcc00收集三块碎片|r|n英雄必须存活。'))
    assert '|cff' not in text and '|r' not in text and '|n' not in text
    assert '收集三块碎片\n英雄必须存活。' in text

def test_group_death_and_duplicate_and_guards_read_as_one_set_of_requirements():
    text=script('IsUnitGroupDeadBJ(group1) and (count>=3 and count>=3)').replace('integer count=0','integer count=0\ngroup group1=null')
    _,_,rendered=details(text)
    assert '全部单位已死亡' in rendered
    assert rendered.count('不少于 3')==1

def test_rendering_uses_worker_metadata_instead_of_reparsing_whole_map(monkeypatch):
    import war3_quest_text as module
    report=analyze(script())
    original=module.parse_jass
    def condition_only(text,*args,**kwargs):
        assert text.startswith('function R24Condition'), 'Map parsing must stay off the Tk render thread'
        return original(text,*args,**kwargs)
    monkeypatch.setattr(module,'parse_jass',condition_only)
    assert '计数“count”' in module.QuestText(report).quest(report.quests[0])

def test_distinct_unknown_predicate_arguments_are_not_collapsed_into_one_rule():
    _,_,rendered=details(script('MysteryPredicate(1) and MysteryPredicate(2)'))
    assert rendered.count('尚无法解释的脚本条件（MysteryPredicate)')==2

def test_quest_handle_prefix_does_not_change_which_quest_is_named():
    from war3_quest_text import QuestText
    report=analyze(script())
    q=report.quests[0]
    report=replace(report,quests=(replace(q,key='Q:main:10:2',title='甲'),replace(q,key='Q:main:10:20',title='乙')))
    reader=QuestText(report)
    assert '“乙”' in reader.expr(reader.parse('IsQuestCompleted(Q:main:10:20)'))

def test_registered_paths_with_one_shared_counter_condition_are_grouped():
    code=script('GetTriggerEvalCount(GetTriggeringTrigger())==13')
    code=code.replace('call TriggerRegisterAnyUnitEventBJ(t,EVENT_PLAYER_UNIT_DEATH)',
        'call TriggerRegisterUnitEvent(t,hero,EVENT_UNIT_DEATH)\ncall TriggerRegisterUnitEvent(t,other,EVENT_UNIT_DEATH)')
    _,_,rendered=details(code)
    assert '条件检查次数' in rendered and '2 条' in rendered
    assert rendered.count('等于 13')==1

def test_unit_type_condition_is_explained_as_a_type_flag_not_a_guessed_story_action():
    _,_,rendered=details(script('IsUnitType(GetDyingUnit(),UNIT_TYPE_SAPPER)'))
    assert '工兵' in rendered and '类型标记' in rendered

@pytest.mark.parametrize('kind',[320,321,322])
def test_deleted_task_operations_cannot_be_submitted(kind):
    from war3_reforged_trainer import War3Trainer
    trainer=object.__new__(War3Trainer)
    with pytest.raises(RuntimeError,match='已移除'):
        trainer._pack_native_helper_command(0,((kind,0,0,0,0),))
