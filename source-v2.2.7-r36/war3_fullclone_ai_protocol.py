"""Work for one bounded tick of the local player's AI assistance."""
import struct

from war3_selection_protocol import build_work as selection_work, validate_work as validate_selection


SIGNATURES = (
    ('GetPlayerController', '(Hplayer;)Hmapcontrol;'),
    ('ConvertMapControl', '(I)Hmapcontrol;'),
    ('GetPlayerSlotState', '(Hplayer;)Hplayerslotstate;'),
    ('ConvertPlayerSlotState', '(I)Hplayerslotstate;'),
    ('GroupEnumUnitsOfPlayer', '(Hgroup;Hplayer;Hboolexpr;)V'),
    ('GroupEnumUnitsInRangeCounted', '(Hgroup;RRRHboolexpr;I)V'),
    ('GroupClear', '(Hgroup;)V'),
    ('GetOwningPlayer', '(Hunit;)Hplayer;'),
    ('GetUnitCurrentOrder', '(Hunit;)I'),
    ('GetWidgetLife', '(Hwidget;)R'),
    ('IsUnitHidden', '(Hunit;)B'),
    ('IsUnitPaused', '(Hunit;)B'),
    ('IsUnitType', '(Hunit;Hunittype;)B'),
    ('ConvertUnitType', '(I)Hunittype;'),
    ('GetUnitX', '(Hunit;)R'),
    ('GetUnitY', '(Hunit;)R'),
    ('IsUnitEnemy', '(Hunit;Hplayer;)B'),
    ('IsUnitVisible', '(Hunit;Hplayer;)B'),
    ('IsUnitInvisible', '(Hunit;Hplayer;)B'),
    ('IsUnitDetected', '(Hunit;Hplayer;)B'),
    ('BlzIsUnitInvulnerable', '(Hunit;)B'),
    ('IssueTargetOrderById', '(Hunit;IHwidget;)B'),
    ('GetResourceAmount', '(Hunit;)I'),
    ('GetPlayerId', '(Hplayer;)I'),
    ('GetPlayerNeutralPassive', '()I'),
    ('GetPlayerState', '(Hplayer;Hplayerstate;)I'),
    ('ConvertPlayerState', '(I)Hplayerstate;'),
    ('ConvertPathingType', '(I)Hpathingtype;'),
    ('IsTerrainPathable', '(RRHpathingtype;)B'),
    ('IssueBuildOrderById', '(Hunit;IRR)B'),
    ('GetUnitAbilityLevel', '(Hunit;I)I'),
    ('BlzGetUnitAbilityCooldownRemaining', '(Hunit;I)R'),
    ('BlzGetUnitAbilityManaCost', '(Hunit;II)I'),
    ('GetUnitState', '(Hunit;Hunitstate;)R'),
    ('ConvertUnitState', '(I)Hunitstate;'),
    ('BlzGetUnitAbility', '(Hunit;I)Hability;'),
    ('BlzGetAbilityRealLevelField', '(Hability;Habilityreallevelfield;I)R'),
    ('ConvertAbilityRealLevelField', '(I)Habilityreallevelfield;'),
    ('BlzGetUnitMaxHP', '(Hunit;)I'),
    ('IssueImmediateOrderById', '(Hunit;I)B'),
    ('GetPlayerNeutralAggressive', '()I'),
    ('GetPlayerTechCount', '(Hplayer;IB)I'),
    ('GetPlayerTechMaxAllowed', '(Hplayer;I)I'),
    ('BlzGetUnitOrderCount', '(Hunit;)I'),
    ('IsPointBlighted', '(RR)B'),
    ('IssuePointOrderById', '(Hunit;IRR)B'),
    ('Player', '(I)Hplayer;'),
    ('IsPlayerEnemy', '(Hplayer;Hplayer;)B'),
    ('GetPlayerStartLocation', '(Hplayer;)I'),
    ('GetStartLocationX', '(I)R'),
    ('GetStartLocationY', '(I)R'),
    ('GetUnitLevel', '(Hunit;)I'),
)
PICKUP, DESTRUCTIBLES, NEUTRAL_CREATURES, NEUTRAL_BUILDINGS = (1 << i for i in range(8, 12))
WORLD_TARGETS = PICKUP | DESTRUCTIBLES
WORLD_COMMON = (
    ('Location', '(RR)Hlocation;'),
    ('MoveLocation', '(Hlocation;RR)V'),
    ('IsLocationVisibleToPlayer', '(Hlocation;Hplayer;)B'),
    ('RemoveLocation', '(Hlocation;)V'),
)
ITEM_HANDLERS = (
    ('GetItemTypeId', '(Hitem;)I'),
    ('GetItemX', '(Hitem;)R'),
    ('GetItemY', '(Hitem;)R'),
    ('IsItemInvulnerable', '(Hitem;)B'),
    ('IsItemVisible', '(Hitem;)B'),
    ('IsItemOwned', '(Hitem;)B'),
    ('UnitInventorySize', '(Hunit;)I'),
    ('UnitItemInSlot', '(Hunit;I)Hitem;'),
    ('ConvertItemBooleanField', '(I)Hitembooleanfield;'),
    ('BlzGetItemBooleanField', '(Hitem;Hitembooleanfield;)B'),
    ('ConvertUnitIntegerField', '(I)Hunitintegerfield;'),
    ('BlzGetUnitIntegerField', '(Hunit;Hunitintegerfield;)I'),
    ('BlzGetItemAbilityByIndex', '(Hitem;I)Hability;'),
    ('ConvertAbilityIntegerLevelField', '(I)Habilityintegerlevelfield;'),
    ('BlzGetAbilityIntegerLevelField', '(Hability;Habilityintegerlevelfield;I)I'),
)
DESTRUCTIBLE_HANDLERS = (
    ('GetDestructableTypeId', '(Hdestructable;)I'),
    ('GetDestructableX', '(Hdestructable;)R'),
    ('GetDestructableY', '(Hdestructable;)R'),
    ('IsDestructableInvulnerable', '(Hdestructable;)B'),
)
TAIL = struct.Struct('<3Q24I')
TAIL_OFFSET = 480 + 8 * len(SIGNATURES)
HANDLERS = struct.Struct('<' + 'Q' * len(SIGNATURES))
OPENING = struct.Struct('<13I')
OPENING_OFFSET = TAIL_OFFSET + TAIL.size
BATTLE = struct.Struct('<8I')
BATTLE_OFFSET = OPENING_OFFSET + 4 * OPENING.size
BUILD_SITES = struct.Struct('<IffIffIffI')
BUILD_SITES_OFFSET = BATTLE_OFFSET + BATTLE.size
WORLD_OFFSET = BUILD_SITES_OFFSET + BUILD_SITES.size
WORLD = struct.Struct('<25Q')
WORLD_RESULT = struct.Struct('<4I')
WORLD_RESULT_OFFSET = WORLD_OFFSET + WORLD.size
MAX_DESTRUCTIBLE_TYPES = 4096
DESTRUCTIBLE_TYPES_OFFSET = WORLD_RESULT_OFFSET + WORLD_RESULT.size
DESTRUCTIBLE_TYPES = struct.Struct(f'<2I{MAX_DESTRUCTIBLE_TYPES}I')
WORK_SIZE = DESTRUCTIBLE_TYPES_OFFSET + DESTRUCTIBLE_TYPES.size
ABI = struct.pack('<3I', 0x46414911, 216, WORK_SIZE)
WORLD_STAGES = ('', '查询背包', '准备目标缓冲区', '读取对象表', '转换对象句柄',
                '核对对象类型', '读取目标生命', '检查目标状态和坐标', '判断地图视野', '下达游戏指令')
TACTICS = 128
MAX_VISITS = 4096
MAX_UNITS_PER_TICK = 24
AI_RANGE = (900, 1600, 2400, 3200, 4000, 4800, 6400, 9600, 12800, 19200, 25600)
WORKER, AVAILABLE, LOW_FOOD, RESOURCES, HALL, SITE, MINE, BUILDER = (1 << i for i in range(8))
RESEARCH_BUILDING = 256
TRAIN_BUILDING, TRAIN_FOOD, TRAIN_RESOURCES, TRAIN_REJECTED = (1 << i for i in range(9, 13))
BUILD_INTENT, TIER_ORDER = 8192, 16384
REVIVE_ORDER, REVIVE_WAIT = 32768, 65536
BUILD_SUPPLY = 1
BUILD_KINDS = (1, 2, 4, 8, 16, 32, 64)
TRAIN_KINDS = (1, 2, 4, 8, 16)
EMPTY_SITE = (0, 0, 0)


def _valid_site(site):
    code, x, y = site
    return (-1000000 <= x <= 1000000 and -1000000 <= y <= 1000000) if code else not (x or y)


def _opening_payload(openings):
    if not openings:
        return bytes(4 * OPENING.size)
    if len(openings) != 4:
        raise ValueError('开局规则必须对应四个原版种族')
    data = []
    for plan in openings:
        if plan is None:
            data.append(bytes(OPENING.size))
            continue
        workers, steps = plan
        if len(steps) > 4 or any(len(step) != 3 for step in steps):
            raise ValueError('开局建筑规则无效')
        items = [item for step in steps for item in step]
        data.append(OPENING.pack(workers, *items, *([0] * (12 - len(items)))))
    return b''.join(data)


def _valid_openings(payload, features):
    for i in range(4):
        worker_target, *steps = OPENING.unpack_from(payload, OPENING_OFFSET + i * OPENING.size)
        if worker_target > 24 or (worker_target and features & 68 != 68):
            return False
        for kind, count, workers in zip(steps[::3], steps[1::3], steps[2::3]):
            if not (kind or count or workers):
                continue
            if (not worker_target or workers > worker_target or kind not in (1, 2, 4)
                    or not 1 <= count <= (2 if kind == 1 else 1)):
                return False
    return True


def world_signature_groups(features):
    return (
        (WORLD_COMMON, bool(features & WORLD_TARGETS)),
        (ITEM_HANDLERS, bool(features & PICKUP)),
        (DESTRUCTIBLE_HANDLERS, bool(features & DESTRUCTIBLES)),
    )


def build_work(entries, tls, *, owner, cursor, radius=900, features=1, allow_build=False,
               allow_research=False, inspect=False, allow_train=False, blocked_builds=0,
               blocked_train=0, openings=(), wave_troops=(),
               pending_site=EMPTY_SITE, avoid_site=EMPTY_SITE, hero_seed=0, world_base=0, converter=0, selectable_destructibles=()):
    handlers = []
    for name, signature in SIGNATURES:
        entry = entries.get(name)
        if entry is None or entry.name != name or entry.signature != signature:
            raise ValueError('AI 托管接口签名不同：' + name)
        handlers.append(entry.handler)
    world_handlers = []
    for signatures, enabled in world_signature_groups(features if owner and (not inspect or world_base) else 0):
        for name, signature in signatures:
            if not enabled:
                world_handlers.append(0)
                continue
            entry = entries.get(name)
            if entry is None or entry.name != name or entry.signature != signature:
                raise ValueError('AI 托管目标接口签名不同：' + name)
            world_handlers.append(entry.handler)
    if wave_troops and len(wave_troops) != 4:
        raise ValueError('出征规则必须对应四个原版种族')
    selectable_destructibles = tuple(selectable_destructibles)
    type_count = len(selectable_destructibles)
    if (type_count > MAX_DESTRUCTIBLE_TYPES or
            any(type(code) is not int or not 0 < code <= 0xffffffff for code in selectable_destructibles)):
        raise ValueError('可选中可破坏物类型无效或超过上限')
    payload = (selection_work(entries) + HANDLERS.pack(*handlers)
               + TAIL.pack(tls, owner, 0, cursor, radius, features, int(allow_build),
                           int(allow_research), int(inspect), int(allow_train), *([0] * 11),
                           blocked_builds, 0, blocked_train, 0, 0, hero_seed)
               + _opening_payload(openings) + BATTLE.pack(*(wave_troops or (0, 0, 0, 0)), 0, 0, 0, 0)
               + BUILD_SITES.pack(*pending_site, *avoid_site, *EMPTY_SITE, 0)
               + WORLD.pack(world_base, converter, *world_handlers) + bytes(WORLD_RESULT.size)
               + DESTRUCTIBLE_TYPES.pack(type_count, 0, *selectable_destructibles,
                                         *([0] * (MAX_DESTRUCTIBLE_TYPES - type_count))))
    validate_work(payload)
    return payload


def validate_work(payload):
    if len(payload) != WORK_SIZE:
        raise ValueError('AI 托管请求长度无效')
    validate_selection(payload[:480])
    if any(WORLD_RESULT.unpack_from(payload, WORLD_RESULT_OFFSET)):
        raise ValueError('AI 托管的目标结果区必须为空')
    handlers = HANDLERS.unpack_from(payload, 480)
    (tls, expected_owner, owner, cursor, radius, features, allow_build, allow_research,
     inspect, allow_train, *output) = TAIL.unpack_from(payload, TAIL_OFFSET)
    if (any(not 0x10000 <= p < 0x800000000000 for p in (*handlers, tls))
            or tls % 8 or len(set(handlers)) != len(handlers)):
        raise ValueError('AI 托管接口地址无效')
    *result, blocked_builds, built_kind, blocked_train, train_kind, train_wait, hero_seed = output
    *waves, issued, mode, ready, reserved = BATTLE.unpack_from(payload, BATTLE_OFFSET)
    sites = BUILD_SITES.unpack_from(payload, BUILD_SITES_OFFSET)
    world_base, converter, *world_handlers = WORLD.unpack_from(payload, WORLD_OFFSET)
    world_features = features if expected_owner and (not inspect or world_base) else 0
    required = [enabled for signatures, enabled in world_signature_groups(world_features) for _ in signatures]
    has_world = bool(world_features & WORLD_TARGETS)
    type_count, type_reserved, *codes = DESTRUCTIBLE_TYPES.unpack_from(payload, DESTRUCTIBLE_TYPES_OFFSET)
    if (type_reserved or type_count > MAX_DESTRUCTIBLE_TYPES or
            (type_count and (not world_features & DESTRUCTIBLES or not codes[0])) or
            any(a >= b for a, b in zip(codes[:type_count], codes[1:type_count])) or any(codes[type_count:])):
        raise ValueError('可选中可破坏物类型列表无效')
    if (any(bool(addr) != enabled for addr, enabled in zip(world_handlers, required))
            or bool(world_base) != has_world or bool(converter) != has_world
            or any(p and not 0x10000 <= p < 0x800000000000 for p in (world_base, converter, *world_handlers))):
        raise ValueError('AI 托管目标接口地址无效')
    if (cursor >= MAX_VISITS or (not expected_owner and (cursor or allow_build or allow_research or inspect or allow_train))
            or radius not in AI_RANGE or not 1 <= features <= 4095
            or max(waves) > 12 or (any(waves) and not features & TACTICS)
            or issued or mode or ready or reserved
            or not _valid_site(sites[:3]) or not _valid_site(sites[3:6]) or any(sites[6:])
            or (sites[0] and (allow_build or not expected_owner or not features & 4))
            or (sites[3] and not allow_build)
            or any(v not in (0, 1) for v in (inspect, allow_build, allow_research, allow_train))
            or (allow_build and not features & 4) or (allow_research and not features & 16)
            or (allow_train and not features & 64) or owner or any(result) or built_kind
            or blocked_builds & ~127 or (blocked_builds and not allow_build)
            or blocked_train & ~31 or (blocked_train and not allow_train) or train_kind or train_wait
            or (hero_seed and not allow_train) or not _valid_openings(payload, features)):
        raise ValueError('AI 托管请求无效')


def decode_work(payload, count):
    if len(payload) != WORK_SIZE:
        raise RuntimeError('AI 托管结果长度无效')
    (_, expected_owner, owner, cursor, _, features, allow_build, allow_research, inspect, allow_train,
     status, mined, wood, spells, built, researched, creeps, trained, changed,
     error, done, blocked_builds, built_kind, blocked_train, train_kind, train_wait, hero_seed) = TAIL.unpack_from(payload, TAIL_OFFSET)
    *waves, issued, mode, ready, reserved = BATTLE.unpack_from(payload, BATTLE_OFFSET)
    sites = BUILD_SITES.unpack_from(payload, BUILD_SITES_OFFSET)
    ordered_site, build_started = sites[6:9], sites[9]
    world_stage, world_items, world_destructibles, world_reserved = WORLD_RESULT.unpack_from(payload, WORLD_RESULT_OFFSET)
    if error and 0 < world_stage < len(WORLD_STAGES):
        raise RuntimeError(f'AI 托管在「{WORLD_STAGES[world_stage]}」中断（错误 {error:#010x}，已接受 {changed} 条指令）')
    if error == 1001:
        raise RuntimeError('当前没有可托管的本地玩家，请先进入游戏地图')
    if error == 1237:
        raise RuntimeError('本地玩家已变化，AI 托管已停止')
    upgraded = bool(status & TIER_ORDER)
    revive_queued = bool(status & REVIVE_ORDER)
    if (error or done != 1 or not owner or (hero_seed and not allow_train) or (expected_owner and owner != expected_owner)
            or (not expected_owner and (cursor or changed)) or cursor >= MAX_VISITS
            or not 0 <= count == changed <= MAX_UNITS_PER_TICK
            or world_reserved or world_stage >= len(WORLD_STAGES)
            or world_items > 512 or (world_items and not features & PICKUP)
            or world_destructibles > 8192 or (world_destructibles and not features & DESTRUCTIBLES)
            or reserved or mode > 4 or ready > MAX_UNITS_PER_TICK or (issued and not mode)
            or max(waves) > 12 or ((any(waves) or issued or mode or ready) and not features & TACTICS)
            or built not in (0, 1) or (built and not allow_build)
            or not _valid_site(ordered_site) or bool(ordered_site[0]) != bool(built)
            or build_started not in (0, 1) or (build_started and not sites[0])
            or bool(built_kind) != bool(built) or built_kind not in (0, *BUILD_KINDS)
            or blocked_builds & ~127 or blocked_builds & built_kind
            or researched not in (0, 1) or (researched and not allow_research)
            or trained not in (0, 1) or (trained and not allow_train)
            or train_kind not in (0, *TRAIN_KINDS) or blocked_train & ~31 or blocked_train & train_kind
            or bool(train_kind) != bool(trained or upgraded or revive_queued)
            or bool(train_wait) != bool(train_kind)
            or train_wait > 180 or not _valid_openings(payload, features)
            or (upgraded and (trained or not allow_train or not features & 4))
            or ((status & REVIVE_WAIT) and not allow_train)
            or (revive_queued and (trained or upgraded or not status & REVIVE_WAIT or train_kind != 4))
            or (creeps and not features & 32) or status & ~131071
            or mined + wood + spells + built + researched + creeps + trained + upgraded + revive_queued + issued > changed
            or (inspect and changed)):
        raise RuntimeError(f'AI 托管未完成（错误 {error}，已接受 {changed} 条指令）')
    result = dict(owner=owner, cursor=cursor, changed=changed, built=bool(built),
                status=status, mined=mined, wood=wood, spells=spells, researched=researched, creeps=creeps,
                trained=trained, built_kind=built_kind, upgraded=upgraded,
                train_kind=train_kind, train_wait=train_wait)
    if features & TACTICS:
        result.update(tactics_issued=issued, tactics_mode=mode, tactics_ready=ready)
    if built or sites[0]:
        result.update(ordered_site=ordered_site, build_started=bool(build_started))
    if status & REVIVE_WAIT:
        result['revive_queued'] = revive_queued
    if inspect and (world_items or world_destructibles):
        result.update(world_items=world_items, world_destructibles=world_destructibles)
    return result
