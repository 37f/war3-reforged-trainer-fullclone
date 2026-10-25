"""R22 semantic contracts: real JASS inputs, independently derived expectations."""
from dataclasses import replace
import hashlib
import time
import pytest

from war3_current_map_script import ScriptSnapshot
from war3_quest_analysis import analyze_quests, AnalysisUnavailable


def snapshot(text,strings=b''):
    script=text.encode('utf-8')
    return ScriptSnapshot('test',1,'owned.w3n::chapter.w3x::war3map.j','jass',script,strings,
        hashlib.sha256(script).hexdigest(),hashlib.sha256(strings).hexdigest(),time.monotonic(),('owned',),())


def analyze(text,strings=b''):
    return analyze_quests(snapshot(text,strings))


def paths(rule):
    return '\n'.join(p.guard+' '+' '.join(p.events)+' '+' '.join(p.callers) for p in rule.paths)


def test_native_quest_alias_wts_and_false_resets_do_not_complete_quest():
    r=analyze('''globals
quest q = null
quest alias = null
endglobals
function main takes nothing returns nothing
 set q = CreateQuest()
 set alias = q
 call QuestSetTitle(alias, "TRIGSTR_001")
 call QuestSetDescription(q, "description // QuestSetFailed(q,true)")
 call QuestSetRequired(q, true)
 call QuestSetCompleted(alias, false)
 call QuestSetFailed(q, false)
endfunction
''',b'STRING 1\n{\nFind the relic\n}\n')
    assert len(r.quests)==1
    q=r.quests[0]
    assert q.title=='Find the relic' and q.required is True
    assert not q.completed and not q.failed and len(q.resets)==2
    assert {'q','alias'}<=set(q.aliases)


def test_bj_last_created_array_items_and_exact_counter_condition():
    r=analyze('''globals
quest q = null
questitem array items
integer recruits = 0
endglobals
function Ready takes nothing returns boolean
 if not (recruits == 3) then
  return false
 endif
 return true
endfunction
function Finish takes nothing returns nothing
 if Ready() then
  call QuestSetCompletedBJ(q,true)
 endif
endfunction
function main takes nothing returns nothing
 call CreateQuestBJ(bj_QUESTTYPE_OPT_UNDISCOVERED,"Secret","Hidden","icon")
 set q = GetLastCreatedQuestBJ()
 call CreateQuestItemBJ(q,"Gather three")
 set items[1] = GetLastCreatedQuestItemBJ()
 if IsQuestItemCompleted(items[1]) then
  set recruits = recruits + 1
 endif
 call Finish()
endfunction
''')
    q=r.quests[0]
    assert (q.title,q.required,q.discovered)==('Secret',False,False)
    assert len(q.items)==1 and q.items[0].description=='Gather three'
    rule=q.completed[0]
    assert 'recruits == 3' in paths(rule) and 'recruits >= 3' not in paths(rule)
    evidence='\n'.join(e.source for p in rule.paths for e in p.variables)
    assert 'recruits = 0' in evidence and 'recruits = recruits + 1' in evidence
    assert any('IsQuestItemCompleted' in e.source for p in rule.paths for e in p.evidence)


def test_region_event_and_registered_early_return_predicate_are_combined():
    r=analyze('''globals
quest q = null
trigger t = null
endglobals
function Gate takes nothing returns boolean
 if not (IsUnitEnemy(GetTriggerUnit(),Player(1)) == true) then
  return false
 endif
 return GetPlayerState(Player(1),PLAYER_STATE_RESOURCE_GOLD) >= 4 or IsUnitDeadBJ(hero)
endfunction
function Action takes nothing returns nothing
 call QuestSetCompleted(q,true)
endfunction
function main takes nothing returns nothing
 set q = CreateQuest()
 set t = CreateTrigger()
 call TriggerRegisterEnterRectSimple(t,rect)
 call TriggerAddCondition(t,Condition(function Gate))
 call TriggerAddAction(t,function Action)
endfunction
''')
    p=r.quests[0].completed[0].paths[0]
    assert 'EnterRect' in ' '.join(p.events) and 'rect' in ' '.join(p.events)
    assert 'IsUnitEnemy' in p.guard and '>= 4' in p.guard and ' or ' in p.guard
    assert 'Gate' in ' '.join(p.callers)
    assert any(e.function=='Gate' and e.line>0 for e in p.evidence)


def test_direct_death_losses_after_delay_are_not_quest_failures():
    r=analyze('''globals
trigger a = null
trigger b = null
endglobals
function IsDead takes nothing returns boolean
 return IsUnitDeadBJ(hero)
endfunction
function LoseA takes nothing returns nothing
 call TriggerSleepAction(2.0)
 call CustomDefeatBJ(Player(0),"Defeat!")
endfunction
function LoseB takes nothing returns nothing
 call CustomDefeatBJ(Player(0),"Defeat!")
endfunction
function main takes nothing returns nothing
 set a=CreateTrigger()
 set b=CreateTrigger()
 call TriggerRegisterAnyUnitEventBJ(a,EVENT_PLAYER_UNIT_DEATH)
 call TriggerAddCondition(a,Condition(function IsDead))
 call TriggerAddAction(a,function LoseA)
 call TriggerRegisterUnitEvent(b,important,EVENT_UNIT_DEATH)
 call TriggerAddAction(b,function LoseB)
endfunction
''')
    assert not r.quests and len(r.outcomes)==2
    assert all(rule.kind=='defeat' for rule in r.outcomes)
    assert 'hero' in paths(r.outcomes[0]) and 'DEATH' in paths(r.outcomes[0])
    assert 'important' in paths(r.outcomes[1])
    assert any('TriggerSleepAction(2.0)' in e.source for p in r.outcomes[0].paths for e in p.evidence)


@pytest.mark.parametrize('mode,expect_gate', [('ConditionalTriggerExecute',True),('TriggerExecute',False)])
def test_manual_trigger_victory_traces_caller_and_respects_execution_mode(mode,expect_gate):
    r=analyze('''globals
trigger t = null
endglobals
function Gate takes nothing returns boolean
 return count >= 4
endfunction
function Victory takes nothing returns nothing
 call CustomVictoryBJ(Player(0),true,true)
endfunction
function main takes nothing returns nothing
 set t=CreateTrigger()
 call TriggerAddCondition(t,Condition(function Gate))
 call TriggerAddAction(t,function Victory)
 if difficulty == 2 then
  call MODE(t)
 endif
endfunction
'''.replace('MODE',mode))
    rule=r.outcomes[0]
    assert rule.kind=='victory' and 'difficulty == 2' in paths(rule)
    assert ('count >= 4' in paths(rule)) is expect_gate
    assert any('main' in p.callers for p in rule.paths)


def test_multiple_callers_remain_alternatives_and_disabled_trigger_is_visible():
    r=analyze('''globals
trigger t=null
endglobals
function Win takes nothing returns nothing
 call CustomVictoryBJ(Player(0),true,true)
endfunction
function First takes nothing returns nothing
 if a == 1 then
  call TriggerExecute(t)
 endif
endfunction
function Second takes nothing returns nothing
 if b == 2 then
  call TriggerExecute(t)
 endif
endfunction
function main takes nothing returns nothing
 set t=CreateTrigger()
 call DisableTrigger(t)
 call TriggerAddAction(t,function Win)
 call First()
 call Second()
endfunction
''')
    rule=r.outcomes[0]
    assert len(rule.paths)==2
    assert any('a == 1' in p.guard and 'b == 2' not in p.guard for p in rule.paths)
    assert any('b == 2' in p.guard and 'a == 1' not in p.guard for p in rule.paths)
    assert any('DisableTrigger' in e.source for p in rule.paths for e in p.evidence)


def test_shadowed_bj_wrapper_is_followed_without_fabricated_quest_or_loss():
    r=analyze('''function CustomDefeatBJ takes player p, string message returns nothing
 call DisplayTextToPlayer(p,0,0,message)
endfunction
function CreateQuestBJ takes integer kind,string title,string desc,string icon returns quest
 return null
endfunction
function main takes nothing returns nothing
 call CustomDefeatBJ(Player(0),"fake")
 call CreateQuestBJ(0,"fake",""," ")
endfunction
''')
    assert not r.quests and not r.outcomes


def test_user_wrapper_substitutes_actual_quest_and_numeric_arguments():
    r=analyze('''globals
quest q=null
endglobals
function Complete takes quest target, integer n returns nothing
 if n >= 4 then
  call QuestSetCompleted(target,true)
 endif
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 call Complete(q,kills)
endfunction
''')
    assert len(r.quests[0].completed)==1
    assert 'kills >= 4' in paths(r.quests[0].completed[0])


def test_ambiguous_alias_goes_to_unassociated_instead_of_first_task():
    r=analyze('''globals
quest q=null
endglobals
function main takes nothing returns nothing
 if flag then
  set q=CreateQuest()
 else
  set q=CreateQuest()
 endif
 call QuestSetCompleted(q,true)
endfunction
''')
    assert len(r.quests)==2 and not any(q.completed for q in r.quests)
    assert any(rule.kind=='completed' for rule in r.unassociated)
    assert r.partial


def test_dynamic_boolean_reset_keeps_only_true_guard_and_marks_dynamic():
    r=analyze('''globals
quest q=null
endglobals
function main takes nothing returns nothing
 set q=CreateQuest()
 call QuestSetFailed(q,flag)
endfunction
''')
    q=r.quests[0]
    assert 'flag' in paths(q.failed[0]) and 'not flag' in paths(q.resets[0])


def test_text_comments_and_bad_ending_names_never_fabricate_outcomes():
    r=analyze('''function DefeatBadEnding takes nothing returns nothing
 // call CustomDefeatBJ(Player(0),"bad")
 call DisplayTextToPlayer(Player(0),0,0,"CustomVictoryBJ(Player(0),true,true)")
 call EndGame(true)
endfunction
function main takes nothing returns nothing
 call DefeatBadEnding()
endfunction
''')
    assert not r.outcomes and not r.quests
    assert any('标准任务' in i for i in r.issues)


def test_remove_player_result_is_only_known_victory_or_defeat():
    r=analyze('''function main takes nothing returns nothing
 call RemovePlayer(Player(0),PLAYER_GAME_RESULT_VICTORY)
 call RemovePlayer(Player(1),PLAYER_GAME_RESULT_DEFEAT)
 call RemovePlayer(Player(2),PLAYER_GAME_RESULT_NEUTRAL)
 call RemovePlayer(Player(3),dynamicResult)
endfunction
''')
    assert [o.kind for o in r.outcomes]==['victory','defeat','unknown-result']
    assert r.partial


def test_dynamic_execute_recursion_missing_predicate_and_loops_are_explicit_partial():
    r=analyze('''globals
quest q=null
endglobals
function Loop takes nothing returns nothing
 if MissingPredicate() then
  call QuestSetCompleted(q,true)
 endif
 call Loop()
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 call ExecuteFunc(dynamicName)
 loop
  exitwhen i > 5
  call Loop()
 endloop
endfunction
''')
    assert r.partial
    detail=' '.join(r.issues)+' '.join(i for q in r.quests for ru in q.completed for p in ru.paths for i in p.issues)
    assert 'ExecuteFunc' in detail and '循环' in detail and '递归' in detail and 'MissingPredicate' in detail


def test_orphan_action_is_not_reported_as_unconditional_reachable():
    r=analyze('''function Orphan takes nothing returns nothing
 call CustomVictoryBJ(Player(0),true,true)
endfunction
function main takes nothing returns nothing
endfunction
''')
    rule=r.outcomes[0]
    assert rule.paths and any('入口' in i for p in rule.paths for i in p.issues)
    assert r.partial


@pytest.mark.parametrize('language', ['lua','encrypted'])
def test_unsupported_language_cannot_be_empty_success(language):
    with pytest.raises(AnalysisUnavailable):
        analyze_quests(replace(snapshot(''),language=language))


def test_cancel_decode_and_syntax_errors_are_explicit():
    with pytest.raises(AnalysisUnavailable,match='取消'):
        analyze_quests(snapshot(''),cancelled=lambda:True)
    with pytest.raises(AnalysisUnavailable):
        analyze_quests(replace(snapshot(''),script=b'\xff'))
    with pytest.raises(AnalysisUnavailable):analyze('function main')


def test_path_and_task_budgets_mark_partial_instead_of_complete(monkeypatch):
    import war3_quest_analysis as module
    monkeypatch.setattr(module,'MAX_TASKS',1)
    r=analyze('''function main takes nothing returns nothing
 call CreateQuestBJ(0,"one",""," ")
 call CreateQuestBJ(0,"two",""," ")
endfunction
''')
    assert len(r.quests)==1 and r.partial and any('上限' in i for i in r.issues)


def test_dynamic_array_alias_is_not_a_unique_task_handle():
    r=analyze('''globals
quest array tasks
endglobals
function main takes nothing returns nothing
 set tasks[i]=CreateQuest()
 call QuestSetCompleted(tasks[i],true)
endfunction
''')
    assert not r.quests[0].completed and r.unassociated and r.partial


def test_counter_assignment_predicate_is_expanded_to_item_evidence():
    r=analyze('''globals
quest q=null
integer count=0
questitem item=null
endglobals
function Done takes nothing returns boolean
 return IsQuestItemCompleted(item)
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 if Done() then
  set count=count+1
 endif
 if count == 1 then
  call QuestSetCompleted(q,true)
 endif
endfunction
''')
    proof=' '.join(e.source for p in r.quests[0].completed[0].paths for e in p.variables)
    assert 'IsQuestItemCompleted(item)' in proof


def test_shadowed_quest_category_constant_is_not_standard_category():
    r=analyze('''globals
integer bj_QUESTTYPE_REQ_DISCOVERED=3
endglobals
function main takes nothing returns nothing
 call CreateQuestBJ(bj_QUESTTYPE_REQ_DISCOVERED,"title",""," ")
endfunction
''')
    assert r.quests[0].required is None and r.partial


def test_multiple_instances_of_creation_wrapper_mark_definition_instance_ambiguity():
    r=analyze('''globals
quest a=null
quest b=null
endglobals
function Make takes nothing returns quest
 return CreateQuest()
endfunction
function main takes nothing returns nothing
 set a=Make()
 set b=Make()
 call QuestSetCompleted(a,true)
endfunction
''')
    assert r.partial and any('实例' in i for i in r.issues)


def test_conditional_action_registration_is_kept_as_an_additional_gate():
    r=analyze('''globals
trigger t=null
endglobals
function Win takes nothing returns nothing
 call CustomVictoryBJ(Player(0),true,true)
endfunction
function main takes nothing returns nothing
 set t=CreateTrigger()
 call TriggerRegisterTimerEvent(t,1,false)
 if mode == 3 then
  call TriggerAddAction(t,function Win)
 endif
endfunction
''')
    assert 'mode == 3' in paths(r.outcomes[0])


def test_event_dispatch_requires_enabled_trigger_and_shows_static_toggle_evidence():
    r=analyze('''globals
trigger t=null
endglobals
function Win takes nothing returns nothing
 call CustomVictoryBJ(Player(0),true,true)
endfunction
function main takes nothing returns nothing
 set t=CreateTrigger()
 call DisableTrigger(t)
 call TriggerRegisterTimerEvent(t,1,false)
 call TriggerAddAction(t,function Win)
endfunction
''')
    assert any('启用' in i for p in r.outcomes[0].paths for i in p.issues)


def test_path_depth_budget_does_not_report_complete(monkeypatch):
    import war3_quest_analysis as module
    monkeypatch.setattr(module,'MAX_DEPTH',2)
    r=analyze('''function Last takes nothing returns nothing
 call CustomVictoryBJ(Player(0),true,true)
endfunction
function Middle takes nothing returns nothing
 call Last()
endfunction
function Outer takes nothing returns nothing
 call Middle()
endfunction
function main takes nothing returns nothing
 call Outer()
endfunction
''')
    assert r.partial and any('深度' in i for p in r.outcomes[0].paths for i in p.issues)


def test_many_sequential_independent_branches_do_not_blow_up_formulas():
    text='function main takes nothing returns nothing\n'
    text+=''.join(f'if flag{i} then\ncall DoNothing()\nendif\n' for i in range(100))
    text+='call CustomVictoryBJ(Player(0),true,true)\nendfunction\n'
    r=analyze(text)
    assert len(r.outcomes)==1 and len(paths(r.outcomes[0]))<200


def test_timer_callback_is_traced_to_timer_start_not_orphaned():
    r=analyze('''function Timeout takes nothing returns nothing
 call CustomDefeatBJ(Player(0),"Time up")
endfunction
function main takes nothing returns nothing
 call TimerStart(clock,60.0,false,function Timeout)
endfunction
''')
    assert 'TimerStart' in paths(r.outcomes[0]) and '60.0' in paths(r.outcomes[0])
    assert not any('入口' in i for p in r.outcomes[0].paths for i in p.issues)


def test_conflicting_task_texts_and_properties_are_preserved_as_uncertain():
    r=analyze('''globals
quest q=null
endglobals
function main takes nothing returns nothing
 set q=CreateQuest()
 if flag then
  call QuestSetTitle(q,"First")
  call QuestSetRequired(q,true)
 else
  call QuestSetTitle(q,"Second")
  call QuestSetRequired(q,false)
 endif
endfunction
''')
    assert 'First' in r.quests[0].title and 'Second' in r.quests[0].title
    assert r.quests[0].required is None and r.partial


def test_goal_path_count_limit_marks_omission(monkeypatch):
    import war3_quest_analysis as module
    monkeypatch.setattr(module,'MAX_PATHS',2)
    r=analyze('''function Win takes nothing returns nothing
 call CustomVictoryBJ(Player(0),true,true)
endfunction
function main takes nothing returns nothing
 if a then
  call Win()
 endif
 if b then
  call Win()
 endif
 if c then
  call Win()
 endif
endfunction
''')
    assert len(r.outcomes[0].paths)<=2 and r.partial
    assert any('上限' in i for i in r.issues)


def test_timeout_is_not_silent_empty_success(monkeypatch):
    import war3_quest_analysis as module
    monkeypatch.setattr(module,'MAX_SECONDS',-1)
    with pytest.raises(AnalysisUnavailable,match='时间上限'):analyze('')


def test_deep_left_associative_expression_is_bounded_without_python_recursion_error():
    text='function main takes nothing returns nothing\nif '+(' + '.join(['n']*300))+' > 0 then\n'
    text+='call CustomVictoryBJ(Player(0),true,true)\nendif\nendfunction\n'
    with pytest.raises(AnalysisUnavailable,match='深度上限'):analyze(text)


def test_unassigned_dynamic_counter_is_visible_as_unknown_static_source():
    r=analyze('''function main takes nothing returns nothing
 if unseenCounter >= 8 then
  call CustomVictoryBJ(Player(0),true,true)
 endif
endfunction
''')
    assert any('unseenCounter' in i for p in r.outcomes[0].paths for i in p.issues)


@pytest.mark.parametrize('mode',['checkConditions','true','false'])
def test_review_dynamic_trigger_execute_bj_preserves_condition_bypass(mode):
    r=analyze('''globals
quest q=null
trigger t=null
boolean checkConditions=false
endglobals
function Gate takes nothing returns boolean
 return false
endfunction
function Finish takes nothing returns nothing
 call QuestSetCompleted(q,true)
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 set t=CreateTrigger()
 call TriggerAddCondition(t,Condition(function Gate))
 call TriggerAddAction(t,function Finish)
 call TriggerExecuteBJ(t,MODE)
endfunction
'''.replace('MODE',mode))
    if mode=='true':assert not r.quests[0].completed
    else:
        rule=r.quests[0].completed[0]
        assert rule.paths
        if mode=='checkConditions':assert 'not checkConditions' in paths(rule)


def test_review_unreachable_action_registration_is_not_certain_timer_path():
    r=analyze('''globals
quest q=null
trigger t=null
endglobals
function Finish takes nothing returns nothing
 call QuestSetCompleted(q,true)
endfunction
function NeverCalled takes nothing returns nothing
 call TriggerAddAction(t,function Finish)
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 set t=CreateTrigger()
 call TriggerRegisterTimerEvent(t,1.0,false)
endfunction
''')
    assert r.partial
    assert all(p.issues for p in r.quests[0].completed[0].paths)


def test_review_conditional_condition_registration_does_not_erase_candidate_outcome():
    r=analyze('''globals
quest q=null
trigger t=null
boolean mode=false
endglobals
function Gate takes nothing returns boolean
 return false
endfunction
function Finish takes nothing returns nothing
 call QuestSetCompleted(q,true)
endfunction
function Register takes nothing returns nothing
 call TriggerAddCondition(t,Condition(function Gate))
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 set t=CreateTrigger()
 if mode then
  call Register()
 endif
 call TriggerAddAction(t,function Finish)
 call ConditionalTriggerExecute(t)
endfunction
''')
    assert r.quests[0].completed and r.partial
    assert any('注册' in i for p in r.quests[0].completed[0].paths for i in p.issues)


def test_review_trigger_reallocation_does_not_join_old_timer_to_new_action():
    r=analyze('''globals
quest q=null
trigger t=null
endglobals
function Finish takes nothing returns nothing
 call QuestSetCompleted(q,true)
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 set t=CreateTrigger()
 call TriggerRegisterTimerEvent(t,1.0,false)
 set t=CreateTrigger()
 call TriggerAddAction(t,function Finish)
endfunction
''')
    assert r.partial
    assert all(not p.events and p.issues for p in r.quests[0].completed[0].paths)


def test_review_cross_function_ambiguous_trigger_alias_has_no_certain_event_join():
    r=analyze('''globals
quest q=null
trigger t=null
endglobals
function Finish takes nothing returns nothing
 call QuestSetCompleted(q,true)
endfunction
function RegisterTimer takes nothing returns nothing
 call TriggerRegisterTimerEvent(t,1.0,false)
endfunction
function RegisterAction takes nothing returns nothing
 call TriggerAddAction(t,function Finish)
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 if flag then
  set t=CreateTrigger()
 else
  set t=CreateTrigger()
 endif
 call RegisterTimer()
 call RegisterAction()
endfunction
''')
    assert r.partial and all(p.issues for p in r.quests[0].completed[0].paths)


@pytest.mark.parametrize('left,operator,expected',[('false','and',False),('true','or',False),('flag','and',True),('flag','or',True)])
def test_review_boolean_short_circuit_guards_rhs_side_effect_calls(left,operator,expected):
    r=analyze('''globals
quest q=null
endglobals
function Complete takes nothing returns boolean
 call QuestSetCompleted(q,true)
 return true
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 if LEFT OP Complete() then
  call DoNothing()
 endif
endfunction
'''.replace('LEFT',left).replace(' OP ',' '+operator+' '))
    q=r.quests[0]
    assert bool(q.completed) is expected
    if expected:
        assert ('not flag' if operator=='or' else 'flag') in paths(q.completed[0])


def test_review_native_creation_does_not_update_bj_last_quest_or_item():
    r=analyze('''globals
quest a=null
quest b=null
questitem first=null
questitem second=null
endglobals
function main takes nothing returns nothing
 set a=CreateQuestBJ(0,"A",""," ")
 set first=CreateQuestItemBJ(a,"First")
 set b=CreateQuest()
 set second=QuestCreateItem(a)
 call QuestSetCompleted(GetLastCreatedQuestBJ(),true)
 call QuestItemSetCompleted(GetLastCreatedQuestItemBJ(),true)
endfunction
''')
    a=next(q for q in r.quests if q.title=='A');b=next(q for q in r.quests if q.key!=a.key)
    assert a.completed and not b.completed
    assert a.items[0].completed and not a.items[1].completed


def test_review_repeated_trigger_constructor_wrapper_does_not_share_instance():
    r=analyze('''globals
quest q=null
trigger t=null
endglobals
function Make takes nothing returns trigger
 return CreateTrigger()
endfunction
function Finish takes nothing returns nothing
 call QuestSetCompleted(q,true)
endfunction
function main takes nothing returns nothing
 set q=CreateQuest()
 set t=Make()
 call TriggerRegisterTimerEvent(t,1.0,false)
 set t=Make()
 call TriggerAddAction(t,function Finish)
endfunction
''')
    assert r.partial and all(p.issues for p in r.quests[0].completed[0].paths)


def test_review_bj_last_state_is_not_assumed_unchanged_across_map_calls():
    r=analyze('''globals
quest a=null
quest b=null
endglobals
function MakeB takes nothing returns nothing
 set b=CreateQuestBJ(0,"B",""," ")
endfunction
function main takes nothing returns nothing
 set a=CreateQuestBJ(0,"A",""," ")
 call MakeB()
 call QuestSetCompleted(GetLastCreatedQuestBJ(),true)
endfunction
''')
    a=next(q for q in r.quests if q.title=='A')
    assert not a.completed
    assert any(q.completed for q in r.quests if q.title=='B') or (r.unassociated and r.partial)



