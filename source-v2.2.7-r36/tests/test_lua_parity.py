"""Lua evidence should share JASS presentation without pretending to run Lua."""
import re
import pytest
from war3_fullclone_quests import ScriptSnapshot,render
from war3_lua_quests import parse_lua
from war3_quest_analysis import analyze_quests
from war3_quest_locations import QuestLocations


def analyze(text):return analyze_quests(ScriptSnapshot(language='lua',script=text.encode('utf8')))


SCRIPT='''q=nil
area=nil
boss=nil
function Gate()
 return IsUnitDeadBJ(boss) and GetHeroLevel(boss)>=3
end
function main()
 area=Rect(-100,-200,300,600)
 boss=CreateUnit(Player(1),FourCC("Hpal"),800,900,0)
 q=CreateQuest()
 QuestSetTitle(q,"回调任务")
 local t=CreateTrigger()
 TriggerRegisterEnterRectSimple(t,area)
 TriggerAddCondition(t,Condition(function()
  return Gate()
 end))
 TriggerAddAction(t,function()
  QuestSetCompleted(q,true)
 end)
end
'''


def test_anonymous_callbacks_keep_named_guards_events_and_locations():
    r=analyze(SCRIPT);q=r.quests[0]
    assert q.title=='回调任务' and q.completed
    rule=q.completed[0];path=rule.paths[0]
    assert 'GetHeroLevel' in path.guard and '>= 3' in path.guard and 'IsUnitDeadBJ' in path.guard
    assert 'EnterRect' in ' '.join(path.events)
    assert {(p.kind,p.x,p.y) for p in QuestLocations(r).rule(rule)}>={('region',100.,200.),('unit',800.,900.)}
    rows,_,_=render(r)
    assert rows[0]['state']=='状态未确认' and rows[0]['conditions'][0]['positions']


def test_anonymous_and_named_lua_callbacks_have_equivalent_evidence():
    inline=analyze(SCRIPT)
    named=SCRIPT.replace('function main()', 'function Finish()\n QuestSetCompleted(q,true)\nend\nfunction main()')
    named=named.replace('Condition(function()\n  return Gate()\n end)','Condition(Gate)')
    named=named.replace('function()\n  QuestSetCompleted(q,true)\n end','Finish')
    a,b=inline.quests[0].completed[0],analyze(named).quests[0].completed[0]
    assert a.paths[0].guard==b.paths[0].guard
    normalize=lambda events:tuple(re.sub(r'T:\w+:\d+:\d+','TRIGGER',e) for e in events)
    assert normalize(a.paths[0].events)==normalize(b.paths[0].events)


def test_lua_and_jass_share_the_same_conditions_and_initial_location_results():
    jass='''globals
quest q=null
rect area=null
unit boss=null
trigger t=null
endglobals
function Gate takes nothing returns boolean
return IsUnitDeadBJ(boss) and GetHeroLevel(boss)>=3
endfunction
function Done takes nothing returns nothing
call QuestSetCompleted(q,true)
endfunction
function main takes nothing returns nothing
set area=Rect(-100,-200,300,600)
set boss=CreateUnit(Player(1),'Hpal',800,900,0)
set q=CreateQuest()
call QuestSetTitle(q,"回调任务")
set t=CreateTrigger()
call TriggerRegisterEnterRectSimple(t,area)
call TriggerAddCondition(t,Condition(function Gate))
call TriggerAddAction(t,function Done)
endfunction
'''
    lua=analyze(SCRIPT);other=analyze_quests(ScriptSnapshot(language='jass',script=jass.encode('utf8')))
    a,b=lua.quests[0],other.quests[0]
    assert a.title==b.title and a.completed[0].paths[0].guard==b.completed[0].paths[0].guard
    positions=lambda r,q:{(p.kind,p.x,p.y,p.rawcode) for p in QuestLocations(r).rule(q.completed[0])}
    assert positions(lua,a)==positions(other,b)


def test_anonymous_timer_keeps_failure_callback_and_delay_evidence():
    r=analyze('''q=nil
function main()
 q=CreateQuest()
 QuestSetTitle(q,"限时任务")
 local timer=CreateTimer()
 TimerStart(timer,20,false,function()
  QuestSetFailed(q,true)
 end)
end
''')
    assert r.quests[0].failed and r.quests[0].failed[0].paths
    assert '20' in str(r.quests[0].failed[0].paths)


@pytest.mark.parametrize('declaration',['local q=CreateQuest()','local target=q'])
def test_captured_locals_do_not_become_unconditional_global_completions(declaration):
    ref='q' if declaration.startswith('local q=') else 'target'
    r=analyze('''q=nil
function main()
 q=CreateQuest()
 QuestSetTitle(q,"闭包")
 '''+declaration+'''
 local t=CreateTrigger()
 TriggerAddAction(t,function()
  QuestSetCompleted('''+ref+''',true)
 end)
end
''')
    assert not r.quests[0].completed
    assert any('捕获外层局部变量' in issue for issue in r.issues)


def test_outer_parse_failure_discards_all_lifted_callback_bodies():
    r=analyze(SCRIPT)
    assert r.quests[0].completed
    bad=SCRIPT.replace('  QuestSetCompleted(q,true)\n end)', '  QuestSetCompleted(q,true)\n end)\n local values={1,2}')
    parsed=parse_lua(bad)
    assert 'main' in parsed.opaque
    assert all(not fn.body for name,fn in parsed.functions.items() if name.startswith('__fc_lua_callback_'))


def test_overridden_callback_registration_does_not_enable_standard_adapter():
    r=analyze('TriggerAddAction=CustomRegister\n'+SCRIPT)
    assert not r.quests[0].completed
    assert any('注册函数已被地图改写' in issue for issue in r.issues)


def test_callback_parameters_cannot_alias_a_global_quest_with_the_same_name():
    r=analyze(SCRIPT.replace('TriggerAddAction(t,function()', 'TriggerAddAction(t,function(q)'))
    assert not r.quests[0].completed
    assert any('回调参数绑定尚未确认' in issue for issue in r.issues)


def test_late_outer_validation_also_removes_lifted_callbacks():
    p=parse_lua(SCRIPT.replace('  QuestSetCompleted(q,true)\n end)', '  QuestSetCompleted(q,true)\n end)\n q=ready and q or nil'))
    assert 'main' in p.opaque
    assert all(not fn.body for name,fn in p.functions.items() if name.startswith('__fc_lua_callback_'))


@pytest.mark.parametrize('local_name',['CreateQuestBJ','Title'])
def test_local_function_names_do_not_use_global_native_or_text_adapters(local_name):
    r=analyze('''function Title(label)
 return "wrong"
end
function main()
 local '''+local_name+'''=UnknownFunction
 CreateQuestBJ(0,Title("name"),"","")
end
''')
    assert not r.quests
    assert any('局部或参数函数名' in issue for issue in r.issues)


@pytest.mark.parametrize('guard',['IsUnitDeadBJ(boss) and GetHeroLevel(boss)>=3','IsUnitDeadBJ(boss) or IsUnitAliveBJ(boss)'])
def test_only_boolean_operand_compositions_get_predicate_return_type(guard):
    p=parse_lua('function Gate()\n return '+guard+'\nend\n')
    assert p.functions['Gate'].return_type=='boolean'
    p=parse_lua('function Gate()\n return 0 or IsUnitDeadBJ(boss)\nend\n')
    assert p.functions['Gate'].return_type!='boolean'


def test_simple_pure_text_helpers_and_integer_concat():
    r=analyze('''function Title(label)
 local text="主线："..label
 return text
end
function Detail(count)
 return "击败"..count.."名敌人"
end
function main()
 CreateQuestBJ(0,Title("守卫城门"),Detail(12),"")
end
''')
    assert r.quests[0].title=='主线：守卫城门' and r.quests[0].description=='击败12名敌人'


@pytest.mark.parametrize('body',['SetHeroLevel(u,10,false)\n return "wrong"','if ready then return "wrong" end','return Title(label)'])
def test_dynamic_side_effect_or_recursive_text_helpers_stay_unknown(body):
    r=analyze('function Title(label)\n '+body+'\nend\nfunction main()\n CreateQuestBJ(0,Title("name"),"","")\nend\n')
    assert r.quests[0].title!='wrong'
    assert any('动态任务文字' in issue for issue in r.issues)


def test_tostring_integer_is_static_but_an_override_is_not():
    r=analyze('function main()\n CreateQuestBJ(0,"任务"..tostring(12),"","")\nend\n')
    assert r.quests[0].title=='任务12'
    r=analyze('tostring=Localized\nfunction main()\n CreateQuestBJ(0,"任务"..tostring(12),"","")\nend\n')
    assert r.quests[0].title!='任务12'
