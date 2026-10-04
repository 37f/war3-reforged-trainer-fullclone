"""Protocol isolation for FullClone operations on the persistent helper."""
import ctypes
import faulthandler
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
from unittest.mock import Mock

import pytest

import war3_reforged_trainer as module


EXTENSION_OPERATIONS = {
    "EXT_VALIDATE_PLAYER_TARGET": 300,
    "EXT_SET_UNIT_OWNER_PLAYER": 301,
    "EXT_CREATE_UNIT_PLAYER": 302,
    "EXT_CLONE_SELECTED_WITH_OWNER": 303,
    "EXT_SHARE_SELECTED_OWNER_CONTROL": 304,
    "EXT_REVIVE_SELECTED_OWNER_HEROES": 305,
    "EXT_FILL_UNIT_VITALS": 306,
    "EXT_SET_SELECTED_OWNER_TEAM": 307,
    "EXT_RESTORE_SELECTED_OWNER_TEAM": 308,
    "EXT_SET_UNIT_COLOR": 309,
    "EXT_SET_SELECTED_OWNER_COLOR": 310,
    "EXT_REPLACE_UNIT": 311,
    "EXT_CAST_INFERNAL": 312,
    "EXT_ADD_HERO_ATTRIBUTES": 313,
    "EXT_GOLD_MINE": 314,
    "EXT_LOCAL_VICTORY": 315,
    "EXT_QUERY_SELECTED_OWNER_TEAM": 316,
}
AUTHOR_PYTHON_OPERATIONS_SHA256 = (
    "13175af7125e57021cd919fa3d94bbdfe01a1fc3c89278569bfccd81ebaf071c"
)
AUTHOR_C_OPERATIONS_SHA256 = (
    "72ce11990bdf79c311413f634357dd01cdcb63ac6dd0f91e5b93659149b2215e"
)


def make_transport_trainer(tmp_path):
    trainer = object.__new__(module.War3Trainer)
    trainer._native_helper_batch_hook = 1
    trainer._native_helper_batch_thread_id = threading.get_ident()
    trainer._native_helper_persistent_hook = None
    trainer._native_helper_persistent_pid = 0
    trainer._native_helper_command_path = Mock(return_value=tmp_path / "command.bin")
    trainer._write_native_helper_command = Mock()
    trainer._wait_native_helper_result = Mock(return_value=[])
    return trainer


def test_protocol_75_is_packed_and_protocol_74_is_rejected():
    trainer = object.__new__(module.War3Trainer)
    operation = (module.War3Trainer.NATIVE_HELPER_OP_EXT_LOCAL_VICTORY, 0, 0, 0, 0)

    payload = trainer._pack_native_helper_command(0, (operation,))

    header = trainer.NATIVE_HELPER_HEADER_STRUCT.unpack_from(payload)
    assert trainer.NATIVE_HELPER_VERSION == 75
    assert header[1] == 75
    protocol_69 = bytearray(payload)
    protocol_69[4:8] = (74).to_bytes(4, "little")
    with pytest.raises(RuntimeError, match="协议不匹配"):
        trainer._parse_native_helper_results(bytes(protocol_69), 1)


def test_extension_operations_reach_the_real_python_transport(tmp_path):
    trainer = make_transport_trainer(tmp_path)

    for name, expected in EXTENSION_OPERATIONS.items():
        kind = getattr(trainer, f"NATIVE_HELPER_OP_{name}")
        assert kind == expected
        unit_address = 1 if kind in (305, 306, 311, 313, 314, 316) else 0
        trainer._run_native_helper_ops_locked(
            unit_address,
            ((kind, 0, 0, 0, 0),),
        )

    assert trainer._write_native_helper_command.call_count == len(EXTENSION_OPERATIONS)
    assert trainer._wait_native_helper_result.call_count == len(EXTENSION_OPERATIONS)


@pytest.mark.parametrize("kind", range(317, 321))
def test_reserved_extension_operations_are_rejected_before_transport(tmp_path, kind):
    trainer = make_transport_trainer(tmp_path)

    with pytest.raises(RuntimeError, match="白名单操作"):
        trainer._run_native_helper_ops_locked(0, ((kind, 0, 0, 0, 0),))

    trainer._write_native_helper_command.assert_not_called()


def test_author_operation_numbers_are_unchanged():
    python_operations = tuple(sorted(
        (name, value)
        for name, value in vars(module.War3Trainer).items()
        if name.startswith("NATIVE_HELPER_OP_") and "_EXT_" not in name
        and isinstance(value, int)
    ))
    assert hashlib.sha256(repr(python_operations).encode()).hexdigest() == (
        AUTHOR_PYTHON_OPERATIONS_SHA256
    )

    helper_source = (Path(__file__).parent / "tools" / "war3_native_helper.c").read_text(
        encoding="utf-8"
    )
    c_operations = tuple(sorted(
        (name, int(value))
        for name, value in re.findall(
            r"^#define (WAR3_NATIVE_OP_[A-Z0-9_]+) (\d+)u$", helper_source, re.MULTILINE
        )
        if "_EXT_" not in name
    ))
    assert hashlib.sha256(repr(c_operations).encode()).hexdigest() == AUTHOR_C_OPERATIONS_SHA256


def test_c_protocol_and_extension_declarations_match_python():
    helper_source = (Path(__file__).parent / "tools" / "war3_native_helper.c").read_text(
        encoding="utf-8"
    )
    version = re.search(r"^#define WAR3_NATIVE_VERSION (\d+)u$", helper_source, re.MULTILINE)
    declarations = dict(
        re.findall(r"^#define WAR3_NATIVE_OP_(EXT_[A-Z0-9_]+) (\d+)u$", helper_source, re.MULTILINE)
    )

    assert version and int(version.group(1)) == module.War3Trainer.NATIVE_HELPER_VERSION == 75
    assert {name: int(value) for name, value in declarations.items()} == EXTENSION_OPERATIONS


C_HARNESS = r'''
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
static uint8_t protocol_object[0x20], protocol_other[0x20];
static uint8_t protocol_owner[0xc0], protocol_clone_owner[0xc0];
static const uint64_t protocol_full = 0x123400005678ULL;
static const uint64_t protocol_clone_full = 0x876500004321ULL;
static uint64_t protocol_unit(uint64_t handle) {
    if (handle == 7) return (uint64_t)(uintptr_t)protocol_object;
    if (handle == 8) return (uint64_t)(uintptr_t)protocol_other;
    return 0;
}
static uint64_t protocol_agent(uint32_t slot, uint32_t serial) {
    if (slot == (uint32_t)protocol_full && serial == (uint32_t)(protocol_full >> 32))
        return (uint64_t)(uintptr_t)protocol_owner;
    if (slot == (uint32_t)protocol_clone_full && serial == (uint32_t)(protocol_clone_full >> 32))
        return (uint64_t)(uintptr_t)protocol_clone_owner;
    return 0;
}
static uint64_t protocol_local(void) { return 2; }
static uint64_t protocol_owning(uint64_t unit) { return unit == 7 || unit == 8 ? 2 : 0; }
static void protocol_set_owner(uint64_t unit, uint64_t player, uint32_t color) {
    (void)unit; (void)player; (void)color;
}
static uint64_t protocol_create(uint64_t player, uint32_t id, float *x, float *y, float *facing) {
    (void)player; (void)id; (void)x; (void)y; (void)facing;
    return 8;
}
static void protocol_remove(uint64_t unit) { (void)unit; }
static uint32_t protocol_facing(uint64_t unit) { (void)unit; return 0; }
static uint32_t protocol_type(uint64_t unit) { (void)unit; return 0x68666f6fu; }
static int32_t protocol_max_hp(uint64_t unit) { (void)unit; return 100; }
static int32_t protocol_max_mp(uint64_t unit) { (void)unit; return 50; }
static void protocol_set_int(uint64_t unit, int32_t value) { (void)unit; (void)value; }
static uint32_t protocol_real(uint64_t unit) {
    float value = unit == 7 ? 100.0f : 100.0f; uint32_t bits;
    memcpy(&bits, &value, sizeof(bits)); return bits;
}
static uint32_t protocol_state(uint64_t unit, int32_t state) {
    float value = state == 2 ? 50.0f : 100.0f; uint32_t bits;
    (void)unit; memcpy(&bits, &value, sizeof(bits)); return bits;
}
static void protocol_set_real(uint64_t unit, float *value) { (void)unit; (void)value; }
static void protocol_set_state(uint64_t unit, int32_t state, float *value) {
    (void)unit; (void)state; (void)value;
}
static uint64_t protocol_ability(uint64_t unit, int32_t index) {
    (void)unit; (void)index; return 0;
}
static uint32_t protocol_ability_id(uint64_t ability) { (void)ability; return 0; }
static int32_t protocol_ability_level(uint64_t unit, uint32_t id) {
    (void)unit; (void)id; return 0;
}
static uint32_t protocol_add_ability(uint64_t unit, uint32_t id) {
    (void)unit; (void)id; return 1;
}
static int32_t protocol_set_ability(uint64_t unit, uint32_t id, int32_t level) {
    (void)unit; (void)id; return level;
}
static int32_t protocol_teams[28];
static uint32_t protocol_alliances[28][28][8];
static uint32_t protocol_colors[28];
static uint32_t protocol_unit_color;
static int32_t protocol_player_id(uint64_t player) {
    if (player == 2) return 7;
    return player >= 100 && player < 128 ? (int32_t)player - 100 : -1;
}
static uint64_t protocol_player(int32_t id) { return id >= 0 && id < 28 ? 100u + (uint64_t)id : 0; }
static uint64_t protocol_slot(uint64_t player) { return protocol_player_id(player) >= 0 ? 201 : 0; }
static uint64_t protocol_convert_slot(int32_t state) { return state == 1 ? 201 : 0; }
static int32_t protocol_get_team(uint64_t player) { return protocol_teams[protocol_player_id(player)]; }
static void protocol_set_team(uint64_t player, int32_t team) { protocol_teams[protocol_player_id(player)] = team; }
static uint32_t protocol_get_alliance(uint64_t source, uint64_t other, int32_t kind) {
    int32_t a=protocol_player_id(source), b=protocol_player_id(other);
    return a>=0 && b>=0 && kind>=0 && kind<8 ? protocol_alliances[a][b][kind] : 0;
}
static void protocol_set_alliance(uint64_t source, uint64_t other, int32_t kind, uint32_t value) {
    int32_t a=protocol_player_id(source), b=protocol_player_id(other);
    if(a>=0 && b>=0 && kind>=0 && kind<8) protocol_alliances[a][b][kind]=value&1u;
}
static void protocol_clear_selection(void) {}
static uint32_t protocol_convert_color(int32_t color) { return 500u+(uint32_t)color; }
static void protocol_set_unit_color(uint64_t unit, uint32_t color) { (void)unit; protocol_unit_color=color; }
static void protocol_set_player_color(uint64_t player, uint32_t color) {
    protocol_colors[protocol_player_id(player)] = color;
}
static uint32_t protocol_get_player_color(uint64_t player) { return protocol_colors[protocol_player_id(player)]; }
static void protocol_native(const char *name, uint64_t handler) {
    for (unsigned index = 0;
         index < sizeof(g_persistent_natives) / sizeof(g_persistent_natives[0]);
         ++index) {
        g_persistent_natives[index].name = g_persistent_native_names[index];
        if (!strcmp(g_persistent_native_names[index], name))
            g_persistent_natives[index].handler = handler;
    }
}
static void protocol_setup_natives(void) {
    ZeroMemory(g_persistent_natives, sizeof(g_persistent_natives));
    protocol_native("GetLocalPlayer", (uint64_t)(uintptr_t)protocol_local);
    protocol_native("GetOwningPlayer", (uint64_t)(uintptr_t)protocol_owning);
    protocol_native("SetUnitOwner", (uint64_t)(uintptr_t)protocol_set_owner);
    protocol_native("CreateUnit", (uint64_t)(uintptr_t)protocol_create);
    protocol_native("RemoveUnit", (uint64_t)(uintptr_t)protocol_remove);
    protocol_native("GetUnitFacing", (uint64_t)(uintptr_t)protocol_facing);
    protocol_native("GetUnitTypeId", (uint64_t)(uintptr_t)protocol_type);
    protocol_native("BlzGetUnitMaxHP", (uint64_t)(uintptr_t)protocol_max_hp);
    protocol_native("BlzSetUnitMaxHP", (uint64_t)(uintptr_t)protocol_set_int);
    protocol_native("GetWidgetLife", (uint64_t)(uintptr_t)protocol_real);
    protocol_native("SetWidgetLife", (uint64_t)(uintptr_t)protocol_set_real);
    protocol_native("BlzGetUnitMaxMana", (uint64_t)(uintptr_t)protocol_max_mp);
    protocol_native("BlzSetUnitMaxMana", (uint64_t)(uintptr_t)protocol_set_int);
    protocol_native("GetUnitState", (uint64_t)(uintptr_t)protocol_state);
    protocol_native("SetUnitState", (uint64_t)(uintptr_t)protocol_set_state);
    protocol_native("BlzGetUnitAbilityByIndex", (uint64_t)(uintptr_t)protocol_ability);
    protocol_native("BlzGetAbilityId", (uint64_t)(uintptr_t)protocol_ability_id);
    protocol_native("GetUnitAbilityLevel", (uint64_t)(uintptr_t)protocol_ability_level);
    protocol_native("UnitAddAbility", (uint64_t)(uintptr_t)protocol_add_ability);
    protocol_native("SetUnitAbilityLevel", (uint64_t)(uintptr_t)protocol_set_ability);
    protocol_native("GetPlayerId", (uint64_t)(uintptr_t)protocol_player_id);
    protocol_native("Player", (uint64_t)(uintptr_t)protocol_player);
    protocol_native("GetPlayerSlotState", (uint64_t)(uintptr_t)protocol_slot);
    protocol_native("ConvertPlayerSlotState", (uint64_t)(uintptr_t)protocol_convert_slot);
    protocol_native("GetPlayerTeam", (uint64_t)(uintptr_t)protocol_get_team);
    protocol_native("SetPlayerTeam", (uint64_t)(uintptr_t)protocol_set_team);
    protocol_native("GetPlayerAlliance", (uint64_t)(uintptr_t)protocol_get_alliance);
    protocol_native("SetPlayerAlliance", (uint64_t)(uintptr_t)protocol_set_alliance);
    protocol_native("ClearSelection", (uint64_t)(uintptr_t)protocol_clear_selection);
    protocol_native("ConvertPlayerColor", (uint64_t)(uintptr_t)protocol_convert_color);
    protocol_native("SetUnitColor", (uint64_t)(uintptr_t)protocol_set_unit_color);
    protocol_native("SetPlayerColor", (uint64_t)(uintptr_t)protocol_set_player_color);
    protocol_native("GetPlayerColor", (uint64_t)(uintptr_t)protocol_get_player_color);
}
__declspec(dllexport) DWORD protocol_dispatch(
    const wchar_t *directory, uint32_t version, uint32_t kind, uint32_t valid, uint32_t *out
) {
    NativeCommand cmd = {0};
    uint64_t input_extra = 0;
    DWORD bytes = 0;
    wchar_t path[MAX_PATH];
    HANDLE file;
    if (wcslen(directory) >= MAX_PATH - 1) return ERROR_INVALID_PARAMETER;
    wcscpy(test_directory, directory);
    cmd.magic = WAR3_NATIVE_MAGIC;
    cmd.version = version;
    cmd.status = WAR3_NATIVE_STATUS_PENDING;
    cmd.op_count = 1;
    cmd.ops[0].kind = kind;
    if (valid && ((kind >= 300 && kind <= 304) || (kind >= 307 && kind <= 310) || kind == 316)) {
        ZeroMemory(protocol_object, sizeof(protocol_object));
        ZeroMemory(protocol_other, sizeof(protocol_other));
        ZeroMemory(protocol_owner, sizeof(protocol_owner));
        ZeroMemory(protocol_clone_owner, sizeof(protocol_clone_owner));
        *(uint64_t *)(protocol_object + 0x18) = protocol_full;
        *(uint64_t *)(protocol_other + 0x18) = protocol_clone_full;
        *(uint64_t *)(protocol_owner + 0x18) = 0x2b7733752b61676cULL;
        *(uint64_t *)(protocol_owner + 0x20) = protocol_full;
        *(uint64_t *)(protocol_owner + 0x90) = (uint64_t)(uintptr_t)protocol_object;
        *(uint64_t *)(protocol_clone_owner + 0x18) = 0x2b7733752b61676cULL;
        *(uint64_t *)(protocol_clone_owner + 0x20) = protocol_clone_full;
        *(uint64_t *)(protocol_clone_owner + 0x90) = (uint64_t)(uintptr_t)protocol_other;
        g_persistent_unit_resolver = (uint64_t)(uintptr_t)protocol_unit;
        g_persistent_agent_resolver = (uint64_t)(uintptr_t)protocol_agent;
        protocol_setup_natives();
        if (kind == WAR3_NATIVE_OP_EXT_VALIDATE_PLAYER_TARGET) {
            cmd.ops[0].rawcode = WAR3_PLAYER_TARGET_LOCAL;
        } else if (kind == WAR3_NATIVE_OP_EXT_CREATE_UNIT_PLAYER) {
            cmd.ops[0].rawcode = 0x68666f6fu;
            cmd.ops[0].handler = WAR3_PLAYER_TARGET_LOCAL;
        } else {
            cmd.op_count = 2;
            cmd.unit_handle = 7;
            cmd.ops[0].kind = WAR3_NATIVE_OP_VALIDATE_UNIT_IDENTITY;
            cmd.ops[0].handler = (uint64_t)(uintptr_t)protocol_object;
            cmd.ops[0].arg0 = protocol_full;
            cmd.ops[0].arg1 = (uint64_t)(uintptr_t)protocol_owner;
            cmd.ops[1].kind = kind;
            if (kind == WAR3_NATIVE_OP_EXT_SET_UNIT_OWNER_PLAYER) {
                cmd.ops[1].rawcode = WAR3_PLAYER_TARGET_LOCAL;
            } else if (kind == WAR3_NATIVE_OP_EXT_CLONE_SELECTED_WITH_OWNER) {
                cmd.ops[1].rawcode = 0x68666f6fu;
                cmd.ops[1].handler = WAR3_PLAYER_TARGET_LOCAL;
            } else if (kind == WAR3_NATIVE_OP_EXT_SHARE_SELECTED_OWNER_CONTROL) {
                cmd.ops[1].rawcode = 4u;
            } else if (kind == WAR3_NATIVE_OP_EXT_SET_SELECTED_OWNER_TEAM) {
                cmd.ops[1].rawcode = 1u;
            } else if (kind == WAR3_NATIVE_OP_EXT_RESTORE_SELECTED_OWNER_TEAM) {
                protocol_teams[7] = 1;
                cmd.ops[1].rawcode = 3u;
                cmd.ops[1].handler = 1u;
                cmd.ops[1].arg0 = 7u;
                cmd.ops[1].arg1 = 0u;
                cmd.reserved = 1u;
                input_extra = (1ULL << 35u); /* peer 0, all original/assigned masks clear */
            } else if (kind == WAR3_NATIVE_OP_EXT_SET_UNIT_COLOR ||
                       kind == WAR3_NATIVE_OP_EXT_SET_SELECTED_OWNER_COLOR) {
                cmd.ops[1].rawcode = 3u;
            }
        }
    }
    command_path(path, MAX_PATH);
    file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0, NULL, CREATE_NEW,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return GetLastError();
    if (!WriteFile(file, &cmd, sizeof(cmd), &bytes, NULL)) {
        CloseHandle(file); DeleteFileW(path); return ERROR_WRITE_FAULT;
    }
    if (cmd.reserved && !WriteFile(file, &input_extra, sizeof(input_extra), &bytes, NULL)) {
        CloseHandle(file); DeleteFileW(path); return ERROR_WRITE_FAULT;
    }
    CloseHandle(file);
    run_command();
    file = CreateFileW(path, GENERIC_READ, 0, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return GetLastError();
    if (!ReadFile(file, &cmd, sizeof(cmd), &bytes, NULL)) {
        CloseHandle(file); DeleteFileW(path); return ERROR_READ_FAULT;
    }
    CloseHandle(file);
    DeleteFileW(path);
    out[0] = cmd.status;
    out[1] = cmd.last_error;
    out[2] = cmd.ops[0].last_error;
    return ERROR_SUCCESS;
}
'''


@pytest.fixture(scope="module")
def c_dispatcher():
    compiler = shutil.which("clang")
    if not compiler:
        pytest.skip("Microsoft-SEH-capable clang is required for the native C dispatcher harness")
    directory = tempfile.TemporaryDirectory(prefix="war3-fullclone-protocol-")
    root = Path(directory.name)
    source = root / "protocol.c"
    helper = Path(__file__).parent / "tools" / "war3_native_helper.c"
    source.write_text(C_HARNESS.replace("HELPER_SOURCE", helper.as_posix()), encoding="utf-8")
    library = root / "protocol.dll"
    subprocess.run(
        [compiler, "-shared", "-O2", "-Wno-microsoft-goto", str(source), "-o", str(library),
         "-luser32", "-lkernel32"],
        check=True,
        capture_output=True,
        timeout=60,
    )
    native = ctypes.CDLL(str(library))
    native.protocol_dispatch.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_uint),
    ]
    native.protocol_dispatch.restype = ctypes.c_uint
    yield native, directory.name
    import _ctypes
    _ctypes.FreeLibrary(native._handle)
    directory.cleanup()


def dispatch(c_dispatcher, version, kind, valid=False):
    native, directory = c_dispatcher
    out = (ctypes.c_uint * 3)()
    enabled = faulthandler.is_enabled()
    try:
        faulthandler.disable()
        assert native.protocol_dispatch(directory + "\\", version, kind, valid, out) == 0
    finally:
        if enabled:
            faulthandler.enable()
    return tuple(out)


def test_real_c_dispatcher_rejects_protocol_69(c_dispatcher):
    assert dispatch(c_dispatcher, 69, 300) == (1, 0, 0)


def test_special_extension_operations_are_no_longer_placeholder_cases():
    source = (Path(__file__).parent / "tools" / "war3_native_helper.c").read_text(encoding="utf-8")
    switch = source[source.index("case WAR3_NATIVE_OP_EXT_CAST_INFERNAL:"):
                    source.index("case WAR3_NATIVE_OP_MANAGE_BOUND_ABILITY:")]
    assert "ERROR_NOT_SUPPORTED" not in switch
    for handler in (
        "war3_ext_cast_infernal", "war3_ext_add_hero_attributes",
        "war3_ext_gold_mine", "war3_ext_local_victory",
    ):
        assert handler in switch


@pytest.mark.parametrize("kind", range(300, 304))
def test_real_c_dispatcher_accepts_valid_implemented_transactions(c_dispatcher, kind):
    assert dispatch(c_dispatcher, 75, kind, valid=True) == (2, 0, 0)


@pytest.mark.parametrize("kind", (304, 307, 308, 309, 310, 316))
def test_real_c_dispatcher_accepts_valid_relation_and_color_transactions(c_dispatcher, kind):
    assert dispatch(c_dispatcher, 75, kind, valid=True) == (2, 0, 0)


@pytest.mark.parametrize("kind", (301, 302, 303, 304, 307, 308, 309, 310, 316))
def test_real_c_dispatcher_rejects_invalid_implemented_transactions_without_placeholder_error(
    c_dispatcher, kind
):
    status, last_error, operation_error = dispatch(c_dispatcher, 75, kind)
    assert status == 3
    assert last_error == operation_error != 0
    assert operation_error != module.ERROR_NOT_SUPPORTED


def test_real_c_dispatcher_keeps_reserved_extension_range_unsupported(c_dispatcher):
    for kind in range(317, 321):
        status, last_error, operation_error = dispatch(c_dispatcher, 75, kind)
        assert status == 3
        assert last_error == operation_error != 0
