"""Behavior tests for protocol-70 FullClone ownership routing."""
import ctypes
import faulthandler
import os
from pathlib import Path
import shutil
import struct
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

import war3_reforged_trainer as module
from test_native_clone_unit_guard import CLONE
from test_native_identity_guard import HARNESS


def result(kind, value=0, error=0):
    return module.NativeHelperOpResult(kind=kind, result=value, last_error=error)


def candidate_and_snapshot(component_mask=0):
    candidate = SimpleNamespace(
        unit_type_id=0x68666F6F,
        unit_address=0x2000,
        handle=0x123400005678,
        owner_address=0x3000,
    )
    snapshot = SimpleNamespace(handle=7, component_mask=component_mask)
    return candidate, snapshot


def test_owner_target_encoding_and_parser_are_exact():
    assert module.PLAYER_TARGET_LOCAL == 0xFFFFFFFC
    assert module.PLAYER_TARGET_SELECTED_OWNER == 0xFFFFFFFD
    assert module.PLAYER_TARGET_NEUTRAL_AGGRESSIVE == 0xFFFFFFFE
    assert module.PLAYER_TARGET_NEUTRAL_PASSIVE == 0xFFFFFFFF
    assert module.parse_player_target("玩家 1") == 0
    assert module.parse_player_target("Player 24") == 23
    assert module.parse_player_target("中立敌对") == 0xFFFFFFFE
    assert module.parse_player_target("Neutral Passive") == 0xFFFFFFFF
    with pytest.raises(ValueError, match="玩家 1 到玩家 24"):
        module.parse_player_target("25")


@pytest.mark.parametrize(
    ("enabled", "mode", "explicit", "expected"),
    [
        (False, "target_player", 23, None),
        (True, "self", 23, 0xFFFFFFFC),
        (True, "selected_owner", 23, 0xFFFFFFFD),
        (True, "target_player", 23, 23),
        (True, "target_player", 0xFFFFFFFE, 0xFFFFFFFE),
        (True, "target_player", 0xFFFFFFFF, 0xFFFFFFFF),
    ],
)
def test_panel_route_distinguishes_author_and_enabled_owner_modes(
    enabled, mode, explicit, expected
):
    assert module.panel_clone_owner_target(enabled, mode, explicit) == expected


def test_validate_and_transfer_use_persistent_operations_without_legacy_helper():
    trainer = object.__new__(module.War3Trainer)
    candidate, _snapshot = candidate_and_snapshot()
    trainer._direct_selected_context = Mock(return_value=(candidate, 7))
    trainer._run_native_helper_ops = Mock(side_effect=[
        [result(trainer.NATIVE_HELPER_OP_EXT_VALIDATE_PLAYER_TARGET, 0x7100)],
        [
            result(trainer.NATIVE_HELPER_OP_VALIDATE_UNIT_IDENTITY),
            result(trainer.NATIVE_HELPER_OP_EXT_SET_UNIT_OWNER_PLAYER, 0x7100),
        ],
    ])

    assert trainer.validate_player_target(23) == 0x7100
    assert trainer.set_selected_unit_owner(23) == 0x7100

    validate_call, transfer_call = trainer._run_native_helper_ops.call_args_list
    assert validate_call.args == (0, ((300, 23, 0, 0, 0),))
    assert transfer_call.args == (
        7,
        (
            (136, 0, 0x2000, 0x123400005678, 0x3000),
            (301, 23, 0, 0, 0),
        ),
    )
    assert not hasattr(trainer, "_native_player_owner_helper_dll_path")


def test_missing_ordinary_player_is_reported_before_creation():
    trainer = object.__new__(module.War3Trainer)
    trainer._run_native_helper_ops = Mock(
        return_value=[result(trainer.NATIVE_HELPER_OP_EXT_VALIDATE_PLAYER_TARGET, 0)]
    )

    with pytest.raises(ValueError, match="地图中没有玩家 24"):
        trainer.validate_player_target(23)


def test_clone_is_one_bound_transaction_and_needs_no_prior_manual_read():
    trainer = object.__new__(module.War3Trainer)
    candidate, snapshot = candidate_and_snapshot(component_mask=3)
    trainer._direct_selected_context = Mock(return_value=(candidate, 7))
    trainer._native_snapshot_for_candidate = Mock(return_value=snapshot)
    trainer.query_mouse_world_position = Mock(return_value=(12.5, -7.25))
    trainer._run_native_helper_ops = Mock(return_value=[
        result(trainer.NATIVE_HELPER_OP_VALIDATE_UNIT_IDENTITY),
        result(trainer.NATIVE_HELPER_OP_EXT_CLONE_SELECTED_WITH_OWNER, 8),
    ])

    assert trainer.clone_selected_unit_with_owner(23) == (0x68666F6F, 8)

    trainer._direct_selected_context.assert_called_once_with()
    trainer.query_mouse_world_position.assert_called_once_with()
    call = trainer._run_native_helper_ops.call_args
    assert call.args[0] == 7
    assert call.args[1][0] == (136, 0, 0x2000, 0x123400005678, 0x3000)
    coordinates = struct.unpack("<Q", struct.pack("<ff", 12.5, -7.25))[0]
    assert call.args[1][1] == (303, 0x68666F6F, 23, coordinates, 3)
    assert call.kwargs["timeout_ms"] == 10000


def test_mass_clone_captures_live_selection_and_position_once():
    trainer = object.__new__(module.War3Trainer)
    candidate, snapshot = candidate_and_snapshot()
    trainer._direct_selected_context = Mock(return_value=(candidate, 7))
    trainer._native_snapshot_for_candidate = Mock(return_value=snapshot)
    trainer.query_mouse_world_position = Mock(return_value=(1.0, 2.0))
    trainer._run_native_helper_ops = Mock(side_effect=[
        [result(136), result(303, handle)] for handle in (8, 9, 10, 11)
    ])

    assert trainer.clone_selected_units_with_owner(4, 0xFFFFFFFD) == (0x68666F6F, 4)

    trainer._direct_selected_context.assert_called_once_with()
    trainer.query_mouse_world_position.assert_called_once_with()
    assert trainer._run_native_helper_ops.call_count == 4
    assert {
        call.args[1][1][2] for call in trainer._run_native_helper_ops.call_args_list
    } == {0xFFFFFFFD}


@pytest.mark.parametrize("preserve_owner", (False, True))
def test_author_mass_clone_forwards_owner_choice_to_each_unit(preserve_owner):
    # The panel's self/original-owner choice must reach every author clone.
    trainer = object.__new__(module.War3Trainer)
    trainer.query_mouse_world_position = Mock(return_value=(1.0, 2.0))
    trainer.create_local_unit = Mock(side_effect=[(0x68666F6F, 8), (0x68666F6F, 9)])

    assert trainer.create_local_units(2, preserve_owner=preserve_owner) == (0x68666F6F, 2)
    assert trainer.create_local_unit.call_args_list == [
        call(None, (1.0, 2.0), use_selected_lookup=True, preserve_owner=preserve_owner),
        call(None, (1.0, 2.0), use_selected_lookup=True, preserve_owner=preserve_owner),
    ]


def test_reinforcements_keep_count_and_selected_owner_consistent():
    trainer = object.__new__(module.War3Trainer)
    candidate, _snapshot = candidate_and_snapshot()
    trainer._direct_selected_context = Mock(return_value=(candidate, 7))
    trainer.query_mouse_world_position = Mock(return_value=(3.0, 4.0))
    trainer._run_native_helper_ops = Mock(side_effect=[
        [result(136), result(302, handle)] for handle in (20, 21, 22)
    ])

    assert trainer.create_units_for_owner_target(
        3, "hcth", 0xFFFFFFFD
    ) == (0x68637468, 3)

    trainer._direct_selected_context.assert_called_once_with()
    trainer.query_mouse_world_position.assert_called_once_with()
    assert trainer._run_native_helper_ops.call_count == 3
    for call in trainer._run_native_helper_ops.call_args_list:
        assert call.args[0] == 7
        assert call.args[1][1][0:3] == (302, 0x68637468, 0xFFFFFFFD)


def test_author_clone_operation_118_remains_separate_from_extension_clone():
    assert module.War3Trainer.NATIVE_HELPER_OP_JASS_CLONE_SELECTED_UNIT == 118
    assert module.War3Trainer.NATIVE_HELPER_OP_EXT_CLONE_SELECTED_WITH_OWNER == 303
    source = (Path(__file__).parent / "tools" / "war3_native_helper.c").read_text(
        encoding="utf-8"
    )
    assert "#define WAR3_NATIVE_OP_JASS_CLONE_SELECTED_UNIT 118u" in source
    assert "#define WAR3_NATIVE_OP_EXT_CLONE_SELECTED_WITH_OWNER 303u" in source


def test_panel_controls_default_off_and_expose_all_owner_choices():
    source = Path(module.__file__).read_text(encoding="utf-8-sig")
    assert 'elephant_panel_clone_owner_enabled = tk.BooleanVar(value=False)' in source
    assert 'text="启用面板复制归属（关闭＝作者逻辑）"' in source
    assert 'value="self"' in source
    assert 'value="selected_owner"' in source
    assert 'value="target_player"' in source
    assert "panel_clone_owner_target(" in source


@pytest.mark.parametrize(
    ("enabled", "requested_mode", "expected"),
    [
        (False, None, False),
        (True, None, True),
        (False, "self", False),
        (True, "self", False),
    ],
)
def test_actual_panel_clone_request_obeys_toggle(enabled, requested_mode, expected):
    assert module.panel_clone_request_uses_extension(enabled, requested_mode) is expected


def test_actual_panel_clone_button_does_not_force_extension_route():
    source = Path(module.__file__).read_text(encoding="utf-8-sig")
    assert (
        'command=lambda: call_async(lambda: elephant_create_unit(True)),'
        in source
    )
    assert 'elephant_create_unit(True, "panel")' not in source


def test_extension_clone_checks_final_owner_after_all_copy_work():
    source = (Path(__file__).parent / "tools" / "war3_native_helper.c").read_text(
        encoding="utf-8"
    )
    clone = source[source.index("case WAR3_NATIVE_OP_EXT_CLONE_SELECTED_WITH_OWNER:"):]
    success = clone.index("op->result = target;")
    copy_finished = clone.rfind("war3_clone_check_saved_items(&clone_guard);", 0, success)
    final_owner = clone.rfind("get_owning_player(target)", 0, success)
    assert copy_finished >= 0
    assert final_owner > copy_finished


OWNER_CLONE = r'''
static unsigned owner_readback_fault, owner_target_reads;
static uint64_t owner_clone_owning(uint64_t unit) {
    clone_step(unit);
    if (unit == 8) {
        ++owner_target_reads;
        if (owner_readback_fault == 1 ||
            (owner_readback_fault == 2 && owner_target_reads > 1)) return 3;
    }
    return 2;
}
static void owner_native(const char *name, uint64_t handler) {
    for (unsigned index = 0; index < sizeof(g_persistent_natives) / sizeof(g_persistent_natives[0]); ++index) {
        g_persistent_natives[index].name = g_persistent_native_names[index];
        if (!strcmp(g_persistent_native_names[index], name))
            g_persistent_natives[index].handler = handler;
    }
}
__declspec(dllexport) DWORD owner_clone_test(
    const wchar_t *directory, unsigned readback_fault, unsigned *out
) {
    NativeCommand cmd = {0}; wchar_t path[MAX_PATH]; DWORD bytes = 0;
    if (wcslen(directory) >= MAX_PATH - 1) return ERROR_INVALID_PARAMETER;
    wcscpy(test_directory, directory);
    ZeroMemory(object, sizeof(object)); ZeroMemory(owner, sizeof(owner));
    ZeroMemory(other, sizeof(other)); ZeroMemory(clone_owner, sizeof(clone_owner));
    ZeroMemory(g_persistent_natives, sizeof(g_persistent_natives));
    *(uint64_t *)(object + 0x18) = full;
    *(uint64_t *)(owner + 0x18) = 0x2b7733752b61676cULL;
    *(uint64_t *)(owner + 0x20) = full;
    *(uint64_t *)(owner + 0x90) = (uint64_t)(uintptr_t)object;
    fault = bad_arguments = clone_calls = clone_created = clone_removed = clone_present = 0;
    clone_at = clone_fault = clone_features = clone_ability_rank = 0;
    clone_level = 1; clone_xp = clone_points = clone_stats[0] = clone_stats[1] = clone_stats[2] = 0;
    clone_hp = 100; clone_mana = 50; clone_life = 100; clone_mp = 50;
    owner_readback_fault = readback_fault; owner_target_reads = 0;
    g_persistent_unit_resolver = (uint64_t)(uintptr_t)clone_resolve;
    g_persistent_agent_resolver = (uint64_t)(uintptr_t)clone_agent;
    owner_native("GetOwningPlayer", (uint64_t)(uintptr_t)owner_clone_owning);
    owner_native("CreateUnit", (uint64_t)(uintptr_t)clone_create);
    owner_native("GetUnitFacing", (uint64_t)(uintptr_t)clone_facing);
    owner_native("GetUnitTypeId", (uint64_t)(uintptr_t)clone_type);
    owner_native("RemoveUnit", (uint64_t)(uintptr_t)clone_remove);
    owner_native("BlzGetUnitMaxHP", (uint64_t)(uintptr_t)clone_max_hp);
    owner_native("BlzSetUnitMaxHP", (uint64_t)(uintptr_t)clone_set_hp);
    owner_native("GetWidgetLife", (uint64_t)(uintptr_t)clone_get_life);
    owner_native("SetWidgetLife", (uint64_t)(uintptr_t)clone_set_life);
    owner_native("BlzGetUnitMaxMana", (uint64_t)(uintptr_t)clone_max_mp);
    owner_native("BlzSetUnitMaxMana", (uint64_t)(uintptr_t)clone_set_mp);
    owner_native("GetUnitState", (uint64_t)(uintptr_t)clone_get_state);
    owner_native("SetUnitState", (uint64_t)(uintptr_t)clone_set_state);
    owner_native("BlzGetUnitAbilityByIndex", (uint64_t)(uintptr_t)clone_ability);
    owner_native("BlzGetAbilityId", (uint64_t)(uintptr_t)clone_ability_id);
    owner_native("GetUnitAbilityLevel", (uint64_t)(uintptr_t)clone_ability_level);
    owner_native("UnitAddAbility", (uint64_t)(uintptr_t)clone_add_ability);
    owner_native("SetUnitAbilityLevel", (uint64_t)(uintptr_t)clone_set_ability);
    cmd.magic = WAR3_NATIVE_MAGIC; cmd.version = WAR3_NATIVE_VERSION;
    cmd.status = WAR3_NATIVE_STATUS_PENDING; cmd.op_count = 2; cmd.unit_handle = 7;
    cmd.ops[0].kind = WAR3_NATIVE_OP_VALIDATE_UNIT_IDENTITY;
    cmd.ops[0].handler = (uint64_t)(uintptr_t)object;
    cmd.ops[0].arg0 = full; cmd.ops[0].arg1 = (uint64_t)(uintptr_t)owner;
    cmd.ops[1].kind = WAR3_NATIVE_OP_EXT_CLONE_SELECTED_WITH_OWNER;
    cmd.ops[1].rawcode = 0x68666f6f; cmd.ops[1].handler = WAR3_PLAYER_TARGET_SELECTED_OWNER;
    cmd.ops[1].arg0 = 0xc080000041400000ULL; cmd.ops[1].arg1 = 0;
    command_path(path, MAX_PATH);
    HANDLE file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0, NULL, CREATE_NEW, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) return GetLastError();
    if (!WriteFile(file, &cmd, sizeof(cmd), &bytes, NULL)) { CloseHandle(file); return ERROR_WRITE_FAULT; }
    CloseHandle(file); run_command();
    file = CreateFileW(path, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) return GetLastError();
    if (!ReadFile(file, &cmd, sizeof(cmd), &bytes, NULL)) { CloseHandle(file); return ERROR_READ_FAULT; }
    CloseHandle(file); DeleteFileW(path);
    out[0] = cmd.status; out[1] = cmd.last_error; out[2] = cmd.ops[1].last_error;
    out[3] = (unsigned)cmd.ops[1].result; out[4] = clone_created;
    out[5] = clone_removed; out[6] = clone_present; out[7] = bad_arguments;
    return ERROR_SUCCESS;
}
'''


@pytest.fixture(scope="module")
def owner_clone_native(tmp_path_factory):
    compiler = shutil.which("clang")
    if not compiler:
        pytest.skip("Microsoft-SEH-capable clang is required for the native owner-clone harness")
    root = tmp_path_factory.mktemp("fullclone-owner")
    source = root / "owner.c"
    library = root / "owner.dll"
    helper = Path(__file__).parent / "tools" / "war3_native_helper.c"
    source.write_text(
        HARNESS.replace("HELPER_SOURCE", helper.as_posix()) + CLONE + OWNER_CLONE,
        encoding="utf-8",
    )
    build = subprocess.run(
        [compiler, "-shared", "-O2", "-Wno-microsoft-goto", str(source), "-o", str(library),
         "-luser32", "-lkernel32"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert build.returncode == 0, build.stderr
    native = ctypes.CDLL(str(library))
    native.owner_clone_test.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_uint),
    ]
    native.owner_clone_test.restype = ctypes.c_uint
    yield native
    import _ctypes
    _ctypes.FreeLibrary(native._handle)


def run_owner_clone(native, directory, failure):
    directory.mkdir(exist_ok=True)
    out = (ctypes.c_uint * 8)()
    enabled = faulthandler.is_enabled()
    try:
        faulthandler.disable()
        assert native.owner_clone_test(str(directory) + "\\", failure, out) == 0
    finally:
        if enabled:
            faulthandler.enable()
    return tuple(out)


def test_native_owner_clone_succeeds_as_one_transaction(owner_clone_native, tmp_path):
    assert run_owner_clone(owner_clone_native, tmp_path / "ok", 0) == (2, 0, 0, 8, 1, 0, 1, 0)


def test_native_owner_readback_failure_removes_new_clone(owner_clone_native, tmp_path):
    status, last_error, operation_error, _phase, created, removed, present, bad = (
        run_owner_clone(owner_clone_native, tmp_path / "rollback", 1)
    )
    assert status == 3
    assert last_error == operation_error != 0
    assert (created, removed, present, bad) == (1, 1, 0, 0)


def test_native_owner_change_during_copy_removes_new_clone(owner_clone_native, tmp_path):
    status, last_error, operation_error, _phase, created, removed, present, bad = (
        run_owner_clone(owner_clone_native, tmp_path / "changed-mid-copy", 2)
    )
    assert status == 3
    assert last_error == operation_error != 0
    assert (created, removed, present, bad) == (1, 1, 0, 0)
