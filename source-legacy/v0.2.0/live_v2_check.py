"""Explicit authorized Legacy test-map driver; never invoked by shipped UI."""
from pathlib import Path
import json
import time
from legacy_backend import LegacyTrainer,Packet,ROOT

REPORT=ROOT/'v2-live-validation.json'
events=[]
def record(name,data):
    events.append(dict(step=name,result=data))
    REPORT.write_text(json.dumps(events,ensure_ascii=False,indent=2),'utf8')
def select(t,unit,kind=1):
    t.snapshot()
    t._request(9,target=unit['handle'],b=int.from_bytes(unit['type_id'].encode(),'big'),kind=kind)
    time.sleep(.3) # Native selection changes settle on the next game frame.
    return t.snapshot()

def main():
    t=LegacyTrainer();t.native_dir=ROOT/'test-native'
    try:
        r=t.connect();record('initial',r)
        source=next(u for u in r['units'] if u['type_id']=='Ekee')
        select(t,source);before=t.clone_preview();record('source',before)
        r=t.clone_selected();record('first_clone',r)
        staging=dict(handle=r['created'][0],type_id='Ekee')
        select(t,staging,2);record('configured_test_clone',t.clone_preview())
        r=t.clone_selected();record('state_copy',r)
        copied=dict(handle=r['created'][0],type_id='Ekee')
        select(t,copied);record('copied_preview',t.clone_preview())
        select(t,staging);r=t.clone_selected(3,'player',15);record('neutral_passive_mass',r)
        for h in r['created']:
            select(t,dict(handle=h,type_id='Ekee'));record('neutral_passive_preview',t.clone_preview())
        select(t,staging);r=t.replace_selected('zhyd');record('replacement',r)
        record('replacement_preview',t.clone_preview())
        select(t,source);record('original_after',t.clone_preview())
    except Exception as exc:
        detail=dict(error=str(exc),details=vars(exc))
        if t.mapping:
            p=Packet.from_buffer_copy(t.mapping[:]);detail.update(native_error=p.error,stage=p.stage,created=list(p.created[:p.created_count]),applied=p.applied)
        record('failure',detail);raise
    finally:t.close()

if __name__=='__main__':main()
