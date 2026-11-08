"""Player directory: independent map fixtures, getter rejection and stale-source gates."""
from contextlib import contextmanager
from types import SimpleNamespace as NS
import struct

import pytest

from war3_player_map_info import parse_player_info,DefinitionError
import war3_player_directory as d


def w3i(version=39,slots=(0,6),mask=0xffffffff):
    """Format-defined fixture, with nonzero padding to detect field drift."""
    i=lambda *v:struct.pack('<'+'i'*len(v),*v)
    text=lambda s:s.encode('utf8')+b'\0'
    raw=i(version,9,7000)
    if version>=27:raw+=i(3,0,1,24371)
    raw+=b''.join(text(s) for s in ('TRIGSTR_1','作者','说明','推荐'))
    raw+=struct.pack('<8f',*range(8))+i(4,4,4,4,96,128,0x100)+b'A'
    if version==18:
        raw+=i(-1)+b''.join(text(s) for s in ('loadtext','loadtitle','subtitle'))
        raw+=i(0)+b''.join(text(s) for s in ('prologuetext','title','subtitle'))
    else:
        raw+=i(-1)
        if version>=39:raw+=i(777)
        raw+=b''.join(text(s) for s in ('path','text','title','sub'))+i(0)
        raw+=b''.join(text(s) for s in ('p-path','p-text','p-title','p-sub'))
        raw+=struct.pack('<i3fI',1,300,5000,0.5,0x11223344)
        if version>=39:raw+=b'F'*24
        if version>=25:raw+=i(123)
        raw+=text('Default')+b'L'+b'RGBA'
        if version>=28:raw+=i(1)
        if version>=31:raw+=i(3,2)
        if version>=32:raw+=struct.pack('<2f',1650,1700)
        if version>=33:raw+=struct.pack('<f',1000)
        if version>=39:raw+=b'W'*40
    raw+=i(len(slots))
    for slot in slots:
        raw+=i(slot,2,4)
        if version>=39:raw+=i(128)
        raw+=i(1)+text('TRIGSTR_2')+struct.pack('<2f',1024,-2048)+struct.pack('<2I',1,64)
        if version>=31:raw+=struct.pack('<2I',2,4)
    raw+=i(1)+struct.pack('<2I',9,mask)+text('TRIGSTR_3')
    return raw


WTS='STRING 1\n{\n测试地图\n}\nSTRING 2\n{\n|cffff0000测试玩家|r\n}\nSTRING 3\n{\n英雄\n}\n'.encode('utf8')


@pytest.mark.parametrize('version',[18,23,24,25,26,27,28,31,32,33,39])
def test_formats_and_unused_force_bits(version):
    raw=w3i(version);r=parse_player_info(raw+b'trailing-upgrades',WTS)
    assert r['parsed_prefix_bytes']==len(raw)
    assert r['map_name']=='测试地图' and r['groups'][0]['name']=='英雄'
    assert r['groups'][0]['members']==[0,6]  # unused mask bits are not players
    p=r['players'][1]
    assert p['name']=='测试玩家' and p['controller']==2 and p['race']==4
    assert p['fixed_start'] and (p['x'],p['y'])==(1024,-2048)
    assert p['skin']==(128 if version==39 else None)
    assert p['enemy_low']==(2 if version>=31 else None)


@pytest.mark.parametrize('raw',[w3i()[:-1],w3i()[:40],w3i(slots=(0,0)),w3i(slots=(32,)),struct.pack('<i',42)])
def test_invalid_config_stops_without_partial_roster(raw):
    with pytest.raises(DefinitionError):parse_player_info(raw)


def test_unresolved_strings_are_explicit():
    r=parse_player_info(w3i())
    assert '文字表缺失' in r['players'][0]['name'] and len(r['issues'])==3


class Memory:
    def __init__(self,data):self.data=data
    def read(self,address,size):return self.data[address][:size]


def getter_fixture():
    code=bytearray(64);code[:5]=bytes.fromhex('4883ec28e8')
    struct.pack_into('<i',code,5,0x5000-0x1000-9)
    code[9:14]=bytes.fromhex('4885c07507')
    code[21:32]=bytes.fromhex('8b80d00400004883c428c3')
    name=bytearray(code);struct.pack_into('<i',name,5,0x5000-0x2000-9)
    return Memory({0x1000:code,0x2000:name}),NS(handler=0x1000,signature='(Hplayer;)Hplayercolor;'),NS(handler=0x2000,signature='(Hplayer;)S')


def test_direct_getter_uses_branch_and_shared_resolver():
    memory,entry,name=getter_fixture()
    assert d.scalar_offset(memory,entry,name,entry.signature)==0x4d0


@pytest.mark.parametrize('change',['signature','resolver','branch','body','alignment','name_signature'])
def test_unrecognized_getters_cannot_admit_offset(change):
    memory,entry,name=getter_fixture();raw=memory.data[entry.handler]
    if change=='signature':entry.signature='()I'
    elif change=='resolver':raw[5]^=1
    elif change=='branch':raw[13]=0x7f
    elif change=='body':raw[29]=0
    elif change=='alignment':raw[23]=0xd1
    else:name.signature='()S'
    with pytest.raises(ValueError):d.scalar_offset(memory,entry,name,'(Hplayer;)Hplayercolor;')


def live_fixture():
    return dict(rows=[dict(id=i,name='游戏名字' if i==0 else '',name_source='游戏读取值',controller=0,race=4,slot_state=1 if i<8 else 0,team=0 if i<4 or i>=24 else 1) for i in range(28)],issues=[],context='1:2:3',profile='fixture')


def test_live_and_map_enum_domains_neutral_and_unassigned():
    live=live_fixture();live['rows'][3]['team']=-1
    cfg=parse_player_info(w3i(slots=(0,6,24)),WTS);cfg.update(trusted=True,origin='fixture')
    r=d.combine(live,cfg);p=r['rows'][0]
    assert p['name']=='游戏名字' and p['controller_label']=='用户'
    assert p['config']['controller_label']=='电脑' and p['config']['skin_label']=='被遗忘者'
    assert p['groups']==['英雄']
    assert next(g for g in r['current_groups'] if g['key']=='team:0')['members']==[0,1,2]
    assert next(g for g in r['current_groups'] if g['key']=='unassigned')['members']==[3]
    assert next(g for g in r['current_groups'] if g['key']=='neutral')['members']==[24,25,26,27]
    assert r['rows'][27]['name']=='中立被动' and '暂无法读取' not in str(r['rows'][27])
    assert 24 not in next(g for g in r['initial_groups'] if g['key']=='config-neutral')['members']


def test_missing_teams_and_config_have_no_invented_membership():
    live=live_fixture()
    for p in live['rows']:p['team']=None
    r=d.combine(live,config_error='尚未进入地图')
    assert not any(g['key'].startswith('team:') for g in r['current_groups'])
    assert r['rows'][0]['config'] is None and not r['source']
    assert any('尚未进入地图' in msg for msg in r['issues'])


def test_team_query_without_selection_does_not_admit_zero_buffer(monkeypatch):
    engine=NS(session=NS(identity=NS(pid=10,created=20),epoch=3,profile=NS(id='fixture')))
    from threading import RLock
    engine.session.lock=RLock();calls=[]
    engine.fullclone=lambda *a,**kw:(calls.append((a,kw)) or dict(rows=[],teams=[0]*28))
    registry=NS(players=lambda m:list(range(28)));table=NS(entries={})
    @contextmanager
    def context(trainer):yield engine,None,registry,None,table
    monkeypatch.setattr(d,'read_context',context);monkeypatch.setattr(d,'player_name',lambda t,i:'')
    r=d.live_players(NS(_engine_instance_24268=lambda:engine))
    assert len(r['rows'])==28 and all(p['team'] is None for p in r['rows'])
    assert calls==[((8,),dict(value=0,target=1))]  # getter-only; no setters


def test_source_cache_cleared_on_refresh_error(monkeypatch):
    engine=NS(session=NS(identity='identity',epoch=3));registry=NS(players=lambda m:[1,2])
    trainer=NS(_engine_instance_24268=lambda:engine)
    api=NS(app=NS(elephant_trainer=lambda:trainer),_player_directory_config=({'origin':'old map'},{}))
    live=live_fixture();live['stamp']=('identity',3,(1,2))
    monkeypatch.setattr(d,'live_players',lambda t:live)
    monkeypatch.setattr(d,'check_source',lambda *a:False)
    monkeypatch.setattr(d,'map_config',lambda t:(_ for _ in ()).throw(ValueError('已换图')))
    @contextmanager
    def context(trainer):yield engine,None,registry,None,None
    monkeypatch.setattr(d,'read_context',context)
    r=d.directory(api)
    assert api._player_directory_config is None and not r['source'] and 'old map' not in str(r)
    engine.session.epoch=4
    with pytest.raises(ValueError,match='地图或连接已变化'):d.directory(api)
