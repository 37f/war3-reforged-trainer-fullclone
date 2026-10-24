import struct
from dataclasses import replace

import pytest

from war3_current_map_catalog import (MAGIC, RuntimeName, RuntimeDefinition,
    CurrentMapCatalogClient, parse_catalog_header, parse_catalog_page, build_runtime_result)


def raw(text):
    return int.from_bytes(text.encode('ascii'), 'little')


def page(kind=0, token=123, start=0, total=1, names=('地图队长',), custom=1, name_id='H600'):
    data=[MAGIC,1,token,kind,total,start,1,raw('hfoo'),raw(name_id),custom,len(names)]
    for index,name in enumerate(names):
        text=name.encode('utf8'); padded=text+b'\0'*((-len(text))%8)
        data.extend((index,0,0,len(text),*struct.unpack('<'+'Q'*(len(padded)//8),padded)))
    return tuple(data)


def test_header_and_rawcode_case_are_preserved():
    assert parse_catalog_header((MAGIC,1,123,2,1,3))==(123,(2,1,3))
    value=parse_catalog_page(page(),123,'unit',0)
    assert value.records[0].rawcode==b'H600' and value.records[0].base==b'hfoo'
    assert value.records[0].names[0].value=='地图队长'


@pytest.mark.parametrize('values',[(MAGIC,1,0,0,0,0),(MAGIC,2,1,0,0,0),
    (MAGIC,1,1,100001,0,0),(MAGIC,1,1,0,0), (MAGIC,1,1,0,0,0,99)])
def test_invalid_header_rejected(values):
    with pytest.raises(ValueError): parse_catalog_header(values)


@pytest.mark.parametrize('change',[
    lambda p:p[:2]+(124,)+p[3:], lambda p:p[:3]+(1,)+p[4:],
    lambda p:p[:5]+(1,)+p[6:], lambda p:p[:-1], lambda p:p+(0,),
    lambda p:p[:10]+(129,)+p[11:], lambda p:p[:14]+(65537,)+p[15:],
    lambda p:p[:6]+(0,)+p[7:]])
def test_malformed_stale_or_wrong_page_rejected(change):
    with pytest.raises(ValueError): parse_catalog_page(change(page()),123,'unit',0)


def definition(code='H600',base='hfoo',names=('名字',)):
    return RuntimeDefinition(code.encode(),base.encode(),True,tuple(RuntimeName(i,0,0,n) for i,n in enumerate(names)))


def test_inheritance_candidates_and_unsafe_copy_scoped_by_category():
    rows={'unit':(definition(names=('|cffff0000队长|r',)),definition('H601','H600',()),
        definition('H602',names=('甲','乙')),definition('0xAB')),
        'item':(definition('H602',names=('物品',)),),'ability':()}
    result=build_runtime_result(rows)
    units={r.rawcode:r for r in result.entries['unit']}
    assert units['H601'].name=='队长' and '继承' in units['H601'].note
    assert '多个候选' in units['H602'].name and '甲' in units['H602'].note and units['H602'].copyable
    assert not units['0xAB'].copyable
    assert result.entries['item'][0].name=='物品'
    assert result.partial


def test_same_candidate_names_do_not_create_false_ambiguity():
    result=build_runtime_result({'unit':(definition(names=('队长','队长')),),'item':(),'ability':()})
    assert result.entries['unit'][0].name=='队长' and not result.partial


def test_trigstr_cycle_and_duplicate_definitions_are_not_reported_complete():
    result=build_runtime_result({'unit':(definition(names=('TRIGSTR_12',)),
        definition('H601','H602',()),definition('H602','H601',())),'item':(),'ability':()})
    assert result.partial and result.entries['unit'][0].name=='TRIGSTR_12'
    with pytest.raises(ValueError): build_runtime_result({'unit':(definition(),definition())})


def test_client_uses_all_categories_and_final_identity_check_without_selection():
    calls=[]
    def query(op,kind=0,start=0,token=0):
        calls.append((op,kind,start,token))
        return (MAGIC,1,123,1,0,1) if op==318 else page(kind=kind,name_id='A600' if kind==2 else 'H600')
    client=CurrentMapCatalogClient(query,lambda:(1,2))
    snapshot=client.read()
    assert [len(snapshot.result.entries[k]) for k in ('unit','item','ability')]==[1,0,1]
    assert calls==[(318,0,0,0),(319,0,0,123),(319,2,0,123),(318,0,0,0)]
    assert client.check(snapshot)


def test_client_rejects_context_changed_between_pages_and_cancellation():
    headers=iter(((MAGIC,1,123,1,0,0),(MAGIC,1,124,1,0,0)))
    client=CurrentMapCatalogClient(lambda op,**kw:next(headers) if op==318 else page(),lambda:1)
    with pytest.raises(RuntimeError,match='变化'): client.read()
    with pytest.raises(RuntimeError,match='取消'): client.read(lambda:True)


def test_client_rejects_identity_change_and_count_mismatch():
    identities=iter((1,2))
    client=CurrentMapCatalogClient(lambda *a,**kw:(MAGIC,1,123,1,0,0),lambda:next(identities))
    with pytest.raises(RuntimeError,match='连接'): client.read()
    client=CurrentMapCatalogClient(lambda op,**kw:(MAGIC,1,123,2,0,0) if op==318 else page(),lambda:1)
    with pytest.raises(ValueError,match='数量'): client.read()


def test_trainer_bridge_uses_read_only_unbound_operations():
    from unittest.mock import Mock
    import war3_reforged_trainer as module
    trainer=object.__new__(module.War3Trainer);trainer.pid=5;trainer.hwnd=6
    trainer._run_native_helper_ops=Mock(return_value=[module.NativeHelperOpResult(318,0,extra_results=(MAGIC,1,12,0,0,0))])
    client=trainer.current_map_catalog_client()
    assert client.read().counts==(0,0,0)
    assert all(call.args[0]==0 and call.args[1]==((318,0,0,0,0),) for call in trainer._run_native_helper_ops.call_args_list)
    assert trainer.NATIVE_HELPER_VERSION==78


def test_trainer_bridge_explains_menu_and_rejects_closed_connection():
    from unittest.mock import Mock
    import threading
    import war3_reforged_trainer as module
    trainer=object.__new__(module.War3Trainer);trainer.pid=5;trainer.hwnd=6
    trainer._persistent_bootstrap_stop=threading.Event()
    trainer._run_native_helper_ops=Mock(side_effect=RuntimeError('native helper 执行失败：status=3 last_error=21'))
    client=trainer.current_map_catalog_client()
    with pytest.raises(RuntimeError,match='未进入地图'): client.read()
    trainer._persistent_bootstrap_stop.set();trainer._run_native_helper_ops.reset_mock()
    with pytest.raises(RuntimeError,match='关闭'): client.read()
    trainer._run_native_helper_ops.assert_not_called()


def test_catalog_cold_connection_waits_for_persistent_injector_thread():
    from types import SimpleNamespace
    import threading
    import war3_reforged_trainer as module
    trainer=object.__new__(module.War3Trainer);trainer.pid=5;trainer.hwnd=6
    trainer._persistent_bootstrap_stop=threading.Event()
    trainer._persistent_bootstrap_thread=SimpleNamespace(is_alive=lambda:True)
    trainer._native_helper_persistent_hook=None
    def query(*args,**kw):
        assert trainer._native_helper_persistent_hook==1,'short-lived query worker must not own the hook'
        return [module.NativeHelperOpResult(318,0,extra_results=(MAGIC,1,12,0,0,0))]
    trainer._run_native_helper_ops=query
    timer=threading.Timer(.03,lambda:setattr(trainer,'_native_helper_persistent_hook',1));timer.start()
    try: assert trainer.current_map_catalog_client().read().counts==(0,0,0)
    finally:timer.join()
