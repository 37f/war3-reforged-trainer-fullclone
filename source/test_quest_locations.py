"""Script-only coordinates must not turn unknown or initial positions into live facts."""
from dataclasses import replace
import pytest
from test_quest_analysis import analyze
from war3_quest_locations import QuestLocations
from war3_quest_text import QuestText

SCRIPT='''globals
quest q=null
rect gg_rct_Exit=null
unit gg_unit_Boss=null
trigger gg_trg_Done=null
integer counter=0
endglobals
function C takes nothing returns boolean
return IsUnitDeadBJ(gg_unit_Boss)
endfunction
function A takes nothing returns nothing
call QuestSetCompleted(q,true)
endfunction
function main takes nothing returns nothing
set gg_rct_Exit=Rect(-400,-200,200,600)
set gg_unit_Boss=CreateUnit(Player(1),'Hpal',800,100,0)
set q=CreateQuest()
set gg_trg_Done=CreateTrigger()
call TriggerRegisterEnterRectSimple(gg_trg_Done,gg_rct_Exit)
call TriggerAddCondition(gg_trg_Done,Condition(function C))
call TriggerAddAction(gg_trg_Done,function A)
endfunction'''


def test_enter_region_and_required_dead_unit_have_distinct_labeled_locations():
    report=analyze(SCRIPT);index=QuestLocations(report);rule=report.quests[0].completed[0]
    places=index.rule(rule)
    assert {(p.kind,p.x,p.y) for p in places}=={('region',-100.,200.),('unit',800.,100.)}
    assert next(p for p in places if p.kind=='region').bounds==(-400.,-200.,200.,600.)
    unit=next(p for p in places if p.kind=='unit')
    assert unit.rawcode=='Hpal' and '初始位置' in unit.describe()
    rendered=QuestText(report,locations=index).quest(report.quests[0])
    assert '关联地点' in rendered and 'X=-100' in rendered and 'X=800' in rendered
    # The original rule guards/events are reused without changing their meaning.
    assert 'IsUnitDeadBJ' in rule.paths[0].guard


def test_generated_local_unit_alias_is_resolved_with_function_and_line_scope():
    script=SCRIPT.replace('set gg_unit_Boss=CreateUnit', 'set temporary=CreateUnit')
    script=script.replace('function main takes nothing returns nothing','function main takes nothing returns nothing\nlocal unit temporary=null')
    script=script.replace("'Hpal',800,100,0)","'Hpal',800,100,0)\nset gg_unit_Boss=temporary\nset temporary=CreateUnit(Player(1),'hfoo',900,200,0)")
    place=QuestLocations(analyze(script)).named('gg_unit_Boss')[0]
    assert (place.x,place.y,place.rawcode)==(800,100,'Hpal')


@pytest.mark.parametrize('replacement',[
    'set gg_rct_Exit=Rect(RandomValue(),0,200,600)',
    'set gg_rct_Exit=Rect(400,200,-200,600)',
    'set gg_rct_Exit=Rect(-400,-200,200,600)\nset gg_rct_Exit=Rect(0,0,10,10)',
])
def test_unknown_reversed_and_conflicting_regions_are_not_guessed(replacement):
    script=SCRIPT.replace('set gg_rct_Exit=Rect(-400,-200,200,600)',replacement)
    assert not QuestLocations(analyze(script)).named('gg_rct_Exit')


def test_no_location_is_explicit_and_does_not_change_counter_condition():
    report=analyze(SCRIPT.replace('IsUnitDeadBJ(gg_unit_Boss)','counter >= 3').replace(
        'call TriggerRegisterEnterRectSimple(gg_trg_Done,gg_rct_Exit)','call TriggerRegisterTimerEventSingle(gg_trg_Done,5)'))
    index=QuestLocations(report)
    assert not index.rule(report.quests[0].completed[0])
    text=QuestText(report,locations=index).quest(report.quests[0])
    assert '关联地点：无位置' in text and '不少于 3' in text


def test_region_composition_lists_each_rectangle_without_picking_one():
    report=analyze(SCRIPT.replace('rect gg_rct_Exit=null','rect gg_rct_Exit=null\nregion udg_Area=null').replace(
        'set q=CreateQuest()','set udg_Area=CreateRegion()\ncall RegionAddRect(udg_Area,gg_rct_Exit)\ncall RegionAddRect(udg_Area,Rect(10,20,30,40))\nset q=CreateQuest()'))
    places=QuestLocations(report).named('udg_Area')
    assert {(p.x,p.y) for p in places}=={(-100,200),(20,30)}


def test_dynamic_local_assignment_cannot_silently_select_a_branch():
    script=SCRIPT.replace('function main takes nothing returns nothing','function main takes nothing returns nothing\nlocal unit u=null')
    script=script.replace("set gg_unit_Boss=CreateUnit(Player(1),'Hpal',800,100,0)",
        "if counter > 0 then\nset u=CreateUnit(Player(1),'Hpal',800,100,0)\nendif\nset gg_unit_Boss=u")
    assert not QuestLocations(analyze(script)).named('gg_unit_Boss')


def test_runtime_unit_coordinates_are_not_substituted_with_initial_spawn():
    script=SCRIPT.replace('quest q=null','quest q=null\nlocation udg_Point=null').replace(
        'set q=CreateQuest()','set udg_Point=GetUnitLoc(gg_unit_Boss)\nset q=CreateQuest()')
    index=QuestLocations(analyze(script))
    assert index.named('gg_unit_Boss') and not index.named('udg_Point')
