"""Read the current map's World Editor selectable flags for destructibles."""
from pathlib import Path
from tempfile import TemporaryDirectory

from war3_custom_objects import parse_object_data
from war3_fullclone_ai_protocol import MAX_DESTRUCTIBLE_TYPES
from war3_fullclone_casc import CascArchive, CascUnavailable, read_build_identity, official_member
from war3_fullclone_files import inspect_windows_source_file
from war3_fullclone_source import active_map_file, metadata, _official_override
from war3_mpq import Archive
from war3_services.map_catalog import slk_rows

SELECTABLE_FIELD = (b'bgse', 0, 0)
DATA_MEMBER = r'Units\DestructableData.slk'


def selectable_type_ids(stock, layers=()):
    flags = {}
    parents = {}
    for tables, mods in (((stock,), ()), *layers):
        for table in tables:
            for code, row in slk_rows(table).items():
                if 'selectable' in row:
                    flags[code.encode('ascii')] = row['selectable'] == '1'
        for mod in mods:
            for definition in parse_object_data(mod, 'destructible'):
                code = definition.rawcode
                if definition.custom and code != definition.base:
                    parents[code] = definition.base
                if SELECTABLE_FIELD in definition.fields:
                    value = definition.fields[SELECTABLE_FIELD]
                    flags[code] = type(value) is int and value == 1

    def is_selectable(code):
        seen = set()
        while code not in flags and code in parents and code not in seen:
            seen.add(code)
            code = parents[code]
        return flags.get(code, False)

    return tuple(sorted(int.from_bytes(code, 'big')
                        for code in flags.keys() | parents.keys() if is_selectable(code)))


def _layer(archive, prefix):
    tables = [raw for name in (DATA_MEMBER, 'DestructableData.slk')
              if (raw := archive.read(name, optional=True)) is not None]
    if len(tables) > 1 and tables[0] != tables[1]:
        raise ValueError('同一档案的可破坏物表不一致')
    mods = tuple(raw for name in (f'{prefix}.w3b', f'{prefix}Skin.w3b')
                 if (raw := archive.read(name, optional=True)) is not None)
    return tables[:1], mods


def _chapter_layer(data):
    with TemporaryDirectory(prefix='war3-ai-destructibles-') as folder:
        path = Path(folder) / 'chapter.w3x'
        path.write_bytes(data)
        with Archive(path) as archive:
            return _layer(archive, 'war3map')


def read_selectable_types(trainer, session):
    info = metadata(trainer)
    executable = Path(trainer._executable_path).resolve()
    root = next((folder for folder in executable.parents[:5] if (folder / '.build.info').is_file()), None)
    if root is None:
        raise ValueError('找不到游戏本地对象数据')
    identity = read_build_identity(root)
    if identity.version != session.profile.data['game_version']:
        raise ValueError('游戏对象数据版本与当前进程不同')
    if _official_override(root, DATA_MEMBER, ''):
        raise ValueError('无法核对本地覆盖的可破坏物对象数据')

    chosen = active_map_file(trainer, info)
    source = None
    with CascArchive(root, identity) as archive:
        stock = archive.read('war3.w3mod:' + DATA_MEMBER.lower(), max_bytes=2 * 1024 * 1024)
        if not stock:
            raise ValueError('找不到原版可破坏物对象数据')
        if chosen is None:
            if _official_override(root, info['map_path'], ''):
                raise ValueError('无法核对本地覆盖的地图档案')
            source = archive.read(official_member(info['map_path']))
    if chosen is not None:
        game_file, chapter = chosen
        with Archive(game_file.path) as archive:
            if chapter:
                layers = (_layer(archive, 'war3campaign'), _chapter_layer(archive.read(chapter)))
            else:
                layers = (_layer(archive, 'war3map'),)
        actual = inspect_windows_source_file(path=game_file.path, pid=trainer.pid)
        if (actual.file_id, actual.size, actual.modified) != (game_file.file_id, game_file.size, game_file.modified):
            raise ValueError('地图文件在读取期间已变化')
    else:
        if not source:
            raise ValueError('当前地图档案无法核对')
        layers = (_chapter_layer(source),)
    codes = selectable_type_ids(stock, layers)
    if len(codes) > MAX_DESTRUCTIBLE_TYPES:
        raise ValueError('可选中可破坏物类型超过上限')
    if metadata(trainer) != info:
        raise ValueError('读取可破坏物数据期间地图已变化')
    return codes


def selectable_types_for_session(trainer, session):
    key = 'fullclone_ai_selectable_destructibles'
    with session.lock:
        if key not in session.cache:
            try:
                session.cache[key] = read_selectable_types(trainer, session)
            except (CascUnavailable, OSError, ValueError, RuntimeError):
                session.cache[key] = None
        return session.cache[key]
