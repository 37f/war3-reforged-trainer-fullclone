"""R23 completion controller checks without Tk or a running game."""
from dataclasses import replace
import threading
import time
from war3_native_quest import QuestRuntimeClient
from test_native_quest import _inspection,_execution,_plan
from test_quest_execution import _report,_script

def report():
    result=_report(_script())
    return replace(result,snapshot=_plan().source_snapshot)

def settle(controller):
    deadline=time.monotonic()+2
    while controller.busy and time.monotonic()<deadline:
        controller.tick();time.sleep(.003)
    controller.tick();assert not controller.busy

def controller(query=None):
    from war3_quest_completion_ui import QuestCompletionController
    calls=[];clock=[10.]
    def transport(request):
        calls.append((request.operation,threading.get_ident()))
        return query(request) if query else _inspection(request) if request.operation=='inspect' else _execution(request)
    client=QuestRuntimeClient(transport,lambda:1,lambda plan:True,clock=lambda:clock[0])
    c=QuestCompletionController(lambda:client,clock=lambda:clock[0])
    return c,calls,clock

def test_selection_and_scan_never_dispatch_and_nonquest_cannot_inspect():
    c,calls,_=controller();r=report()
    c.select(r,'coverage');c.inspect();settle(c)
    assert not calls and not c.can_execute
    c.select(r,r.quests[0].key);assert not calls and not c.can_execute

def test_eligible_quest_preflight_runs_off_caller_thread_and_expires():
    c,calls,clock=controller();r=report();c.select(r,r.quests[0].key)
    c.inspect();settle(c)
    assert c.can_execute and calls==[('inspect',calls[0][1])]
    assert calls[0][1]!=threading.get_ident()
    clock[0]+=2.1;c.tick();assert not c.can_execute
    c.execute();assert len(calls)==1

def test_double_click_starts_one_original_flow():
    c,calls,_=controller();r=report();c.select(r,r.quests[0].key)
    c.inspect();settle(c);c.execute();c.execute();settle(c)
    assert [op for op,_ in calls]==['inspect','execute']
    assert c.result.may_have_run and not c.can_execute
    c.observe();settle(c)
    assert [op for op,_ in calls]==['inspect','execute','status']

def test_source_or_selection_change_clears_execution_proof():
    c,calls,_=controller();r=report();c.select(r,r.quests[0].key)
    c.inspect();settle(c);assert c.can_execute
    c.select(r,'coverage');c.execute();assert len(calls)==1 and not c.can_execute

def test_cancel_after_possible_dispatch_keeps_unknown_instead_of_claiming_cancelled():
    entered=threading.Event();release=threading.Event()
    def query(request):
        if request.operation=='inspect':return _inspection(request)
        entered.set();assert release.wait(2);return _execution(request)
    c,calls,_=controller(query);r=report();c.select(r,r.quests[0].key)
    c.inspect();settle(c);c.execute();assert entered.wait(1)
    c.select(None,None);release.set();settle(c)
    assert c.result.status=='unknown' and c.result.may_have_run
    assert not c.can_execute

def test_complex_original_flow_has_concrete_refusal_and_no_native_query():
    c,calls,_=controller();r=report()
    r=_report(_script(extra='call KillUnit(GetTriggerUnit())'))
    c.select(r,r.quests[0].key);c.inspect();settle(c)
    assert c.plan is not None and not c.plan.eligible and c.message and not calls
