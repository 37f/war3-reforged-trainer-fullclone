"""R31 current-script provenance, isolated from the author's unit readers.

The source/VM fields below are admitted only for the observed exact build.
No old 2.0.4 field is used. Unknown builds retain manual file analysis.
"""
from pathlib import Path,PureWindowsPath
import hashlib
import struct
import tempfile

from war3_object_registry import decode_game_state
from war3_fullclone_runtime import read_context
from war3_fullclone_quests import ScriptSnapshot,_members,_source

BUILD='3.0.1.24371'


def _string(memory,address,limit=4096):
    data=bytearray()
    while len(data)<limit:
        part=memory.read(address+len(data),min(32,limit-len(data),4096-((address+len(data))&4095)))
        if b'\0' in part:return (bytes(data)+part.split(b'\0',1)[0]).decode('utf8')
        data.extend(part)
    raise ValueError('当前地图名称超过读取上限')


def metadata(trainer):
    with read_context(trainer) as (engine,memory,registry,mode,natives):
        if engine.session.profile.data['game_version']!=BUILD:raise ValueError('此游戏小版本的任务来源尚未核对；可以只读分析指定地图文件')
        world=decode_game_state(memory.read_u64(registry.base+registry.addresses['game_state']),engine.session.profile)
        # Direct reference held in the current CGameState, verified read-only
        # against Maps/(2)hillsofglory.w3m in the live 24371 process.
        if memory.read_u64(world)!=registry.base+0x27548e0:raise ValueError('当前地图状态对象类型不同')
        path_record=memory.read_u64(world+0x2ed0)
        name=_string(memory,memory.read_u64(path_record+0x38))
        path=PureWindowsPath(name)
        if path.suffix.casefold() not in ('.w3m','.w3x') or '..' in path.parts or any(ord(c)<32 for c in name):raise ValueError('当前地图来源路径无效')
        host=memory.read_u64(world+0x25d8)
        if memory.read_u64(host)!=registry.base+0x2878890:raise ValueError('当前地图脚本宿主尚未就绪')
        context=memory.read_u64(mode.tls+engine.session.profile.section('context')['native_slot'])
        count=memory.read_u32(context+0xe8);index=memory.read_u32(host+8)
        if not 0<=index<count<=4096:raise ValueError('当前地图脚本上下文无效')
        vm=memory.read_u64(memory.read_u64(context+0xf0)+index*8)
        if memory.read_u64(vm+0x4868)!=host:raise ValueError('当前地图脚本宿主发生变化')
        symbols=memory.read_u64(vm+0x4878)
        if memory.read_u64(world+0x2ed0)!=path_record:raise ValueError('地图读取期间已切换')
        return dict(identity=engine.session.identity,epoch=engine.session.epoch,world=world,
            map_path=name,path_record=path_record,host=host,vm=vm,symbols=symbols,
            module=registry.base,profile=engine.session.profile.id)


def current_script(trainer):
    before=metadata(trainer)
    from war3_fullclone_files import enumerate_game_files,inspect_windows_source_file,_path_parts
    engine=trainer._engine_instance_24268();files=enumerate_game_files(engine.pid)
    name=before['map_path'];parts=_path_parts(name);candidates=[]
    for f in files:
        suffix=PureWindowsPath(f.path).suffix.casefold()
        if suffix in ('.w3m','.w3x') and _path_parts(f.path)[-len(parts):]==parts:candidates.append((f,''))
        elif suffix=='.w3n':
            from war3_mpq import Archive
            try:
                with Archive(f.path) as archive:
                    if archive.read(name,optional=True):candidates.append((f,name))
            except Exception:continue
    if len(candidates)>1:raise ValueError('当前地图实际档案不唯一，未绑定任务')
    source_stamp=None;trusted=True
    if candidates:
        f,chapter=candidates[0];actual=inspect_windows_source_file(path=f.path,pid=engine.pid)
        if actual.file_id!=f.file_id or actual.size!=f.size or actual.modified!=f.modified:raise ValueError('地图文件身份与游戏持有文件不同')
        if f.modified>f.process_created:raise ValueError('地图文件在游戏启动后有过修改，请重开游戏后检索')
        snapshot,_=_source(f.path,chapter);source_stamp=dict(kind='file',path=f.path,id=f.file_id,size=f.size,modified=f.modified)
    else:
        from war3_fullclone_casc import read_build_identity,CascArchive,official_member,_local_file_override_configuration
        root=Path(trainer._executable_path).parent
        for _ in range(5):
            if (root/'.build.info').is_file():break
            root=root.parent
        ident=read_build_identity(root);member=official_member(name)
        with CascArchive(root,ident) as archive:
            raw=archive.read(member)
        if not raw:raise ValueError('未找到当前地图的本地脚本资源')
        from war3_mpq import Archive
        with tempfile.TemporaryDirectory(prefix='war3-r31-source-') as folder:
            path=Path(folder)/'current.w3m';path.write_bytes(raw)
            with Archive(path) as archive:script,wts,language=_members(archive)
        enabled,_,_=_local_file_override_configuration();trusted=not enabled
        origin=str(root)+'::'+member
        if not trusted:origin+='（安装包基础脚本；本地文件覆盖已开启，生效来源未完全确认）'
        snapshot=ScriptSnapshot(script=script,strings_data=wts,language=language,origin=origin,script_sha256=hashlib.sha256(script).hexdigest())
        source_stamp=dict(kind='casc',root=str(root),stamp=ident.stamp,member=member)
    after=metadata(trainer)
    if before!=after:raise ValueError('分析期间当前地图已变化')
    proof=dict(metadata=before,source=source_stamp,trusted=trusted)
    return snapshot,proof


def check_source(trainer,proof):
    if metadata(trainer)!=proof['metadata']:return False
    source=proof['source']
    if source['kind']=='file':
        from war3_fullclone_files import inspect_windows_source_file
        f=inspect_windows_source_file(path=source['path'],pid=trainer.pid)
        return (f.file_id,f.size,f.modified)==(tuple(source['id']),source['size'],source['modified'])
    from war3_fullclone_casc import read_build_identity,_local_file_override_configuration
    if proof.get('trusted') and _local_file_override_configuration()[0]:return False
    return read_build_identity(Path(source['root'])).stamp==tuple(source['stamp'])


def quest_states(trainer,report,proof):
    if not proof.get('trusted'):return {q.key:dict(state='状态未确认',reason='本地文件覆盖已开启，无法将基础脚本与运行中的任务唯一绑定') for q in report.quests}
    from war3_fullclone_status import query_states
    return query_states(trainer,report,proof)
