"""R27 links use explicit script evidence, never object names or runtime guesses."""
import pytest
from test_quest_analysis import analyze
from war3_quest_locations import QuestLocations


def task(guard='true',actions='',setup='',globals_='',extra='',event=None):
    event=event or 'call TriggerRegisterTimerEventSingle(gg_trg_Done,5)'
    return f'''globals
quest q=null
trigger gg_trg_Done=null
rect gg_rct_Exit=null
unit gg_unit_Boss=null
unit gg_unit_NPC=null
{globals_}
endglobals
function C takes nothing returns boolean
return {guard}
endfunction
function A takes nothing returns nothing
{actions}
call QuestSetCompleted(q,true)
endfunction
{extra}
function main takes nothing returns nothing
set gg_rct_Exit=Rect(100,200,300,400)
set gg_unit_Boss=CreateUnit(Player(1),'Hpal',800,100,0)
set gg_unit_NPC=CreateUnit(Player(24),'nmrk',50,60,0)
{setup}
set q=CreateQuest()
set gg_trg_Done=CreateTrigger()
{event}
call TriggerAddCondition(gg_trg_Done,Condition(function C))
call TriggerAddAction(gg_trg_Done,function A)
endfunction'''


def places(script):
    report=analyze(script);index=QuestLocations(report)
    return index.rule(report.quests[0].completed[0])


@pytest.mark.parametrize('event',['TriggerRegisterEnterRectSimple','TriggerRegisterLeaveRectSimple'])
def test_enter_and_leave_exit_regions(event):
    result=places(task(event=f'call {event}(gg_trg_Done,gg_rct_Exit)'))
    assert any(p.kind=='region' and (p.x,p.y)==(200,300) for p in result)


def test_range_and_inline_rect_coordinates_are_visible():
    result=places(task(event='call TriggerRegisterUnitInRange(gg_trg_Done,gg_unit_Boss,256,null)'))
    assert any(p.locatable and '半径 256' in p.via for p in result)
    result=places(task(event='call TriggerRegisterEnterRectSimple(gg_trg_Done,Rect(-20,-40,60,80))'))
    assert any(p.kind=='region' and (p.x,p.y)==(20,20) for p in result)


@pytest.mark.parametrize('guard,actions,event',[
    ('IsUnitDeadBJ(gg_unit_Boss)','','call TriggerRegisterTimerEventSingle(gg_trg_Done,5)'),
    ('true','','call TriggerRegisterUnitEvent(gg_trg_Done,gg_unit_Boss,EVENT_UNIT_RESCUED)'),
    ('GetOrderTargetUnit()==gg_unit_Boss','','call TriggerRegisterTimerEventSingle(gg_trg_Done,5)'),
    ('true','call SetUnitPosition(gg_unit_Boss,1200,1300)','call TriggerRegisterEnterRectSimple(gg_trg_Done,gg_rct_Exit)'),
])
def test_kill_rescue_dialogue_and_escort_named_unit_refs(guard,actions,event):
    result=places(task(guard,actions,event=event))
    assert any(p.kind=='unit' and (p.x,p.y)==(800,100) for p in result)
    assert all('非实时' in p.describe() for p in result if p.kind=='unit')
    if actions:assert any(p.source=='teleport' and (p.x,p.y)==(1200,1300) for p in result)


def test_item_type_links_pickup_spawn_and_matching_shop_but_not_other_stock():
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I001'",setup="""
call CreateItem('I001',400,500)
call CreateItem('I002',900,950)
call AddItemToStock(gg_unit_NPC,'I001',1,1)
call AddItemToStock(gg_unit_Boss,'I002',1,1)"""))
    items=[p for p in result if p.kind=='item']
    assert any(p.rawcode=='I001' and p.source=='spawn' and (p.x,p.y)==(400,500) for p in items)
    assert any(p.rawcode=='I001' and p.source=='vendor' and (p.x,p.y)==(50,60) for p in items)
    assert not any(p.rawcode=='I002' for p in items)


def test_death_callback_drop_is_labeled_as_source_initial_not_actual_death_position():
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I001'",globals_='trigger drop=null',setup='''
set drop=CreateTrigger()
call TriggerRegisterUnitEvent(drop,gg_unit_Boss,EVENT_UNIT_DEATH)
call TriggerAddAction(drop,function Drop)
''',extra='''function Drop takes nothing returns nothing
call CreateItem('I001',GetUnitX(GetDyingUnit()),GetUnitY(GetDyingUnit()))
endfunction'''))
    drop=next(p for p in result if p.source=='drop' and p.locatable)
    assert (drop.x,drop.y)==(800,100)
    assert '实际掉落随死亡位置' in drop.describe() and '非实时' in drop.describe()


def test_item_holder_does_not_become_a_guaranteed_drop():
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I001'",setup="call UnitAddItemById(gg_unit_Boss,'I001')"))
    assert any(p.source=='holder' and '不能据此认定掉落' in p.describe() for p in result)
    assert not any(p.source=='drop' for p in result)


def test_item_delivery_and_explicit_use_drop_points():
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I001'",actions='''
call UnitDropItemTarget(GetTriggerUnit(),GetManipulatedItem(),gg_unit_NPC)
call UnitUseItemPoint(GetTriggerUnit(),GetManipulatedItem(),1000,1100)
call UnitDropItemPoint(GetTriggerUnit(),GetManipulatedItem(),1200,1300)'''))
    assert any(p.source=='delivery' and (p.x,p.y)==(50,60) for p in result)
    assert any(p.source=='delivery' and (p.x,p.y)==(1000,1100) for p in result)
    assert any(p.source=='drop-fixed' and (p.x,p.y)==(1200,1300) for p in result)


def test_destructible_neutral_building_capture_and_build_order_locations():
    result=places(task('GetDestructableLife(gg_dest_Door)<=0',globals_='destructable gg_dest_Door=null',
        setup="set gg_dest_Door=CreateDestructable('LTg1',25,35,0,1,0)",
        actions="call SetUnitOwner(gg_unit_NPC,Player(0),true)\ncall IssueBuildOrderById(gg_unit_Boss,'hbar',700,750)"))
    assert any(p.kind=='destructable' and (p.x,p.y)==(25,35) for p in result)
    assert any(p.kind=='unit' and (p.x,p.y)==(50,60) for p in result)
    assert any(p.source=='build' and p.rawcode=='hbar' and (p.x,p.y)==(700,750) for p in result)


def test_camera_preset_observation_and_teleport_are_separate_click_targets():
    result=places(task(globals_='camerasetup gg_cam_Exit=null\nlocation udg_Landing=null',setup='''
set gg_cam_Exit=CreateCameraSetup()
call CameraSetupSetDestPosition(gg_cam_Exit,1500,1600,0)
set udg_Landing=Location(1700,1800)''',actions='''
call CameraSetupApplyForceDuration(gg_cam_Exit,true,0)
call PanCameraToTimed(1900,2000,1)
call SetUnitPositionLoc(gg_unit_Boss,udg_Landing)'''))
    assert any(p.source=='camera' and (p.x,p.y)==(1500,1600) for p in result)
    assert any(p.source=='observation' and (p.x,p.y)==(1900,2000) for p in result)
    assert any(p.source=='teleport' and (p.x,p.y)==(1700,1800) for p in result)


def test_explicit_timer_callback_links_its_spawn_action_but_pure_timer_has_no_place():
    assert not places(task())
    script=task(globals_='timer udg_T=null',setup='call StartTimed()',extra='''
function Expired takes nothing returns nothing
call QuestSetFailed(q,true)
endfunction
function StartTimed takes nothing returns nothing
call CreateUnit(Player(1),'hfoo',2100,2200,0)
call TimerStart(udg_T,30,false,function Expired)
endfunction''')
    report=analyze(script);index=QuestLocations(report)
    result=index.rule(report.quests[0].failed[0])
    assert any((p.x,p.y)==(2100,2200) for p in result)


def test_parameterized_item_source_and_action_wrapper_are_followed_without_execution():
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I001'",setup="call Spawn('I001',2500,2600)",
        actions='call Teleport(gg_unit_Boss,2700,2800)',extra='''
function Spawn takes integer code, real x, real y returns nothing
call CreateItem(code,x,y)
endfunction
function Teleport takes unit u, real x, real y returns nothing
call SetUnitPosition(u,x,y)
endfunction'''))
    assert any(p.rawcode=='I001' and (p.x,p.y)==(2500,2600) for p in result)
    assert any(p.source=='teleport' and (p.x,p.y)==(2700,2800) for p in result)


def test_unknown_object_is_displayed_but_not_locatable_and_init_is_not_swept():
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I999'",setup="call CreateItem('I001',800,900)"))
    assert result and all(not p.locatable for p in result)
    assert all('无位置' in p.describe() for p in result)
    assert not any(p.rawcode=='I001' for p in result)


def test_random_item_spawn_links_referenced_region_without_inventing_exact_point():
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I001'",setup="""
call CreateItem('I001',GetRandomReal(GetRectMinX(gg_rct_Exit),GetRectMaxX(gg_rct_Exit)),GetRectCenterY(gg_rct_Exit))"""))
    p=next(p for p in result if p.source=='spawn-region')
    assert (p.x,p.y)==(200,300) and p.bounds==(100,200,300,400)
    assert '具体刷新点未确认' in p.describe()


def test_escort_move_order_keeps_actor_initial_and_explicit_waypoint():
    result=places(task(actions='call IssuePointOrder(gg_unit_Boss,"move",3200,3300)'))
    assert any(p.kind=='unit' and (p.x,p.y)==(800,100) for p in result)
    assert any(p.source=='order' and (p.x,p.y)==(3200,3300) for p in result)


def test_random_drop_table_lists_candidates_as_candidates():
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I001'",globals_='trigger drop=null',setup='''
set drop=CreateTrigger()
call TriggerRegisterUnitEvent(drop,gg_unit_Boss,EVENT_UNIT_DEATH)
call TriggerAddAction(drop,function Drop)
''',extra='''function Drop takes nothing returns nothing
call RandomDistAddItem('I001',50)
call RandomDistAddItem('I002',50)
call UnitDropItem(GetDyingUnit(),RandomDistChoose())
endfunction'''))
    drop=next(p for p in result if p.source=='drop' and p.rawcode=='I001')
    assert drop.locatable and '随机掉落候选' in drop.describe()


def test_reforged_skin_constructor_and_later_unconditional_local_write():
    script=task('IsUnitDeadBJ(gg_unit_Boss)')
    script=script.replace('function main takes nothing returns nothing','function main takes nothing returns nothing\nlocal unit u=null')
    script=script.replace("set gg_unit_Boss=CreateUnit(Player(1),'Hpal',800,100,0)","""
if GetRandomInt(0,1)==1 then
set u=CreateUnit(Player(1),'hfoo',10,20,0)
endif
set u=BlzCreateUnitWithSkin(Player(1),'Hpal',800,100,0,'Hpal')
set gg_unit_Boss=u""")
    result=places(script)
    assert any(p.kind=='unit' and (p.x,p.y)==(800,100) for p in result)


def test_registration_initializers_do_not_add_other_quest_regions():
    script=task().replace('rect gg_rct_Exit=null','rect gg_rct_Exit=null\nrect gg_rct_Other=null\ntrigger other=null')
    script=script.replace('function main takes nothing returns nothing','''
function InitOther takes nothing returns nothing
set other=CreateTrigger()
call TriggerRegisterEnterRectSimple(other,gg_rct_Other)
endfunction
function InitTasks takes nothing returns nothing
call InitOther()
set gg_trg_Done=CreateTrigger()
call TriggerRegisterTimerEventSingle(gg_trg_Done,5)
call TriggerAddCondition(gg_trg_Done,Condition(function C))
call TriggerAddAction(gg_trg_Done,function A)
endfunction
function main takes nothing returns nothing''')
    start=script.index('set gg_trg_Done=CreateTrigger()',script.index('function main'))
    script=script[:start]+"set gg_rct_Other=Rect(5000,6000,7000,8000)\ncall InitTasks()\nendfunction"
    assert not places(script)


def test_parameterized_completion_helper_does_not_add_opposite_branch_camera():
    script=task(actions='call Complete(q,true)',extra='''
function Complete takes quest target, boolean win returns nothing
if win then
call PanCameraToTimed(1000,1100,0)
call QuestSetCompleted(target,true)
else
call PanCameraToTimed(5000,5100,0)
call QuestSetFailed(target,true)
endif
endfunction''')
    script=script.replace('call Complete(q,true)\ncall QuestSetCompleted(q,true)','call Complete(q,true)')
    result=places(script)
    assert any(p.source=='observation' and (p.x,p.y)==(1000,1100) for p in result)
    assert not any((p.x,p.y)==(5000,5100) for p in result)


def test_map_defined_familiar_name_is_not_assumed_to_move_camera():
    result=places(task(actions='call PanCameraToTimed(4500,4600,0)',extra='''
function PanCameraToTimed takes real x, real y, real duration returns nothing
return
endfunction'''))
    assert not result


def test_source_limit_is_visible_and_overflow_marker_is_not_clickable():
    setup='\n'.join(f"call CreateItem('I001',{n*10},500)" for n in range(130))
    result=places(task("GetItemTypeId(GetManipulatedItem())=='I001'",setup=setup))
    assert sum(p.locatable for p in result)==128
    marker=next(p for p in result if '超过 128' in p.via)
    assert not marker.locatable and '无位置' in marker.describe()
