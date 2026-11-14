"""Manually run only on the user's authorized Legacy test map.

Production helper performs every tested feature. The separate unshipped helper
is used to select tracked objects and configure a newly created test hero.
"""
from pathlib import Path
import hashlib,json,time
from legacy_backend import LegacyTrainer,Packet,ROOT
events=[]
created=[]
def save(name,result):
    events.append(dict(step=name,result=result))
    (ROOT/'v2-live-acceptance.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),'utf8')
def select(unit,kind=1):
    t=LegacyTrainer();t.native_dir=ROOT/'test-native'
    try:
        t.connect();t._request(9,target=unit['handle'],b=int.from_bytes(unit['type_id'].encode(),'big'),kind=kind)
    finally:t.close()
    time.sleep(.35)
def request(name,fn):
    t=LegacyTrainer()
    try:
        t.connect();r=fn(t);save(name,r)
        if 'created' in r:created.extend(r['created'])
        return r
    except Exception as exc:
        p=Packet.from_buffer_copy(t.mapping[:]) if t.mapping else None
        save(name,dict(error=str(exc),stage=p.stage if p else None,created=list(p.created[:p.created_count]) if p else []));raise
    finally:t.close()
def preview(unit):
    select(unit);return request('preview',lambda t:t.clone_preview())
def ref(h,raw='Ekee'):return dict(handle=h,type_id=raw)
def expect_error(t,fn,text):
    try:fn()
    except RuntimeError as exc:
        assert text in str(exc),str(exc)
        p=Packet.from_buffer_copy(t.mapping[:]);assert p.applied==0 and p.created_count==0
        return dict(expected_error=str(exc),applied=p.applied)
    raise AssertionError('Expected rejection')
def main():
    original=ref(1052131)
    before=preview(original)
    r=request('single_self',lambda t:t.clone_selected());assert len(r['created'])==1
    staging=ref(r['created'][0]);select(staging,2);source=request('configured',lambda t:t.clone_preview())
    assert source['units'][0]['level']==4 and source['detail']['xp']==1100 and source['detail']['points']==1
    r=request('copy_state',lambda t:t.clone_selected());copy=ref(r['created'][0]);after=preview(copy)
    for field in ('level','str','agi','int','hp','max_hp','mp','max_mp'):
        assert source['units'][0][field]==after['units'][0][field],field
    for field in ('xp','points','paused','xp_paused'):assert source['detail'][field]==after['detail'][field],field
    for a,b in zip(source['detail']['items'],after['detail']['items']):
        assert a['handle']!=b['handle']
        assert {k:v for k,v in a.items() if k!='handle'}=={k:v for k,v in b.items() if k!='handle'}
    for a in source['detail']['abilities']:
        if a['flags']&32:continue
        assert any(b['id']==a['id'] and b['level']==a['level'] for b in after['detail']['abilities'])
    neutral=[]
    for slot in (12,15):
        select(staging);r=request('mass_player_'+str(slot+1),lambda t:t.clone_selected(2,'player',slot));assert len(r['created'])==2
        for h in r['created']:
            q=preview(ref(h));assert q['units'][0]['owner']==slot;neutral.append(ref(h))
    select(neutral[-1]);r=request('mass_source_owner',lambda t:t.clone_selected(2,'selected'));assert len(r['created'])==2
    for h in r['created']:assert preview(ref(h))['units'][0]['owner']==15
    select(staging);r=request('mass_ordinary_player2',lambda t:t.clone_selected(2,'player',1))
    for h in r['created']:assert preview(ref(h))['units'][0]['owner']==1
    select(copy);r=request('replace_zhyd',lambda t:t.replace_selected('zhyd'));hydra=ref(r['created'][0],'zhyd');q=preview(hydra)
    assert q['units'][0]['type_id']=='zhyd' and not q['units'][0]['hero']
    assert [a['handle'] for a in after['detail']['items']]==[a['handle'] for a in q['detail']['items']]
    select(staging);r=request('replace_hero',lambda t:t.replace_selected('Hpal'));paladin=ref(r['created'][0],'Hpal');q=preview(paladin)
    assert q['units'][0]['level']==4 and q['detail']['xp']==1100 and q['detail']['points']==1
    assert [a['handle'] for a in source['detail']['items']]==[a['handle'] for a in q['detail']['items']]
    request('invalid_id',lambda t:expect_error(t,lambda:t.replace_selected('ZZZZ'),'创建目标单位'))
    request('inactive_player',lambda t:expect_error(t,lambda:t.clone_selected(1,'player',8),'未在当前地图启用'))
    request('test_operation_not_shipped',lambda t:expect_error(t,lambda:t._request(9),'参数超出'))
    select(original);select(hydra,4);r=request('multi_selection',lambda t:t.clone_selected(2,'self'))
    assert len(r['created'])==4 and len(r['units'])==2
    original_after=preview(original)
    for field in ('level','str','agi','int','max_hp','max_mp'):assert before['units'][0][field]==original_after['units'][0][field]
    assert before['detail']['items']==original_after['detail']['items']
    save('passed',dict(ok=True,production_helper_sha256=hashlib.sha256((ROOT/'legacy32/legacy_bridge32_v2.dll').read_bytes()).hexdigest(),created_handles=created,
        original_preserved=True,gameplay_writes_authorized=True,original_handle=original['handle']))

if __name__=='__main__':main()
