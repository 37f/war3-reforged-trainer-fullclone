"""Behavior tests for the R12 unit transactions on the persistent helper."""
import ctypes
import faulthandler
from pathlib import Path
import shutil
import struct
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import war3_reforged_trainer as module


def candidate():
    return SimpleNamespace(
        unit_address=0x5000,
        handle=0x123400005678,
        owner_address=0x7000,
    )


def result(kind=0, value=0, arg0=0, arg1=0):
    return module.NativeHelperOpResult(
        kind=kind,
        result=value,
        arg0=arg0,
        arg1=arg1,
    )


def trainer_with_response(*responses):
    trainer = module.War3Trainer.__new__(module.War3Trainer)
    trainer.pid = 4321
    trainer._unit_pathing_states = {}
    trainer._elephant_selection_override = None
    trainer._direct_selected_context = Mock(return_value=(candidate(), 7))
    trainer._run_native_helper_ops = Mock(side_effect=responses)
    return trainer


def guard_operation():
    return (136, 0, 0x5000, 0x123400005678, 0x7000)


def test_replace_unit_is_one_bound_persistent_transaction():
    trainer = trainer_with_response([
        result(136),
        result(311, 8),
    ])

    assert trainer.replace_selected_unit("hfoo") == (0x68666F6F, 8)

    call = trainer._run_native_helper_ops.call_args
    assert call.args == (
        7,
        (guard_operation(), (311, 0x68666F6F, 0, 0, 0)),
    )
    assert call.kwargs["timeout_ms"] == 10000


def test_invalid_replacement_stops_before_transport():
    trainer = trainer_with_response()

    with pytest.raises(ValueError, match="替换单位 ID 无效"):
        trainer.replace_selected_unit(0)

    trainer._direct_selected_context.assert_not_called()
    trainer._run_native_helper_ops.assert_not_called()


def test_revive_selected_owner_uses_one_captured_mouse_point():
    trainer = trainer_with_response([
        result(136),
        result(305, 3, arg0=4),
    ])
    trainer.query_mouse_world_position = Mock(return_value=(12.5, -7.25))

    assert trainer.revive_selected_owner_dead_heroes_at_mouse() == 3

    coordinates = struct.unpack("<Q", struct.pack("<ff", 12.5, -7.25))[0]
    call = trainer._run_native_helper_ops.call_args
    assert call.args == (
        7,
        (guard_operation(), (305, 0, 0, coordinates, 0)),
    )
    trainer.query_mouse_world_position.assert_called_once_with()


@pytest.mark.parametrize(
    ("mask", "expected"),
    [
        (1, (1, 0)),
        (3, (1, 1)),
    ],
)
def test_fill_vitals_reports_life_and_optional_mana(mask, expected):
    trainer = trainer_with_response([
        result(136),
        result(306, mask, arg0=725, arg1=0 if mask == 1 else 350),
    ])

    assert trainer.fill_selected_unit_life_and_mana() == expected
    assert trainer._run_native_helper_ops.call_args.args == (
        7,
        (guard_operation(), (306, 0, 0, 0, 0)),
    )


def test_pathing_toggle_uses_process_and_stable_unit_identity():
    trainer = trainer_with_response()
    trainer._run_elephant_unit_bool = Mock()

    assert trainer.toggle_selected_unit_pathing() is False
    assert trainer._unit_pathing_states == {(4321, 0x123400005678): False}
    assert trainer.toggle_selected_unit_pathing() is True
    assert trainer._unit_pathing_states == {(4321, 0x123400005678): True}
    assert trainer._run_elephant_unit_bool.call_args_list[0].args == (
        "SetUnitPathing",
        False,
    )


def test_failed_pathing_write_does_not_change_confirmed_state():
    trainer = trainer_with_response()
    trainer._run_elephant_unit_bool = Mock(side_effect=RuntimeError("native failed"))

    with pytest.raises(RuntimeError, match="native failed"):
        trainer.toggle_selected_unit_pathing()

    assert trainer._unit_pathing_states == {}


def test_process_change_discards_pathing_state():
    source = open(module.__file__, encoding="utf-8").read()
    refresh = source[
        source.index("    def refresh_window"):
        source.index("    def _close_native_helper_persistent")
    ]
    assert "self._unit_pathing_states = {}" in refresh


UNIT_HARNESS = r'''
#include <windows.h>
#include <wchar.h>
static wchar_t test_directory[MAX_PATH];
static DWORD fake_temp_path(DWORD count, wchar_t *path) {
    size_t length = wcslen(test_directory);
    if (length + 1 >= count) return 0;
    memcpy(path, test_directory, (length + 1) * sizeof(wchar_t));
    return (DWORD)length;
}
#define GetTempPathW fake_temp_path
#include "HELPER_SOURCE"
#undef GetTempPathW

static uint8_t source_object[0x20], source_owner[0xc0];
static const uint64_t source_full = 0x123400005678ULL;
static unsigned source_removed, target_removed, target_created;
static unsigned mana_writes, revive_calls, revive_index;
static int scenario;
static uint32_t active_kind;
static float current_life, current_mana, revived_x, revived_y;

static uint64_t unit_resolver(uint64_t handle) {
    return handle == 7 ? (uint64_t)(uintptr_t)source_object : 0;
}
static uint64_t agent_resolver(uint32_t slot, uint32_t serial) {
    if (slot == (uint32_t)source_full && serial == (uint32_t)(source_full >> 32))
        return (uint64_t)(uintptr_t)source_owner;
    return 0;
}
static uint64_t get_owner(uint64_t unit) { return unit ? 2 : 0; }
static uint32_t real_bits(float value) { uint32_t bits; memcpy(&bits, &value, 4); return bits; }
static uint32_t get_x(uint64_t unit) { (void)unit; return real_bits(10.0f); }
static uint32_t get_y(uint64_t unit) { (void)unit; return real_bits(20.0f); }
static uint32_t get_facing(uint64_t unit) { (void)unit; return real_bits(90.0f); }
static uint32_t get_state(uint64_t unit, int32_t state) {
    float value = 0.0f;
    if (active_kind == WAR3_NATIVE_OP_EXT_FILL_UNIT_VITALS) {
        value = state == 2 ? current_mana : state == 0 ? current_life : 0.0f;
        return real_bits(value);
    }
    if (unit == 7) value = state == 0 ? 50.0f : state == 1 ? 100.0f : state == 2 ? 25.0f : 50.0f;
    else value = state == 0 ? current_life : state == 1 ? 200.0f : state == 2 ? current_mana : 100.0f;
    return real_bits(value);
}
static void set_state(uint64_t unit, int32_t state, float *value) {
    (void)unit;
    if (state == 0) current_life = *value;
    if (state == 2) { current_mana = *value; ++mana_writes; }
}
static int32_t max_hp(uint64_t unit) { (void)unit; return 725; }
static int32_t max_mana(uint64_t unit) { (void)unit; return scenario == 4 ? 0 : 350; }
static void set_life(uint64_t unit, float *value) { (void)unit; current_life = *value; }
static uint32_t get_life(uint64_t unit) { (void)unit; return real_bits(current_life); }
static uint64_t create_unit(uint64_t owner, uint32_t rawcode, float *x, float *y, float *facing) {
    (void)owner; (void)rawcode; (void)x; (void)y; (void)facing;
    if (scenario == 1) return 0;
    target_created = 1;
    return 8;
}
static uint32_t get_type(uint64_t unit) {
    if (unit == 7) return 0x68666f6fu;
    return scenario == 2 ? 0x68626164u : 0x68706561u;
}
static void remove_unit(uint64_t unit) {
    if (unit == 7) source_removed = 1;
    if (unit == 8) target_removed = 1;
}
static int32_t get_hero_xp(uint64_t unit) { (void)unit; return 0; }
static void set_hero_xp(uint64_t unit, int32_t xp, uint32_t effect) { (void)unit; (void)xp; (void)effect; }
static uint32_t is_unit_type(uint64_t unit, uint64_t type) { (void)unit; (void)type; return 0; }
static uint64_t convert_unit_type(int32_t type) { return 100u + (uint64_t)type; }
static uint64_t item_in_slot(uint64_t unit, int32_t slot) { (void)unit; (void)slot; return 0; }
static void unit_remove_item(uint64_t unit, uint64_t item) { (void)unit; (void)item; }
static uint32_t unit_add_item(uint64_t unit, uint64_t item) { (void)unit; (void)item; return 1; }
static uint32_t is_hidden(uint64_t unit) { (void)unit; return 0; }
static void show_unit(uint64_t unit, uint32_t show) { (void)unit; (void)show; }
static void kill_unit(uint64_t unit) { (void)unit; }
static uint64_t create_mine(uint64_t owner, float *x, float *y, float *facing) {
    return create_unit(owner, 0x75676f6cu, x, y, facing);
}
static int32_t get_resource(uint64_t unit) { (void)unit; return 12345; }
static void set_resource(uint64_t unit, int32_t amount) { (void)unit; (void)amount; }
static uint64_t create_group(void) { revive_index = 0; return 99; }
static void enum_units(uint64_t group, uint64_t owner, uint64_t filter) {
    (void)group; (void)owner; (void)filter; revive_index = 0;
}
static uint64_t first_group(uint64_t group) {
    (void)group;
    static const uint64_t units[] = {10, 11, 12, 0};
    return units[revive_index];
}
static void group_remove(uint64_t group, uint64_t unit) { (void)group; (void)unit; ++revive_index; }
static void destroy_group(uint64_t group) { (void)group; }
static uint32_t revive_is_type(uint64_t unit, uint64_t type) {
    if (type == 100) return unit == 10 || unit == 11;
    if (type == 101) return unit == 10 || unit == 12;
    return 0;
}
static uint32_t revive_hero(uint64_t unit, float *x, float *y, uint32_t effect) {
    (void)unit; (void)effect; ++revive_calls; revived_x = *x; revived_y = *y; return 1;
}
static void bind_native(const char *name, uint64_t handler) {
    for (unsigned i = 0; i < sizeof(g_persistent_natives) / sizeof(g_persistent_natives[0]); ++i) {
        g_persistent_natives[i].name = g_persistent_native_names[i];
        if (!strcmp(g_persistent_native_names[i], name)) g_persistent_natives[i].handler = handler;
    }
}
static void setup(void) {
    ZeroMemory(g_persistent_natives, sizeof(g_persistent_natives));
    bind_native("GetOwningPlayer", (uint64_t)(uintptr_t)get_owner);
    bind_native("GetUnitX", (uint64_t)(uintptr_t)get_x);
    bind_native("GetUnitY", (uint64_t)(uintptr_t)get_y);
    bind_native("GetUnitFacing", (uint64_t)(uintptr_t)get_facing);
    bind_native("GetUnitState", (uint64_t)(uintptr_t)get_state);
    bind_native("SetUnitState", (uint64_t)(uintptr_t)set_state);
    bind_native("BlzGetUnitMaxHP", (uint64_t)(uintptr_t)max_hp);
    bind_native("BlzGetUnitMaxMana", (uint64_t)(uintptr_t)max_mana);
    bind_native("SetWidgetLife", (uint64_t)(uintptr_t)set_life);
    bind_native("GetWidgetLife", (uint64_t)(uintptr_t)get_life);
    bind_native("CreateUnit", (uint64_t)(uintptr_t)create_unit);
    bind_native("GetUnitTypeId", (uint64_t)(uintptr_t)get_type);
    bind_native("RemoveUnit", (uint64_t)(uintptr_t)remove_unit);
    bind_native("GetHeroXP", (uint64_t)(uintptr_t)get_hero_xp);
    bind_native("SetHeroXP", (uint64_t)(uintptr_t)set_hero_xp);
    bind_native("IsUnitType", (uint64_t)(uintptr_t)(scenario == 3 ? revive_is_type : is_unit_type));
    bind_native("ConvertUnitType", (uint64_t)(uintptr_t)convert_unit_type);
    bind_native("UnitItemInSlot", (uint64_t)(uintptr_t)item_in_slot);
    bind_native("UnitRemoveItem", (uint64_t)(uintptr_t)unit_remove_item);
    bind_native("UnitAddItem", (uint64_t)(uintptr_t)unit_add_item);
    bind_native("IsUnitHidden", (uint64_t)(uintptr_t)is_hidden);
    bind_native("ShowUnit", (uint64_t)(uintptr_t)show_unit);
    bind_native("KillUnit", (uint64_t)(uintptr_t)kill_unit);
    bind_native("CreateBlightedGoldmine", (uint64_t)(uintptr_t)create_mine);
    bind_native("GetResourceAmount", (uint64_t)(uintptr_t)get_resource);
    bind_native("SetResourceAmount", (uint64_t)(uintptr_t)set_resource);
    bind_native("CreateGroup", (uint64_t)(uintptr_t)create_group);
    bind_native("GroupEnumUnitsOfPlayer", (uint64_t)(uintptr_t)enum_units);
    bind_native("FirstOfGroup", (uint64_t)(uintptr_t)first_group);
    bind_native("GroupRemoveUnit", (uint64_t)(uintptr_t)group_remove);
    bind_native("DestroyGroup", (uint64_t)(uintptr_t)destroy_group);
    bind_native("ReviveHero", (uint64_t)(uintptr_t)revive_hero);
}
__declspec(dllexport) DWORD unit_transaction_test(
    const wchar_t *directory, uint32_t kind, uint32_t selected_scenario, uint32_t *out
) {
    NativeCommand cmd = {0}; wchar_t path[MAX_PATH]; DWORD bytes = 0; HANDLE file;
    wcscpy(test_directory, directory); scenario = (int)selected_scenario; active_kind = kind;
    source_removed = target_removed = target_created = mana_writes = revive_calls = 0;
    current_life = current_mana = revived_x = revived_y = 0.0f;
    ZeroMemory(source_object, sizeof(source_object)); ZeroMemory(source_owner, sizeof(source_owner));
    *(uint64_t *)(source_object + 0x18) = source_full;
    *(uint64_t *)(source_owner + 0x18) = 0x2b7733752b61676cULL;
    *(uint64_t *)(source_owner + 0x20) = source_full;
    *(uint64_t *)(source_owner + 0x90) = (uint64_t)(uintptr_t)source_object;
    g_persistent_unit_resolver = (uint64_t)(uintptr_t)unit_resolver;
    g_persistent_agent_resolver = (uint64_t)(uintptr_t)agent_resolver;
    setup();
    cmd.magic = WAR3_NATIVE_MAGIC; cmd.version = WAR3_NATIVE_VERSION;
    cmd.status = WAR3_NATIVE_STATUS_PENDING; cmd.op_count = 2; cmd.unit_handle = 7;
    cmd.ops[0].kind = WAR3_NATIVE_OP_VALIDATE_UNIT_IDENTITY;
    cmd.ops[0].handler = (uint64_t)(uintptr_t)source_object;
    cmd.ops[0].arg0 = source_full; cmd.ops[0].arg1 = (uint64_t)(uintptr_t)source_owner;
    cmd.ops[1].kind = kind;
    if (kind == WAR3_NATIVE_OP_EXT_REPLACE_UNIT) cmd.ops[1].rawcode = 0x68706561u;
    if (kind == WAR3_NATIVE_OP_EXT_REVIVE_SELECTED_OWNER_HEROES)
        cmd.ops[1].arg0 = ((uint64_t)real_bits(-7.25f) << 32) | real_bits(12.5f);
    command_path(path, MAX_PATH);
    file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0, NULL, CREATE_NEW, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) return GetLastError();
    if (!WriteFile(file, &cmd, sizeof(cmd), &bytes, NULL)) { CloseHandle(file); return ERROR_WRITE_FAULT; }
    CloseHandle(file); run_command();
    file = CreateFileW(path, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) return GetLastError();
    if (!ReadFile(file, &cmd, sizeof(cmd), &bytes, NULL)) { CloseHandle(file); return ERROR_READ_FAULT; }
    CloseHandle(file); DeleteFileW(path);
    out[0]=cmd.status; out[1]=cmd.last_error; out[2]=cmd.ops[1].last_error;
    out[3]=(uint32_t)cmd.ops[1].result; out[4]=source_removed; out[5]=target_removed;
    out[6]=target_created; out[7]=mana_writes; out[8]=revive_calls;
    out[9]=(uint32_t)current_life; out[10]=(uint32_t)current_mana;
    out[11]=(uint32_t)(revived_x * 100.0f); out[12]=(uint32_t)(-revived_y * 100.0f);
    return ERROR_SUCCESS;
}
'''


@pytest.fixture(scope="module")
def native_transactions(tmp_path_factory):
    compiler = shutil.which("clang")
    if not compiler:
        pytest.skip("Microsoft-SEH-capable clang is required")
    root = tmp_path_factory.mktemp("fullclone-unit-transactions")
    helper = Path(__file__).parent / "tools" / "war3_native_helper.c"
    source = root / "unit_transactions.c"
    source.write_text(
        UNIT_HARNESS.replace("HELPER_SOURCE", helper.as_posix()),
        encoding="utf-8",
    )
    library = root / "unit_transactions.dll"
    build = subprocess.run(
        [compiler, "-shared", "-O2", "-Wno-microsoft-goto", str(source),
         "-o", str(library), "-luser32", "-lkernel32"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert build.returncode == 0, build.stderr
    native = ctypes.CDLL(str(library))
    native.unit_transaction_test.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_uint),
    ]
    native.unit_transaction_test.restype = ctypes.c_uint
    yield native
    import _ctypes
    _ctypes.FreeLibrary(native._handle)


def run_native(native, directory, kind, scenario=0):
    directory.mkdir(exist_ok=True)
    out = (ctypes.c_uint * 13)()
    enabled = faulthandler.is_enabled()
    try:
        faulthandler.disable()
        assert native.unit_transaction_test(str(directory) + "\\", kind, scenario, out) == 0
    finally:
        if enabled:
            faulthandler.enable()
    return tuple(out)


def test_native_replacement_commits_only_after_new_unit_is_valid(native_transactions, tmp_path):
    values = run_native(native_transactions, tmp_path / "replace-ok", 311)
    assert values[:7] == (2, 0, 0, 8, 1, 0, 1)


@pytest.mark.parametrize(
    ("scenario", "created", "target_removed"),
    [(1, 0, 0), (2, 1, 1)],
)
def test_native_replacement_failure_preserves_source(
    native_transactions, tmp_path, scenario, created, target_removed
):
    values = run_native(native_transactions, tmp_path / f"replace-{scenario}", 311, scenario)
    assert values[0] == 3
    assert values[1] == values[2] != 0
    assert values[4:7] == (0, target_removed, created)


@pytest.mark.parametrize(
    ("scenario", "mask", "mana_writes", "mana"),
    [(0, 3, 1, 350), (4, 1, 0, 0)],
)
def test_native_fill_vitals_skips_zero_max_mana(
    native_transactions, tmp_path, scenario, mask, mana_writes, mana
):
    values = run_native(native_transactions, tmp_path / f"fill-{scenario}", 306, scenario)
    assert values[:4] == (2, 0, 0, mask)
    assert values[7] == mana_writes
    assert values[9:11] == (725, mana)


def test_native_revive_enumerates_only_dead_heroes_at_one_point(native_transactions, tmp_path):
    values = run_native(native_transactions, tmp_path / "revive", 305, 3)
    assert values[:4] == (2, 0, 0, 1)
    assert values[8] == 1
    assert values[11:13] == (1250, 725)
