"""R28 entry clues must not imply runtime acceptance or rewrite quest rules."""
import pytest
from test_quest_analysis import analyze
from war3_quest_locations import QuestLocations


def entry(action='call QuestSetDiscovered(q,true)',guard='true',event=None,setup='',extra='',globals_=''):
    event=event or 'call TriggerRegisterEnterRectSimple(t,area)'
    return f'''globals
quest q=null
quest other=null
trigger t=null
rect area=null
rect unrelated=null
unit npc=null
{globals_}
endglobals
function Test takes nothing returns boolean
return {guard}
endfunction
function Accept takes nothing returns nothing
{action}
endfunction
{extra}
function main takes nothing returns nothing
set area=Rect(100,200,300,400)
set unrelated=Rect(8000,9000,10000,11000)
set npc=CreateUnit(Player(0),'nmrk',50,60,0)
set q=CreateQuest()
call QuestSetTitle(q,"Entry quest")
call QuestSetDiscovered(q,false)
set t=CreateTrigger()
{setup}
{event}
call TriggerAddCondition(t,Condition(function Test))
call TriggerAddAction(t,function Accept)
endfunction'''


def before(script):
    report=analyze(script);index=QuestLocations(report)
    q=next(q for q in report.quests if 'q' in q.aliases)
    return index.before(q)


def test_precreated_hidden_quest_discovery_has_event_location_without_changing_rules():
    report=analyze(entry());prior=repr(report)
    index=QuestLocations(report);points=index.before(report.quests[0])
    assert [(p.x,p.y) for p in points]==[(200,300)]
    assert points[0].source=='pre-region' and '触发区域中心' in points[0].describe()
    assert repr(report)==prior and not report.quests[0].completed


def test_delayed_task_creation_before_runtime_handle_exists_has_entry_region():
    script=entry(action='set q=CreateQuest()').replace('set q=CreateQuest()\ncall QuestSetTitle','call QuestSetTitle')
    assert any((p.x,p.y)==(200,300) for p in before(script))


@pytest.mark.parametrize('action',['call QuestSetDiscovered(q,true)','call QuestSetDiscoveredBJ(q,true)',
    'call QuestSetDiscoveredBJ(true,q)'])
def test_npc_acceptance_from_separate_registered_condition(action):
    points=before(entry(action,guard='GetOrderTargetUnit()==npc'))
    npc=next(p for p in points if p.kind=='unit')
    assert (npc.x,npc.y)==(50,60) and npc.source=='pre-npc'
    assert '脚本初始位置，非实时' in npc.describe()


def test_multiple_entry_events_and_item_stock_locations_are_separate():
    points=before(entry(guard="GetItemTypeId(GetManipulatedItem())=='I001'",
        event='call TriggerRegisterEnterRectSimple(t,area)\ncall TriggerRegisterUnitEvent(t,npc,EVENT_UNIT_SELL_ITEM)',
        setup="call CreateItem('I001',400,500)\ncall AddItemToStock(npc,'I001',1,1)"))
    assert {(200,300),(50,60),(400,500)} <= {(p.x,p.y) for p in points}
    assert any(p.kind=='item' and p.source=='vendor' for p in points)


def test_false_discovery_and_unrelated_initialization_are_not_entry_points():
    assert not before(entry(action='call QuestSetDiscovered(q,false)'))
    assert not before(entry(action='call QuestSetCompleted(q,true)'))
    points=before(entry())
    assert not any((p.x,p.y) in ((9000,10000),(50,60)) for p in points)


def test_shared_discovery_wrapper_keeps_quest_parameter_context():
    script=entry(action='call Reveal(q)',extra='''function Reveal takes quest which returns nothing
call QuestSetDiscovered(which,true)
endfunction''',setup='''set other=CreateQuest()
call QuestSetDiscovered(other,false)''')
    report=analyze(script);index=QuestLocations(report)
    assert index.before(next(q for q in report.quests if 'q' in q.aliases))
    assert not index.before(next(q for q in report.quests if 'other' in q.aliases))


def test_explicit_predecessor_execute_retains_entry_region_and_landing():
    script=entry(event='call TriggerRegisterTimerEventSingle(t,10)',globals_='trigger first=null',
        extra='''function First takes nothing returns nothing
call SetUnitPosition(npc,1200,1300)
call TriggerExecute(t)
endfunction''',setup='''set first=CreateTrigger()
call TriggerRegisterEnterRectSimple(first,area)
call TriggerAddAction(first,function First)''')
    points=before(script)
    assert any((p.x,p.y)==(200,300) for p in points)
    assert any(p.source=='teleport' and (p.x,p.y)==(1200,1300) for p in points)


def test_dialog_acceptance_follows_display_trigger_not_unrelated_units():
    script=entry(event='call TriggerRegisterDialogEvent(t,d)',globals_='dialog d=null\ntrigger first=null',
        extra='''function First takes nothing returns nothing
call DialogDisplay(Player(0),d,true)
endfunction''',setup='''set d=DialogCreate()
set first=CreateTrigger()
call TriggerRegisterUnitInRange(first,npc,256,null)
call TriggerAddAction(first,function First)''')
    points=before(script)
    assert any((p.x,p.y)==(50,60) and '半径 256' in p.via for p in points)


def test_pure_timer_and_dynamic_object_stay_unresolved():
    assert not before(entry(event='call TriggerRegisterTimerEventSingle(t,10)'))
    points=before(entry(guard='GetOrderTargetUnit()==npc').replace("CreateUnit(Player(0),'nmrk',50,60,0)",'SomeDynamicUnit()'))
    assert any(p.kind=='unit' and not p.locatable for p in points)


def test_unrelated_earlier_branch_and_post_entry_actions_are_not_entry_locations():
    points=before(entry(action='''if GetRandomInt(0,1)==1 then
call SetUnitPosition(npc,8000,9000)
endif
call QuestSetDiscovered(q,true)
call SetUnitPosition(npc,9000,10000)'''))
    assert not any((p.x,p.y) in ((8000,9000),(9000,10000)) for p in points)


def test_explicit_helper_before_acceptance_and_fixed_build_sources_keep_their_labels():
    points=before(entry(action='call Reveal(q)',extra='''function Reveal takes quest which returns nothing
call SetUnitPosition(npc,1200,1300)
call IssueBuildOrder(npc,"farm",1400,1500)
call QuestSetDiscovered(which,true)
endfunction'''))
    assert any(p.source=='teleport' and (p.x,p.y)==(1200,1300) for p in points)
    assert any(p.source=='build' and (p.x,p.y)==(1400,1500) for p in points)


def test_overridden_discovery_function_is_not_assumed_native():
    script=entry(extra='''function QuestSetDiscovered takes quest which, boolean flag returns nothing
return
endfunction''')
    assert not before(script)


