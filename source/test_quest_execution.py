"""Conservative R23 completion-plan qualification tests."""
import hashlib

from war3_current_map_script import ScriptSnapshot
from war3_quest_analysis import analyze_quests


def _report(script):
    payload=script.encode('utf8')
    snapshot=ScriptSnapshot(
        identity=('test-process',1),session_token=7,origin='fixture.w3x::war3map.j',
        language='jass',script=payload,strings_data=b'',
        script_sha256=hashlib.sha256(payload).hexdigest(),
        strings_sha256=hashlib.sha256(b'').hexdigest(),validated_at=0,
        provenance=('fixture',),stamp=('fixture',))
    return analyze_quests(snapshot)


def _script(finish='call QuestSetCompletedBJ(udg_QUEST,true)',extra=''):
    return f'''globals
quest udg_QUEST = null
trigger gg_trg_Finish = null
endglobals
function main takes nothing returns nothing
 call CreateTasks()
 call InitCustomTriggers()
endfunction
function InitCustomTriggers takes nothing returns nothing
 call InitTrig_Finish()
endfunction
function InitTrig_Finish takes nothing returns nothing
 set gg_trg_Finish = CreateTrigger()
 call TriggerRegisterAnyUnitEventBJ(gg_trg_Finish, PLAYER_EVENT_PLAYER_UNIT_PICKUP_ITEM)
 call TriggerAddAction(gg_trg_Finish, function FinishAction)
endfunction
function CreateTasks takes nothing returns nothing
 set udg_QUEST = CreateQuestBJ(bj_QUESTTYPE_REQ_DISCOVERED)
 call QuestSetTitleBJ(udg_QUEST, "Find the relic")
endfunction
function FinishAction takes nothing returns nothing
 {extra}
 {finish}
endfunction
'''


def _quest(report):
    assert len(report.quests)==1
    return report.quests[0]


def test_simple_original_completion_trigger_qualifies_and_is_bound_to_exact_snapshot():
    from war3_quest_execution import build_completion_plan
    report=_report(_script())
    quest=_quest(report)

    plan=build_completion_plan(report,quest.key)

    assert plan.eligible
    assert plan.quest_key==quest.key
    assert plan.quest_alias=='udg_QUEST'
    assert plan.entry_trigger=='gg_trg_Finish'
    assert plan.entry_function=='FinishAction'
    assert plan.snapshot_identity==report.snapshot.identity
    assert plan.snapshot_token==report.snapshot.session_token
    assert plan.script_sha256==report.snapshot.script_sha256


def test_reward_in_outer_action_is_included_in_original_flow_evidence():
    from war3_quest_execution import build_completion_plan
    script=_script(extra='call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 100)')
    report=_report(script)

    plan=build_completion_plan(report,_quest(report).key)

    assert plan.eligible
    assert 'SetPlayerState' in plan.recognized_calls
    assert plan.chain_functions==('FinishAction',)


def test_unknown_action_local_condition_rejects_full_flow():
    from war3_quest_execution import build_completion_plan
    report=_report(_script(extra='if udg_Kills >= 10 then\n call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 100)\nendif'))

    plan=build_completion_plan(report,_quest(report).key)

    assert not plan.eligible
    assert any('分支条件' in reason for reason in plan.reasons)


def test_event_response_dependent_action_is_rejected():
    from war3_quest_execution import build_completion_plan
    report=_report(_script(extra='call KillUnit(GetTriggerUnit())'))

    plan=build_completion_plan(report,_quest(report).key)

    assert not plan.eligible
    assert any('事件响应' in reason for reason in plan.reasons)


def test_dynamic_execute_func_in_completion_action_is_rejected():
    from war3_quest_execution import build_completion_plan
    report=_report(_script(finish='call ExecuteFunc(udg_FinishName)'))

    plan=build_completion_plan(report,_quest(report).key)

    assert not plan.eligible
    assert any('动态' in reason for reason in plan.reasons)


def test_missing_completion_setter_is_not_executable():
    from war3_quest_execution import build_completion_plan
    report=_report(_script(finish='call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 100)'))

    plan=build_completion_plan(report,_quest(report).key)

    assert not plan.eligible
    assert any('完成状态' in reason for reason in plan.reasons)


def test_two_event_roots_reaching_same_task_are_ambiguous():
    from war3_quest_execution import build_completion_plan
    script=_script()+'''\nfunction InitTrig_Alternate takes nothing returns nothing
 set gg_trg_Finish = CreateTrigger()
 call TriggerRegisterAnyUnitEventBJ(gg_trg_Finish, PLAYER_EVENT_PLAYER_UNIT_DEATH)
 call TriggerAddAction(gg_trg_Finish, function FinishAction)
endfunction
'''
    report=_report(script)

    plan=build_completion_plan(report,_quest(report).key)

    assert not plan.eligible
    assert any('多个' in reason or '不唯一' in reason for reason in plan.reasons)


def test_same_title_quests_remain_distinct_by_script_key():
    from war3_quest_execution import build_completion_plan
    script=_script()+'''\nglobals
 quest udg_OTHER = null
endglobals
function CreateOtherQuest takes nothing returns nothing
 set udg_OTHER = CreateQuestBJ(bj_QUESTTYPE_REQ_DISCOVERED)
 call QuestSetTitleBJ(udg_OTHER, "Find the relic")
endfunction
'''
    report=_report(script)

    assert len(report.quests)==2
    plans=[build_completion_plan(report,q.key) for q in report.quests]

    assert len({plan.quest_key for plan in plans})==2
    assert sum(plan.eligible for plan in plans)==1


def test_setter_helper_is_not_selected_instead_of_reward_owning_caller():
    from war3_quest_execution import build_completion_plan
    script=_script(finish='call FinishInner()',extra='call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 100)')+'''
function FinishInner takes nothing returns nothing
 call QuestSetCompletedBJ(udg_QUEST,true)
endfunction
'''
    report=_report(script)
    plan=build_completion_plan(report,_quest(report).key)
    assert plan.eligible and plan.entry_function=='FinishAction'
    assert plan.chain_functions==('FinishAction','FinishInner')
    assert 'SetPlayerState' in plan.recognized_calls


def test_unknown_wrapper_cannot_hide_event_context_or_omitted_rewards():
    from war3_quest_execution import build_completion_plan
    report=_report(_script(extra='call MysteryReward(udg_QUEST)'))
    plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('MysteryReward' in reason for reason in plan.reasons)


def test_wrong_action_signature_is_rejected():
    from war3_quest_execution import build_completion_plan
    report=_report(_script().replace('function FinishAction takes nothing returns nothing',
        'function FinishAction takes integer value returns nothing'))
    plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('签名' in reason for reason in plan.reasons)


def test_snapshot_hash_tampering_is_rejected():
    from dataclasses import replace
    from war3_quest_execution import build_completion_plan
    report=_report(_script())
    report=replace(report,snapshot=replace(report.snapshot,script=report.snapshot.script+b'// changed\n'))
    plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('哈希' in reason for reason in plan.reasons)


def test_queued_inner_trigger_keeps_original_outer_reward_flow():
    from war3_quest_execution import build_completion_plan
    script=_script(finish='call QueuedTriggerAddBJ(gg_trg_Inner,true)',
        extra='call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 100)')
    script=script.replace('trigger gg_trg_Finish = null','trigger gg_trg_Finish = null\ntrigger gg_trg_Inner = null')
    script=script.replace('call InitTrig_Finish()','call InitTrig_Finish()\n call InitInner()')+'''
function InitInner takes nothing returns nothing
 set gg_trg_Inner = CreateTrigger()
 call TriggerAddAction(gg_trg_Inner,function InnerAction)
endfunction
function InnerAction takes nothing returns nothing
 call QuestSetCompletedBJ(udg_QUEST,true)
endfunction
'''
    report=_report(script);plan=build_completion_plan(report,_quest(report).key)
    assert plan.eligible and plan.entry_trigger=='gg_trg_Finish'
    assert plan.chain_functions==('FinishAction','InnerAction')
    assert dict(plan.trigger_bindings)=={'gg_trg_Finish':('FinishAction',),'gg_trg_Inner':('InnerAction',)}


def test_one_action_completing_two_tasks_is_not_a_single_task_entry():
    from war3_quest_execution import build_completion_plan
    script=_script(extra='call QuestSetCompletedBJ(udg_OTHER,true)')
    script=script.replace('quest udg_QUEST = null','quest udg_QUEST = null\nquest udg_OTHER = null')
    script=script.replace('call CreateTasks()','call CreateTasks()\n call CreateOther()')+'''
function CreateOther takes nothing returns nothing
 set udg_OTHER = CreateQuestBJ(bj_QUESTTYPE_REQ_DISCOVERED)
endfunction
'''
    report=_report(script)
    quest=next(q for q in report.quests if 'udg_QUEST' in q.aliases)
    plan=build_completion_plan(report,quest.key)
    assert not plan.eligible
    assert any('其他任务' in reason for reason in plan.reasons)


def test_research_event_response_cannot_be_synthesized_by_trigger_execute():
    from war3_quest_execution import build_completion_plan
    report=_report(_script(extra='call SetPlayerTechResearched(Player(0),GetResearched(),1)'))
    plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('事件响应' in reason for reason in plan.reasons)


def test_declaring_an_unknown_native_does_not_make_its_context_known():
    from war3_quest_execution import build_completion_plan
    report=_report('native MysteryReward takes quest value returns nothing\n'+_script(extra='call MysteryReward(udg_QUEST)'))
    plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('MysteryReward' in reason for reason in plan.reasons)


def test_conditional_action_registration_does_not_prove_current_action_list():
    from war3_quest_execution import build_completion_plan
    script=_script().replace('call TriggerAddAction(gg_trg_Finish, function FinishAction)',
        'if udg_Register then\n call TriggerAddAction(gg_trg_Finish, function FinishAction)\n endif')
    report=_report(script);plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('注册' in reason for reason in plan.reasons)


def test_trigger_alias_reassignment_is_not_a_stable_original_instance():
    from war3_quest_execution import build_completion_plan
    script=_script()+'''
function ResetEntry takes nothing returns nothing
 set gg_trg_Finish = null
endfunction
'''
    report=_report(script);plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('赋值' in reason for reason in plan.reasons)


def test_later_action_list_mutation_is_not_silently_ignored():
    from war3_quest_execution import build_completion_plan
    script=_script()+'''
function RemoveEntryActions takes nothing returns nothing
 call TriggerClearActions(gg_trg_Finish)
endfunction
'''
    report=_report(script);plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('动作列表' in reason for reason in plan.reasons)


def test_two_distinct_event_triggers_with_same_completion_are_not_arbitrarily_chosen():
    from war3_quest_execution import build_completion_plan
    script=_script().replace('trigger gg_trg_Finish = null',
        'trigger gg_trg_Finish = null\ntrigger gg_trg_Other = null')
    script=script.replace('call InitTrig_Finish()','call InitTrig_Finish()\n call InitOther()')+'''
function InitOther takes nothing returns nothing
 set gg_trg_Other = CreateTrigger()
 call TriggerRegisterAnyUnitEventBJ(gg_trg_Other,PLAYER_EVENT_PLAYER_UNIT_DEATH)
 call TriggerAddAction(gg_trg_Other,function OtherAction)
endfunction
function OtherAction takes nothing returns nothing
 call QuestSetCompletedBJ(udg_QUEST,true)
endfunction
'''
    report=_report(script);plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible and plan.entry_trigger is None
    assert any('多个原事件入口' in reason for reason in plan.reasons)


def test_reassigned_quest_alias_cannot_select_one_of_two_instances():
    from war3_quest_execution import build_completion_plan
    script=_script()+'''
function RecreateTask takes nothing returns nothing
 set udg_QUEST = CreateQuestBJ(bj_QUESTTYPE_REQ_DISCOVERED)
endfunction
'''
    report=_report(script)
    assert len(report.quests)==2
    assert all(not build_completion_plan(report,q.key).eligible for q in report.quests)


def test_recursive_original_flow_is_rejected_even_when_it_contains_a_setter():
    from war3_quest_execution import build_completion_plan
    report=_report(_script(extra='call FinishAction()'))
    plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible
    assert any('递归' in reason for reason in plan.reasons)


def test_original_trigger_conditions_are_not_silently_bypassed():
    from war3_quest_execution import build_completion_plan
    script=_script().replace('call TriggerAddAction(gg_trg_Finish, function FinishAction)',
        'call TriggerAddCondition(gg_trg_Finish,Condition(function NeedsCount))\n call TriggerAddAction(gg_trg_Finish, function FinishAction)')+'''
function NeedsCount takes nothing returns boolean
 return udg_Kills >= 10
endfunction
'''
    report=_report(script);plan=build_completion_plan(report,_quest(report).key)
    assert not plan.eligible and plan.root_conditions
    assert any('入口条件' in reason for reason in plan.reasons)

