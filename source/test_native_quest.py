"""R23 typed runtime-client boundary; no game process is opened."""
from dataclasses import replace
import threading
import pytest

from test_quest_execution import _report,_script
from war3_current_map_script import GameSourceFile,MapSourceMetadata
from war3_quest_execution import build_completion_plan


def _plan(identity=1):
    report=_report(_script())
    source=GameSourceFile('C:/Maps/fixture.w3x',(1,2),1000,10,20,handle=333)
    snapshot=replace(report.snapshot,identity=identity,
        stamp=(MapSourceMetadata(7,'metadata','C:/Maps/fixture.w3x','',False),source))
    report=replace(report,snapshot=snapshot)
    return build_completion_plan(report,report.quests[0].key)


def _inspection(request,**changes):
    reply={'protocol':79,'kind':'inspected','plan_id':request.plan_id,
        'session_token':request.session_token,'helper_epoch':'1'*32,'proof_id':'2'*32,
        'vm':0x600000000,'quest_handle':100,'quest_object':0x600001000,'quest_full':1000,
        'trigger_handle':101,'trigger_object':0x600002000,'trigger_full':1001,
        'bindings_fingerprint':12345,'source_file_id':request.source.file_id,
        'completed':False,'failed':False,'discovered':True}
    reply.update(changes);return reply


def _execution(request,**changes):
    reply={'protocol':79,'kind':'execution-result','plan_id':request.plan_id,
        'session_token':request.session_token,'helper_epoch':'1'*32,
        'request_id':request.request_id,'dispatch_id':request.request_id,
        'status':'dispatched','dispatched':True,'completed':False,
        'message':'原完成流程已派发，等待任务状态读回','error':0,'already_dispatched':False}
    reply.update(changes);return reply


def test_readonly_inspection_binds_current_source_and_exact_task_without_dispatch():
    from war3_native_quest import QuestRuntimeClient
    requests=[];plan=_plan('connection')
    def query(request):requests.append(request);return _inspection(request)
    client=QuestRuntimeClient(query,lambda:'connection',lambda p:True,clock=lambda:100)
    proof=client.inspect(plan)
    assert len(requests)==1 and requests[0].operation=='inspect'
    assert requests[0].source.handle==333 and requests[0].quest_alias=='udg_QUEST'
    assert proof.quest_full==1000 and proof.connection_identity=='connection'
    assert proof.plan_id==requests[0].plan_id and not proof.completed


@pytest.mark.parametrize('changes',[
    {'session_token':8},{'source_file_id':(1,3)},{'quest_handle':0},
    {'quest_object':0x600001001},{'helper_epoch':'bad'},{'completed':1},
    {'bindings_fingerprint':0},{'protocol':78},
])
def test_malformed_or_stale_runtime_proof_is_rejected(changes):
    from war3_native_quest import QuestRuntimeClient
    client=QuestRuntimeClient(lambda r:_inspection(r,**changes),lambda:1,lambda p:True)
    with pytest.raises((ValueError,RuntimeError)):client.inspect(_plan())


@pytest.mark.parametrize('state',['completed','failed'])
def test_completed_or_failed_task_cannot_obtain_an_executable_proof(state):
    from war3_native_quest import QuestRuntimeClient
    client=QuestRuntimeClient(lambda r:_inspection(r,**{state:True}),lambda:1,lambda p:True)
    with pytest.raises(RuntimeError):client.inspect(_plan())


def test_expired_proof_is_rejected_before_transport():
    from war3_native_quest import QuestRuntimeClient
    clock=[100.];requests=[];plan=_plan()
    def query(r):requests.append(r);return _inspection(r)
    client=QuestRuntimeClient(query,lambda:1,lambda p:True,clock=lambda:clock[0])
    proof=client.inspect(plan);clock[0]=102.1
    result=client.execute(plan,proof,'3'*32)
    assert result.status=='rejected-before-dispatch' and len(requests)==1


@pytest.mark.parametrize('change',['source','connection'])
def test_changed_source_or_connection_rejects_execution_before_transport(change):
    from war3_native_quest import QuestRuntimeClient
    identity=[1];valid=[True];requests=[];plan=_plan()
    def query(r):requests.append(r);return _inspection(r)
    client=QuestRuntimeClient(query,lambda:identity[0],lambda p:valid[0])
    proof=client.inspect(plan)
    if change=='source':valid[0]=False
    else:identity[0]=2
    assert client.execute(plan,proof,'3'*32).status=='rejected-before-dispatch'
    assert len(requests)==1


def test_timeout_after_possible_dispatch_is_unknown_and_never_automatically_retried():
    from war3_native_quest import QuestRuntimeClient
    requests=[];plan=_plan()
    def query(r):
        requests.append(r)
        if r.operation=='inspect':return _inspection(r)
        raise TimeoutError('reply lost after dispatch may have happened')
    client=QuestRuntimeClient(query,lambda:1,lambda p:True)
    proof=client.inspect(plan)
    first=client.execute(plan,proof,'3'*32)
    second=client.execute(plan,proof,'4'*32)
    assert first.status=='unknown' and first.may_have_run
    assert second.status=='unknown'
    assert [r.operation for r in requests]==['inspect','execute']


def test_double_click_cannot_start_two_dispatch_calls_while_first_reply_is_pending():
    from war3_native_quest import QuestRuntimeClient
    entered=threading.Event();release=threading.Event();requests=[];plan=_plan()
    def query(r):
        requests.append(r)
        if r.operation=='inspect':return _inspection(r)
        entered.set();assert release.wait(3);return _execution(r)
    client=QuestRuntimeClient(query,lambda:1,lambda p:True)
    proof=client.inspect(plan);results=[]
    thread=threading.Thread(target=lambda:results.append(client.execute(plan,proof,'3'*32)))
    thread.start()
    try:
        assert entered.wait(3)
        second=client.execute(plan,proof,'4'*32)
        assert second.may_have_run
    finally:release.set();thread.join(3)
    assert len(results)==1 and results[0].status=='dispatched'
    assert sum(r.operation=='execute' for r in requests)==1


def test_inconsistent_completed_reply_is_unknown_and_does_not_enable_retry():
    from war3_native_quest import QuestRuntimeClient
    requests=[];plan=_plan()
    def query(r):
        requests.append(r)
        return _inspection(r) if r.operation=='inspect' else _execution(r,status='observed-completed',completed=False)
    client=QuestRuntimeClient(query,lambda:1,lambda p:True)
    proof=client.inspect(plan)
    assert client.execute(plan,proof,'3'*32).status=='unknown'
    assert client.execute(plan,proof,'4'*32).status=='unknown'
    assert sum(r.operation=='execute' for r in requests)==1


def test_helper_epoch_change_during_dispatch_is_unknown():
    from war3_native_quest import QuestRuntimeClient
    plan=_plan()
    def query(r):return _inspection(r) if r.operation=='inspect' else _execution(r,helper_epoch='5'*32)
    client=QuestRuntimeClient(query,lambda:1,lambda p:True);proof=client.inspect(plan)
    assert client.execute(plan,proof,'3'*32).status=='unknown'


def test_requery_retiring_catalog_token_cannot_make_same_live_quest_retryable():
    from war3_native_quest import QuestRuntimeClient
    requests=[];plan=_plan()
    def query(r):
        requests.append(r)
        return _inspection(r) if r.operation=='inspect' else _execution(r)
    client=QuestRuntimeClient(query,lambda:1,lambda p:True)
    first=client.inspect(plan);assert client.execute(plan,first,'3'*32).status=='dispatched'
    snapshot=replace(plan.source_snapshot,session_token=8,
        stamp=(replace(plan.source_snapshot.stamp[0],session_token=8),plan.source_snapshot.stamp[1]))
    refreshed=replace(plan,snapshot_token=8,source_snapshot=snapshot)
    second=client.inspect(refreshed)
    assert client.execute(refreshed,second,'4'*32).status=='dispatched'
    assert sum(r.operation=='execute' for r in requests)==1


def test_missing_game_owned_source_handle_is_not_replaced_with_a_host_file_handle():
    from war3_native_quest import QuestRuntimeClient
    plan=_plan();snapshot=plan.source_snapshot
    plan=replace(plan,source_snapshot=replace(snapshot,stamp=(snapshot.stamp[0],replace(snapshot.stamp[1],handle=0))))
    client=QuestRuntimeClient(lambda r:pytest.fail('unbound source must not reach native transport'),lambda:1,lambda p:True)
    with pytest.raises(RuntimeError):client.inspect(plan)


def _wire_reply(request):
    import struct
    digest=lambda text:struct.unpack('<'+'Q'*(len(text)//16),bytes.fromhex(text))
    return (0x31515352,1,0,request.session_token,*digest(request.plan_id),
        *digest('1'*32),*digest('2'*32),0x600000000,100,0x600001000,1000,
        101,0x600002000,1001,12345,*request.source.file_id,4,0,0,0,0,0,0,0,0,0)


def test_native_wire_carries_only_bounded_names_and_verified_source_identity():
    from war3_native_quest import QuestRuntimeClient,encode_quest_request,decode_quest_response
    captured=[]
    def query(request):
        words=encode_quest_request(request);captured.append(words)
        assert words[:10]==(0x31515352,1,0,7,333,1,2,1000,10,20)
        assert len(words)<=8192
        return decode_quest_response(request,_wire_reply(request))
    client=QuestRuntimeClient(query,lambda:1,lambda p:True)
    assert client.inspect(_plan()).quest_full==1000 and len(captured)==1


@pytest.mark.parametrize('change',[
    lambda words:words[:-1],lambda words:words+(0,),
    lambda words:(0,)+words[1:],lambda words:words[:1]+(99,)+words[2:],
    lambda words:words[:22]+(128,)+words[23:],
    lambda words:words[:31]+(1,),
])
def test_native_wire_rejects_unsupported_shape_or_flags(change):
    from war3_native_quest import QuestRuntimeClient,decode_quest_response
    client=QuestRuntimeClient(lambda request:decode_quest_response(request,change(_wire_reply(request))),
        lambda:1,lambda p:True)
    with pytest.raises((ValueError,RuntimeError)):client.inspect(_plan())


def test_observation_never_redispatches_original_flow():
    from war3_native_quest import QuestRuntimeClient
    operations=[]
    def query(request):
        operations.append(request.operation)
        if request.operation=='inspect':return _inspection(request)
        return _execution(request,**({'status':'observed-completed','completed':True}
            if request.operation=='status' else {}))
    client=QuestRuntimeClient(query,lambda:1,lambda p:True)
    plan=_plan();proof=client.inspect(plan);request_id='3'*32
    assert client.execute(plan,proof,request_id).status=='dispatched'
    result=client.observe(plan,proof,request_id)
    assert result.status=='observed-completed'
    assert operations==['inspect','execute','status']
    assert client.execute(plan,proof,'4'*32).status=='observed-completed'
    assert operations==['inspect','execute','status']


def test_observation_requires_an_existing_possibly_dispatched_request():
    from war3_native_quest import QuestRuntimeClient
    operations=[]
    def query(request):operations.append(request.operation);return _inspection(request)
    client=QuestRuntimeClient(query,lambda:1,lambda p:True)
    plan=_plan();proof=client.inspect(plan)
    assert client.observe(plan,proof,'3'*32).status=='rejected-before-dispatch'
    assert operations==['inspect']
