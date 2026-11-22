"""The ID policy must affect the old relocation payload, never object identity."""
import struct,threading
from types import SimpleNamespace
import pytest
from war3_fullclone_item_filter import parse_filter,filter_items
from war3_fullclone_runtime import gather
from war3_fullclone_items_protocol import SIGNATURES


def raw(code):return int.from_bytes(code.encode('ascii'),'big')


@pytest.fixture
def scene(monkeypatch):
    rows=[dict(full=i+1,address=0x80000+i*16,rawcode=raw(code)) for i,code in enumerate(('I000','i000','ratf'))]
    calls=[];snapshot=dict(items=rows,base=0x40000,converter=0x50000,item_tag=77,epoch=7)
    def capture(trainer):calls.append(('snapshot',));return snapshot
    monkeypatch.setattr('war3_fullclone_runtime.item_snapshot',capture)
    def execute(kind,names,build,decode,request):
        entries={n:SimpleNamespace(name=n,signature=s,handler=0x20000+i*16) for i,(n,s) in enumerate(SIGNATURES)}
        p=bytearray(build(entries,0x30000));n,preview=struct.unpack_from('<2I',p,96)
        identities=[struct.unpack_from('<2QI',p,128+i*64) for i in range(n)]
        calls.append(('payload',kind,identities,request))
        struct.pack_into('<6I',p,96,n,preview,0,1,n,n);return decode(p,n)
    engine=SimpleNamespace(session=SimpleNamespace(lock=threading.RLock(),epoch=7),_execute=execute)
    def mouse():calls.append(('mouse',));return 100.,200.
    trainer=SimpleNamespace(_engine_instance_24268=lambda:engine,query_mouse_world_position=mouse)
    return trainer,rows,calls,engine


@pytest.mark.parametrize('mode,text,indices',[
    ('all','invalid draft',[0,1,2]),('include','I000，ratf',[0,2]),('exclude','I000; ratf',[1]),
    ('include','I000 I000',[0]),('exclude','i000',[0,2]),
])
def test_payload_contains_only_matching_original_identities(scene,mode,text,indices):
    trainer,rows,calls,_=scene;before=[dict(r) for r in rows]
    result=gather(trainer,filter_mode=mode,filter_ids=text)
    packet=next(c for c in calls if c[0]=='payload')
    assert packet[2]==[(rows[i]['full'],rows[i]['address'],rows[i]['rawcode']) for i in indices]
    assert result['changed']==len(indices) and rows==before and packet[1]=='fullclone_items'


def test_no_match_never_moves_anything_or_falls_back_to_all(scene):
    trainer,_,calls,_=scene;result=gather(trainer,filter_mode='include',filter_ids='I999')
    assert result['changed']==0 and calls==[('snapshot',)]


@pytest.mark.parametrize('mode,text',[('include',''),('exclude','abc'),('include','中文物品'),('unknown','I000'),('include','I0000'),('exclude','x'*129)])
def test_bad_filter_is_rejected_before_process_or_mouse_access(scene,mode,text):
    trainer,_,calls,_=scene
    with pytest.raises(ValueError):gather(trainer,filter_mode=mode,filter_ids=text)
    assert not calls


def test_stale_epoch_is_rejected_before_movement(scene):
    trainer,_,calls,engine=scene;engine.session.epoch=8
    with pytest.raises(ValueError,match='地图已改变'):gather(trainer,filter_mode='include',filter_ids='I000')
    assert calls==[('snapshot',)]


def test_filtered_preview_keeps_the_existing_read_only_transaction_flag(scene):
    trainer,_,calls,_=scene;r=gather(trainer,True,filter_mode='include',filter_ids='I000')
    assert r['preview'] and calls[-1][3]==dict(preview=True)
