"""R25: ambiguous bindings, game flag transitions and stale worker rejection."""
from dataclasses import replace
import threading
import time
import pytest

from test_quest_analysis import analyze
from test_quest_ui import Client,pump,SCRIPT
from war3_quest_status import (MAGIC,QuestState,QuestStatusPlan,status_plan,batches,parse_reply,read_states)
from war3_quest_ui import QuestAnalysisController


def reply(token,n,flags=0):
    return (MAGIC,1,token,n)+tuple(v for i in range(n) for v in (0,0x100001+i,0x20000+i*256,11+i,flags))


def test_scalar_bindings_exclude_arrays_locals_and_bj_scratch_globals():
    report=analyze('''globals
quest q=null
quest array qa
quest bj_lastCreatedQuest=null
endglobals
function main takes nothing returns nothing
local quest temporary=null
set q=CreateQuest()
set qa[1]=CreateQuest()
set temporary=CreateQuest()
set bj_lastCreatedQuest=CreateQuest()
endfunction''')
    plan=status_plan(report)
    assert plan.bindings==((report.quests[0].key,('q',)),)
    assert len(plan.unavailable)==3


def test_duplicate_aliases_are_never_guessed():
    report=analyze(SCRIPT);q=report.quests[0]
    report=replace(report,quests=(q,replace(q,key='another')))
    assert not status_plan(report).bindings


@pytest.mark.parametrize('flags,expected',[(0,'active'),(1,'completed'),(2,'failed'),(3,'unconfirmed')])
def test_real_flags_drive_state_even_when_static_script_contains_completion(flags,expected):
    report=analyze(SCRIPT);plan=status_plan(report)
    states=read_states(plan,17,lambda token,words:reply(token,words[0],flags),clock=lambda:42.)
    state=states[report.quests[0].key]
    assert state.state==expected
    assert state.read_at==(0. if flags==3 else 42.)


def test_alias_disagreement_and_shared_runtime_instance_are_unconfirmed():
    plan=QuestStatusPlan((('a',('q','other')),),())
    assert read_states(plan,17,lambda t,w:reply(t,w[0]))['a'].state=='unconfirmed'
    plan=QuestStatusPlan((('a',('q',)),('b',('other',))),())
    data=(MAGIC,1,17,2)+(0,1,0x20000,3,1)*2
    result=read_states(plan,17,lambda t,w:data)
    assert all(s.state=='unconfirmed' for s in result.values())


def test_destroyed_quest_does_not_reuse_the_previous_completed_state():
    plan=QuestStatusPlan((('a',('q',)),),())
    data=(MAGIC,1,17,1,6,0,0,0,0)
    result=read_states(plan,17,lambda t,w:data)
    assert result['a'].state=='unconfirmed' and result['a'].read_at==0


def test_protocol_and_session_mismatch_are_rejected():
    with pytest.raises(RuntimeError):parse_reply(reply(18,1),17,1)
    with pytest.raises(RuntimeError):parse_reply(reply(17,2),17,1)
    with pytest.raises(RuntimeError):parse_reply((MAGIC,1,17,1,0,1,0x20000,3,255),17,1)


def test_names_are_batched_within_existing_ipc_limit_and_never_truncated():
    names=['q'+'x'*126,'q2','q3','q4'+'z'*90]
    actual=[]
    for group,words in batches(names):
        actual.extend(group)
        assert len(words)<=28 and words[0]==len(group)
    assert actual==names
    with pytest.raises(ValueError):list(batches(['q[0]']))


def test_live_failure_preserves_static_report_then_recovers_next_poll():
    client=Client();clock=[100.];calls=[]
    def provider(report,plan,cancelled):
        calls.append(1)
        if len(calls)==1:raise RuntimeError('getter unavailable')
        return {report.quests[0].key:QuestState('completed','',42.)}
    c=QuestAnalysisController(lambda:client,clock=lambda:clock[0],status_provider=provider)
    try:
        pump(c,lambda:c.report is not None and not c.busy)
        original=c.report
        assert c.live_error=='getter unavailable'
        clock[0]+=1.1
        pump(c,lambda:bool(c.live_states))
        assert c.report is original and not c.live_error
        assert next(iter(c.live_states.values())).state=='completed'
    finally:c.close()


@pytest.mark.parametrize('action',['hide','reconnect','cancel','close','map_change'])
def test_late_live_result_cannot_publish_after_context_changes(action):
    client=Client();entered=threading.Event();release=threading.Event()
    def provider(report,plan,cancelled):
        entered.set();release.wait(2)
        return {report.quests[0].key:QuestState('completed','',42.)}
    c=QuestAnalysisController(lambda:client,status_provider=provider)
    c.tick(True);assert entered.wait(2)
    try:
        if action=='hide':c.tick(False)
        elif action=='reconnect':client.connection='other';c.invalidate()
        elif action=='cancel':c.cancel()
        elif action=='close':c.close()
        else:client.token=2;c._auto=False
        release.set()
        deadline=time.monotonic()+2
        while c.busy and time.monotonic()<deadline:
            c.tick(action not in ('hide','reconnect'));time.sleep(.005)
        assert not c.live_states
        assert c.report is None
    finally:release.set();c.close()
