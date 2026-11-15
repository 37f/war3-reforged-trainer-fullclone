"""Lua quest evidence and provenance regression. No game code is executed."""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
import struct

import pytest

from war3_fullclone_quests import ScriptSnapshot, _members
from war3_quest_analysis import analyze_quests, AnalysisUnavailable
from war3_quest_locations import QuestLocations
from war3_lua_quests import parse_lua, LuaParseError


SCRIPT='''q = nil
area = nil
boss = nil
t = nil
title = ""
description = ""
function Texts()
 title = StringIdentity("TRIGSTR_001")
 description = "找到目标。"
 description = description .. "完成后返回。"
end
function Gate()
 if not (GetHeroLevel(boss) >= 3) then
  return false
 end
 return IsUnitDeadBJ(boss)
end
function Done()
 QuestSetCompletedBJ(q, true)
end
function Lost()
 QuestSetFailedBJ(q, true)
end
function main()
 area = Rect(-100,-200,300,600)
 boss = CreateUnit(Player(1), FourCC("Hpal"), 800, 900, 0)
 Texts()
 CreateQuestBJ(bj_QUESTTYPE_OPT_UNDISCOVERED, title, description, "icon")
 q = GetLastCreatedQuestBJ()
 CreateQuestItemBJ(q,"击败目标")
 t = CreateTrigger()
 TriggerRegisterEnterRectSimple(t, area)
 TriggerAddCondition(t, Condition(Gate))
 TriggerAddAction(t, Done)
end
'''


def analyze(text=SCRIPT):
    return analyze_quests(ScriptSnapshot(language='lua',script=text.encode('utf8'),strings_data=b'STRING 1\n{\nLua quest\n}\n'))


def test_lua_text_wts_aliases_guards_and_both_quest_outcomes():
    report=analyze();assert len(report.quests)==1
    q=report.quests[0]
    assert q.title=='Lua quest' and q.required is False and q.discovered is False
    assert q.description=='找到目标。完成后返回。'
    assert q.items[0].description=='击败目标' and q.completed and q.failed
    path=q.completed[0].paths[0]
    assert 'EnterRect' in ' '.join(path.events) and 'GetHeroLevel' in path.guard and '>= 3' in path.guard
    assert 'q' in q.aliases
    assert any('Lua 静态' in i for i in report.issues)


def test_lua_locations_use_exact_region_and_initial_unit_constructor():
    r=analyze();locations=QuestLocations(r)
    assert {(p.kind,p.x,p.y) for p in locations.rule(r.quests[0].completed[0])}>={('region',100.,200.),('unit',800.,900.)}
    assert any('初始' in p.describe() for p in locations.named('boss'))


def test_lua_comments_long_strings_and_call_text_are_not_executed_or_scanned():
    text='''-- CreateQuestBJ(0,"fake1","","")
--[=[ function Fake() CreateQuest() end ]=]
payload = [==[QuestSetFailed(q,true) -- not code]==]
function main()
 local text = "CreateQuest()"
 CreateQuestBJ(0,"real",payload,"icon")
end
'''
    r=analyze(text)
    assert len(r.quests)==1 and r.quests[0].title=='real' and not r.quests[0].failed
    assert 'QuestSetFailed' in r.quests[0].description


@pytest.mark.parametrize('unsupported',[
 'local values = {1, 2}',
 'local cb = function() return true end',
 'for n=1,2 do QuestSetFailed(q,true) end',
 'do local q = nil end',
 'if true then local q = nil end',
 'q = flag and q or nil',
])
def test_unknown_function_is_opaque_instead_of_losing_its_guards(unsupported):
    r=analyze('''q=nil
function Complex()
 '''+unsupported+'''
 QuestSetCompleted(q,true)
end
function main()
 q=CreateQuest()
 QuestSetTitle(q,"real")
 Complex()
end
''')
    assert len(r.quests)==1 and not r.quests[0].completed
    assert any('Complex' in i and '未展开' in i for i in r.issues)


def test_native_override_and_reassigned_function_cannot_enable_bj_adapter():
    for prefix in ['function CreateQuestBJ(a,b,c,d)\n local x = {1}\nend\n','CreateQuestBJ = CustomQuestFactory\n']:
        r=analyze(prefix+'function main()\n CreateQuestBJ(0,"Not a standard quest","","")\nend\n')
        assert not r.quests and r.partial


def test_unknown_top_level_function_literal_is_not_parsed_as_global_actions():
    r=analyze('''builder = function()
 CreateQuestBJ(0,"Hidden inside unparsed closure","","")
end
function main()
 CreateQuestBJ(0,"Visible","","")
end
''')
    assert [q.title for q in r.quests]==['Visible']


def test_lua_zero_and_empty_string_are_not_simplified_as_boolean_false():
    text='''q=nil
function Finish()
 if amount == true then
  QuestSetCompleted(q,true)
 end
end
function main()
 q=CreateQuest()
 Finish()
end
'''
    r=analyze(text);guard=r.quests[0].completed[0].paths[0].guard
    assert 'amount == true' in guard
    assert guard!='amount'


def test_local_callback_shadow_does_not_resolve_to_global_function():
    text=SCRIPT.replace(' TriggerAddAction(t, Done)',' local Done = callback\n TriggerAddAction(t, Done)')
    r=analyze(text)
    assert any('动作函数无法静态确定' in i for i in r.issues)


def test_lua_cancel_and_unclosed_blocks_fail_explicitly():
    with pytest.raises(LuaParseError,match='取消'):parse_lua('function main() end',lambda:True)
    with pytest.raises(LuaParseError,match='未闭合'):parse_lua('function main()\n if flag then\n end')
    with pytest.raises(AnalysisUnavailable):analyze('function main()\n x="bad\nend')


def test_archive_lua_host_does_not_select_leftover_jass():
    class Archive:
        def read(self,name,optional=False):return {'war3map.j':b'old jass','war3map.lua':b'function main() end'}.get(name)
    assert _members(Archive(),preferred_language='lua')[2]=='lua'
    assert _members(Archive())[2]=='jass'


def test_lua_status_never_enters_jass_symbol_or_native_query(monkeypatch):
    import war3_fullclone_source as source
    import war3_fullclone_status as status
    monkeypatch.setattr(status,'query_states',lambda *args:pytest.fail('JASS query used for Lua'))
    r=analyze();states=source.quest_states(None,r,dict(metadata=dict(language='lua'),trusted=True))
    assert all(v['state']=='状态未确认' and 'Lua' in v['reason'] for v in states.values())


@pytest.mark.parametrize('valid_rtti',[True,False])
def test_lua_host_metadata_validates_rtti_without_reading_jass_vm(monkeypatch,valid_rtti):
    import war3_fullclone_source as source
    base=0x10000000;world=0x20000000;record=0x21000000;name=0x22000000;host=0x23000000;col=base+0x30000;typeaddr=base+0x40000
    u64={base+0x10:1,world:base+0x27548e0,world+0x2ed0:record,record+0x38:name,world+0x25d8:host,
         host:base+0x2878f50,base+0x2878f50-8:col}
    class Memory:
        def read_u64(self,address):assert address in u64;return u64[address]
        def read(self,address,size):
            if address==col:return struct.pack('<6I',1 if valid_rtti else 0,0,0,0x40000,0,0x30000)
            raise AssertionError('Unexpected VM/memory read')
    profile=SimpleNamespace(data={'game_version':source.BUILD},id='exact')
    engine=SimpleNamespace(session=SimpleNamespace(profile=profile,identity='test',epoch=7))
    @contextmanager
    def context(t):yield engine,Memory(),SimpleNamespace(base=base,addresses={'game_state':0x10}),None,None
    monkeypatch.setattr(source,'read_context',context);monkeypatch.setattr(source,'decode_game_state',lambda a,p:world)
    monkeypatch.setattr(source,'_string',lambda m,a,limit=4096:'current.w3x' if a==name else '.?AVLuaScriptInstance_t@@' if a==typeaddr+16 else pytest.fail('Unknown string'))
    if not valid_rtti:
        with pytest.raises(ValueError,match='Lua 脚本宿主类型'):source.metadata(None)
        return
    result=source.metadata(None)
    assert result['language']=='lua' and result['vm']==result['symbols']==0


def test_keyword_like_strings_cannot_close_blocks_or_call_arguments():
    r=analyze('function main()\n CreateQuestBJ(0,")","end", "if")\nend\n')
    assert r.quests[0].title==')' and r.quests[0].description=='end'


def test_utf8_decimal_and_hex_escapes_remain_human_text():
    r=analyze(r'function main()'+"\n"+r' CreateQuestBJ(0,"\228\189\160","\xE5\xA5\xBD","")'+"\nend\n")
    assert r.quests[0].title=='你' and r.quests[0].description=='好'


def test_opaque_initializer_empty_reset_does_not_hide_nonempty_text_candidate():
    text=SCRIPT+'\nfunction InitGlobals()\n title=""\n for i=1,2 do array[i]=nil end\nend\n'
    assert analyze(text).quests[0].title=='Lua quest'
    text=SCRIPT+'\nfunction DynamicText()\n title=GetUnknownText()\n local cb=function() end\nend\n'
    assert analyze(text).quests[0].title=='title'


def test_map_string_wrapper_only_exposes_explicitly_labelled_base_wts_candidate():
    text='function StringIdentity(key)\n return "map override"\nend\n'+SCRIPT
    r=analyze(text)
    assert r.quests[0].title=='Lua quest'
    assert any('基础字符串表候选' in issue for issue in r.issues)
    from war3_quest_text import QuestText
    assert '最终文字未确认' in QuestText(r).quest(r.quests[0])


def test_native_override_inside_unparsed_top_level_closure_is_not_a_builtin():
    r=analyze('''RegisterInit(function()
 function CreateQuestBJ(a,b,c,d)
  return CustomSystem()
 end
end)
function main()
 CreateQuestBJ(0,"This is a custom system","","")
end
''')
    assert not r.quests and r.partial
