"""Independent read-only metadata for extensions; existing readers are untouched."""
from contextlib import contextmanager
import struct
import time

from war3_game_profile import profile_scope
from war3_native_table import NativeTable24268


@contextmanager
def read_context(trainer):
    engine=trainer._engine_instance_24268()
    with engine.session.lock:
        with engine.memory_factory(engine.pid) as memory:
            registry,context,mode=engine.session.prepare(memory)
            with profile_scope(engine.session.profile):
                table=NativeTable24268(memory,memory.read_u64(mode.tls+engine.session.profile.section('context')['native_slot']))
                yield engine,memory,registry,mode,table


def player_name(trainer,index):
    if type(index) is not int or not 0<=index<28:return ''
    with read_context(trainer) as (engine,memory,registry,mode,table):
        # Derive the two field offsets from the current getter's instructions.
        # Never execute GetPlayerName's lazy getter or string interner.
        name=table.entries['GetPlayerName'];code=memory.read(name.handler,41)
        if code[:4]!=b'\x48\x83\xec\x28' or code[24]!=0xe8:raise ValueError('玩家名字读取接口尚未核对')
        getter=name.handler+29+struct.unpack_from('<i',code,25)[0]
        body=memory.read(getter,45)
        if body[36:40]!=b'\x48\x83\xc1\x70' or body[40]!=0xe8:raise ValueError('玩家名字字段布局尚未核对')
        accessor=getter+45+struct.unpack_from('<i',body,41)[0]
        if memory.read(accessor,15)!=bytes.fromhex('488b41104885c07405488b4038c3c3'):raise ValueError('玩家名字字符串访问器不同')
        players=registry.players(memory)
        if index>=len(players):return ''
        player=players[index];storage=memory.read_u64(player+0x70+0x10)
        if not storage:return ''
        address=memory.read_u64(storage+0x38)
        if not address:return ''
        raw=bytearray()
        while len(raw)<512:
            data=memory.read(address+len(raw),min(32,512-len(raw),4096-((address+len(raw))&4095)))
            if b'\0' in data:raw.extend(data.split(b'\0',1)[0]);break
            raw.extend(data)
        else:raise ValueError('玩家名字超过读取上限')
        if registry.players(memory)[index]!=player or memory.read_u64(player+0x80)!=storage:raise ValueError('玩家名字读取期间发生变化')
        return bytes(raw).decode('utf8')


def item_snapshot(trainer):
    start=time.monotonic();items=[];seen=set()
    with read_context(trainer) as (engine,memory,registry,mode,table):
        layout=registry.layout;root=memory.read_u64(registry.base+registry.addresses['registry_root'])
        for offset in (layout['primary'],layout['alternate']):
            address=root+offset;pointer=memory.read_u64(address);count=memory.read_u32(address+layout['count'])
            if not 0<count<=1_000_000:raise ValueError('当前地图对象注册表数量超出保护上限')
            for start_index in range(0,count,4096):
                if time.monotonic()-start>10:raise ValueError('地面物品身份读取超过时间上限')
                n=min(4096,count-start_index);data=memory.read(pointer+start_index*layout['stride'],n*layout['stride'])
                for j in range(n):
                    at=j*layout['stride'];marker=struct.unpack_from('<I',data,at)[0]
                    owner=struct.unpack_from('<Q',data,at+layout['slot_owner'])[0]
                    if marker!=0xfffffffe or not owner:continue
                    try:
                        if memory.read_u64(owner+layout['owner_tag'])!=layout['item_tag']:continue
                        obj=memory.read_u64(owner+layout['owner_data']);full=memory.read_u64(obj+layout['object_handle'])
                        rawcode=memory.read_u32(obj+layout['object_rawcode'])
                        if full in seen or not rawcode:continue
                        if registry.resolve_handle(memory,full)!=owner:continue
                        seen.add(full);items.append(dict(full=full,address=obj,rawcode=rawcode))
                        if len(items)>100000:raise ValueError('当前地图物品数量超过100000')
                    except OSError:continue  # A concurrently destroyed object is not a target.
            if memory.read_u64(address)!=pointer or memory.read_u32(address+layout['count'])!=count:raise ValueError('读取期间对象注册表已变化，请重试')
        # FirstOfGroup explicitly sets DL=1, RCX=object then tail-calls this
        # shared object-to-native-handle converter. Verify that complete setup.
        handler=table.entries['FirstOfGroup'].handler;code=memory.read(handler,44)
        if code[30:40]!=bytes.fromhex('b201488bc84883c428e9'):raise ValueError('新版对象句柄转换入口尚未核对')
        converter=handler+44+struct.unpack_from('<i',code,40)[0]
        if not registry.base<=converter<registry.base+engine.session.profile.section('fingerprint')['image_size']:raise ValueError('对象转换接口超出游戏映像')
        return dict(items=items,base=registry.base,converter=converter,item_tag=layout['item_tag'],epoch=engine.session.epoch)


def gather(trainer,preview=False):
    engine=trainer._engine_instance_24268()
    with engine.session.lock:
        snapshot=item_snapshot(trainer)
        x,y=trainer.query_mouse_world_position()
        from war3_fullclone_items_protocol import SIGNATURES,build_work,decode_work
        def build(entries,tls):
            if snapshot['epoch']!=engine.session.epoch:raise ValueError('地图已改变，未移动物品')
            return build_work(entries,tls,**{k:v for k,v in snapshot.items() if k!='epoch'},x=x,y=y,preview=preview)
        return engine._execute('fullclone_items',tuple(n for n,_ in SIGNATURES),build,decode_work,dict(preview=preview))


def current_script(trainer):
    from war3_fullclone_source import current_script as read
    return read(trainer)


def check_source(trainer,proof):
    from war3_fullclone_source import check_source as check
    return check(trainer,proof)


def quest_states(trainer,report,proof):
    from war3_fullclone_source import quest_states as query
    return query(trainer,report,proof)
