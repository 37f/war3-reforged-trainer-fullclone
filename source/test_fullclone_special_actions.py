"""Behavior tests for the remaining published R12 special actions."""
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
    trainer._direct_selected_context = Mock(return_value=(candidate(), 7))
    trainer._run_native_helper_ops = Mock(side_effect=responses)
    return trainer


def guard_operation():
    return (136, 0, 0x5000, 0x123400005678, 0x7000)


def test_increment_hero_level_reads_live_value_on_every_press():
    trainer = trainer_with_response()
    trainer.get_selected_hero_level = Mock(side_effect=[4, 5])
    trainer.set_selected_hero_level = Mock(side_effect=lambda value: value)

    assert trainer.increment_selected_hero_level() == 5
    assert trainer.increment_selected_hero_level() == 6
    assert trainer.set_selected_hero_level.call_args_list[0].args == (5,)
    assert trainer.set_selected_hero_level.call_args_list[1].args == (6,)


def test_increment_hero_level_silently_skips_nonhero():
    trainer = trainer_with_response()
    trainer.get_selected_hero_level = Mock(return_value=0)
    trainer.set_selected_hero_level = Mock()

    assert trainer.increment_selected_hero_level() is None
    trainer.set_selected_hero_level.assert_not_called()


def test_increment_attributes_is_one_bound_transaction_and_unpacks_values():
    packed = 12 | (13 << 32)
    trainer = trainer_with_response([
        result(136),
        result(313, 1, packed, 14),
    ])

    assert trainer.increment_selected_hero_attributes(2) == (12, 13, 14)
    assert trainer._run_native_helper_ops.call_args.args == (
        7,
        (guard_operation(), (313, 2, 0, 0, 0)),
    )


def test_increment_attributes_silently_skips_nonhero():
    trainer = trainer_with_response([
        result(136),
        result(313, 0xFFFFFFFFFFFFFFFF),
    ])

    assert trainer.increment_selected_hero_attributes() is None


@pytest.mark.parametrize("delta", [0, -1, 1_000_000_001])
def test_attribute_delta_bounds_stop_before_transport(delta):
    trainer = trainer_with_response()

    with pytest.raises(ValueError, match="英雄属性增量"):
        trainer.increment_selected_hero_attributes(delta)

    trainer._direct_selected_context.assert_not_called()


def test_gold_mine_read_and_set_use_bound_persistent_operation():
    read_trainer = trainer_with_response([
        result(136), result(314, 12345),
    ])
    assert read_trainer.selected_gold_mine_amount() == 12345
    assert read_trainer._run_native_helper_ops.call_args.args == (
        7, (guard_operation(), (314, 0, 0, 0, 0)),
    )

    set_trainer = trainer_with_response([
        result(136), result(314, 777),
    ])
    assert set_trainer.set_selected_gold_mine_amount(777) == 777
    assert set_trainer._run_native_helper_ops.call_args.args == (
        7, (guard_operation(), (314, 1, 777, 0, 0)),
    )


def test_gold_mine_silently_skips_nonmine_and_validates_bounds():
    trainer = trainer_with_response([
        result(136), result(314, 0xFFFFFFFFFFFFFFFF),
    ])
    assert trainer.selected_gold_mine_amount() is None

    trainer = trainer_with_response()
    with pytest.raises(ValueError, match="金矿黄金"):
        trainer.set_selected_gold_mine_amount(1_000_000_001)
    trainer._direct_selected_context.assert_not_called()


def test_local_victory_does_not_require_a_selected_unit():
    trainer = trainer_with_response([result(315, 8)])

    assert trainer.win_local_player() is True
    assert trainer._run_native_helper_ops.call_args.args == (
        0, ((315, 0, 0, 0, 0),),
    )
    trainer._direct_selected_context.assert_not_called()


def test_infernal_uses_verified_r12_cast_transaction_at_one_captured_mouse_point():
    trainer = trainer_with_response([result(312, 55)])
    trainer.query_mouse_world_position = Mock(return_value=(12.5, -7.25))

    assert trainer.summon_infernal_at_mouse() == 55

    coordinates = struct.unpack("<Q", struct.pack("<ff", 12.5, -7.25))[0]
    assert trainer._run_native_helper_ops.call_args.args == (
        0, ((312, 0, 0, coordinates, 0),),
    )
    trainer.query_mouse_world_position.assert_called_once_with()


def test_infernal_operation_restores_verified_r12_dummy_cast_path():
    source = (Path(__file__).parent / "tools" / "war3_native_helper.c").read_text(
        encoding="utf-8"
    )
    start = source.index("static DWORD war3_ext_cast_infernal(")
    end = source.index("static DWORD war3_ext_revive_selected_owner_heroes(", start)
    implementation = source[start:end]
    assert "0x68666f6f" in implementation
    assert "UnitApplyTimedLife" in implementation


def test_game_speed_extension_is_removed_from_python_and_native_helper():
    source = (Path(__file__).parent / "tools" / "war3_native_helper.c").read_text(
        encoding="utf-8"
    )
    assert not hasattr(module.War3Trainer, "NATIVE_HELPER_OP_EXT_SET_GAME_SPEED")
    assert not hasattr(module.War3Trainer, "set_game_speed")
    assert "WAR3_NATIVE_OP_EXT_SET_GAME_SPEED" not in source
    assert "war3_ext_set_game_speed" not in source
    for native_name in (
        "ConvertGameSpeed", "SetGameSpeed", "GetGameSpeed",
        "ConvertMapFlag", "IsMapFlagSet",
    ):
        assert f'"{native_name}"' not in source


SPECIAL_HARNESS = r'''
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

static uint8_t object[0x20], owner[0xc0];
static const uint64_t full = 0x123400005678ULL;
static int scenario, stats[3], resource;
static unsigned writes, removed, order_id, event_log;
static uint32_t bits(float value) { uint32_t out; memcpy(&out, &value, 4); return out; }
static uint64_t unit_resolver(uint64_t handle) { return handle == 7 ? (uint64_t)(uintptr_t)object : 0; }
static uint64_t agent_resolver(uint32_t slot, uint32_t serial) {
    return slot == (uint32_t)full && serial == (uint32_t)(full >> 32)
        ? (uint64_t)(uintptr_t)owner : 0;
}
static int32_t hero_level(uint64_t unit) { (void)unit; return scenario == 1 ? 0 : 4; }
static int32_t get_str(uint64_t u, uint32_t b) { (void)u; (void)b; return stats[0]; }
static int32_t get_agi(uint64_t u, uint32_t b) { (void)u; (void)b; return stats[1]; }
static int32_t get_int(uint64_t u, uint32_t b) { (void)u; (void)b; return stats[2]; }
static void set_str(uint64_t u, int32_t v, uint32_t p) { (void)u;(void)p;stats[0]=v;++writes; }
static void set_agi(uint64_t u, int32_t v, uint32_t p) { (void)u;(void)p;stats[1]=v;++writes; }
static void set_int(uint64_t u, int32_t v, uint32_t p) { (void)u;(void)p;stats[2]=v;++writes; }
static uint32_t get_type(uint64_t unit) { (void)unit; return scenario == 1 ? 0x68666f6fu : 0x6e676f6cu; }
static int32_t get_resource(uint64_t unit) { (void)unit; return resource; }
static void set_resource(uint64_t unit, int32_t value) { (void)unit; resource=value; ++writes; }
static uint64_t get_local(void) { event_log=event_log*10+1; return 8; }
static uint64_t convert_result(int32_t value) { (void)value; event_log=event_log*10+2; return 9; }
static void remove_player(uint64_t p, uint64_t r) { (void)p;(void)r;event_log=event_log*10+3; }
static void end_game(uint32_t score) { (void)score;event_log=event_log*10+4; }
static uint64_t create_unit(uint64_t p,uint32_t id,float*x,float*y,float*f) {
    (void)p;(void)x;(void)y;(void)f; return id==0x68666f6fu ? 55 : 0;
}
static uint32_t add_ability(uint64_t u,uint32_t id) { return u==55 && id==0x4155696eu; }
static void set_max_mana(uint64_t u,int32_t v) { (void)u;(void)v; }
static void set_state(uint64_t u,int32_t s,float*v) { (void)u;(void)s;(void)v; }
static uint32_t issue_order(uint64_t u,int32_t id,float*x,float*y) {
    (void)u;(void)x;(void)y; order_id=(uint32_t)id; return scenario != 1;
}
static void timed_life(uint64_t u,uint32_t id,float*v) { (void)u;(void)id;(void)v; ++writes; }
static void remove_unit(uint64_t u) { (void)u; ++removed; }
static void bind_native(const char *name, uint64_t handler) {
    for (unsigned i=0;i<sizeof(g_persistent_natives)/sizeof(g_persistent_natives[0]);++i) {
        g_persistent_natives[i].name=g_persistent_native_names[i];
        if (!strcmp(name,g_persistent_native_names[i])) g_persistent_natives[i].handler=handler;
    }
}
static void setup(void) {
    ZeroMemory(g_persistent_natives,sizeof(g_persistent_natives));
    bind_native("GetHeroLevel",(uint64_t)(uintptr_t)hero_level);
    bind_native("GetHeroStr",(uint64_t)(uintptr_t)get_str); bind_native("GetHeroAgi",(uint64_t)(uintptr_t)get_agi);
    bind_native("GetHeroInt",(uint64_t)(uintptr_t)get_int); bind_native("SetHeroStr",(uint64_t)(uintptr_t)set_str);
    bind_native("SetHeroAgi",(uint64_t)(uintptr_t)set_agi); bind_native("SetHeroInt",(uint64_t)(uintptr_t)set_int);
    bind_native("GetUnitTypeId",(uint64_t)(uintptr_t)get_type); bind_native("GetResourceAmount",(uint64_t)(uintptr_t)get_resource);
    bind_native("SetResourceAmount",(uint64_t)(uintptr_t)set_resource); bind_native("GetLocalPlayer",(uint64_t)(uintptr_t)get_local);
    bind_native("ConvertPlayerGameResult",(uint64_t)(uintptr_t)convert_result); bind_native("RemovePlayer",(uint64_t)(uintptr_t)remove_player);
    bind_native("EndGame",(uint64_t)(uintptr_t)end_game); bind_native("CreateUnit",(uint64_t)(uintptr_t)create_unit);
    bind_native("UnitAddAbility",(uint64_t)(uintptr_t)add_ability); bind_native("BlzSetUnitMaxMana",(uint64_t)(uintptr_t)set_max_mana);
    bind_native("SetUnitState",(uint64_t)(uintptr_t)set_state); bind_native("IssuePointOrderById",(uint64_t)(uintptr_t)issue_order);
    bind_native("UnitApplyTimedLife",(uint64_t)(uintptr_t)timed_life); bind_native("RemoveUnit",(uint64_t)(uintptr_t)remove_unit);
}
__declspec(dllexport) DWORD special_test(const wchar_t *directory,uint32_t kind,uint32_t selected,uint64_t*out) {
    NativeCommand cmd={0}; wchar_t path[MAX_PATH]; DWORD bytes=0; HANDLE file;
    wcscpy(test_directory,directory); scenario=(int)selected; writes=removed=order_id=event_log=0;
    stats[0]=10;stats[1]=20;stats[2]=30;resource=0;
    ZeroMemory(object,sizeof(object));ZeroMemory(owner,sizeof(owner));
    *(uint64_t *)(object+0x18)=full; *(uint64_t *)(owner+0x18)=0x2b7733752b61676cULL;
    *(uint64_t *)(owner+0x20)=full; *(uint64_t *)(owner+0x90)=(uint64_t)(uintptr_t)object;
    g_persistent_unit_resolver=(uint64_t)(uintptr_t)unit_resolver;
    g_persistent_agent_resolver=(uint64_t)(uintptr_t)agent_resolver; setup();
    cmd.magic=WAR3_NATIVE_MAGIC;cmd.version=WAR3_NATIVE_VERSION;cmd.status=WAR3_NATIVE_STATUS_PENDING;
    if (kind==WAR3_NATIVE_OP_EXT_ADD_HERO_ATTRIBUTES || kind==WAR3_NATIVE_OP_EXT_GOLD_MINE) {
        cmd.op_count=2;cmd.unit_handle=7;cmd.ops[0].kind=WAR3_NATIVE_OP_VALIDATE_UNIT_IDENTITY;
        cmd.ops[0].handler=(uint64_t)(uintptr_t)object;cmd.ops[0].arg0=full;cmd.ops[0].arg1=(uint64_t)(uintptr_t)owner;
        cmd.ops[1].kind=kind;if(kind==WAR3_NATIVE_OP_EXT_ADD_HERO_ATTRIBUTES)cmd.ops[1].rawcode=2;
        if(kind==WAR3_NATIVE_OP_EXT_GOLD_MINE && selected==2){cmd.ops[1].rawcode=1;cmd.ops[1].handler=777;}
    } else {
        cmd.op_count=1;cmd.ops[0].kind=kind;
        if(kind==WAR3_NATIVE_OP_EXT_CAST_INFERNAL)cmd.ops[0].arg0=((uint64_t)bits(-7.25f)<<32)|bits(12.5f);
    }
    command_path(path,MAX_PATH);file=CreateFileW(path,GENERIC_READ|GENERIC_WRITE,0,NULL,CREATE_NEW,0,NULL);
    if(file==INVALID_HANDLE_VALUE)return GetLastError();WriteFile(file,&cmd,sizeof(cmd),&bytes,NULL);CloseHandle(file);run_command();
    file=CreateFileW(path,GENERIC_READ,0,NULL,OPEN_EXISTING,0,NULL);ReadFile(file,&cmd,sizeof(cmd),&bytes,NULL);
    CloseHandle(file);DeleteFileW(path);NativeOp *op=&cmd.ops[cmd.op_count-1];
    out[0]=cmd.status;out[1]=cmd.last_error;out[2]=op->last_error;out[3]=op->result;out[4]=op->arg0;out[5]=op->arg1;
    out[6]=writes;out[7]=removed;out[8]=order_id;out[9]=event_log;return 0;
}
'''


@pytest.fixture(scope="module")
def native_special_actions(tmp_path_factory):
    compiler = shutil.which("clang")
    if not compiler:
        pytest.skip("Microsoft-SEH-capable clang is required")
    root = tmp_path_factory.mktemp("fullclone-special-actions")
    helper = Path(__file__).parent / "tools" / "war3_native_helper.c"
    source = root / "special.c"
    source.write_text(SPECIAL_HARNESS.replace("HELPER_SOURCE", helper.as_posix()), encoding="utf-8")
    library = root / "special.dll"
    build = subprocess.run([compiler, "-shared", "-O2", "-Wno-microsoft-goto", str(source),
                            "-o", str(library), "-luser32", "-lkernel32"],
                           capture_output=True, text=True, timeout=60)
    assert build.returncode == 0, build.stderr
    native = ctypes.CDLL(str(library))
    native.special_test.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint,
                                    ctypes.POINTER(ctypes.c_uint64)]
    native.special_test.restype = ctypes.c_uint
    yield native
    import _ctypes
    _ctypes.FreeLibrary(native._handle)


def run_native(native, directory, kind, scenario=0):
    directory.mkdir(exist_ok=True)
    out = (ctypes.c_uint64 * 10)()
    enabled = faulthandler.is_enabled()
    try:
        faulthandler.disable()
        assert native.special_test(str(directory) + "\\", kind, scenario, out) == 0
    finally:
        if enabled:
            faulthandler.enable()
    return tuple(out)


def test_native_attribute_increment_and_nonhero_silence(native_special_actions, tmp_path):
    values = run_native(native_special_actions, tmp_path / "attr", 313)
    assert values[:4] == (2, 0, 0, 1)
    assert values[4] == 12 | (22 << 32) and values[5:7] == (32, 3)
    skipped = run_native(native_special_actions, tmp_path / "nonhero", 313, 1)
    assert skipped[:3] == (2, 0, 0) and skipped[3] == 0xFFFFFFFFFFFFFFFF and skipped[6] == 0


def test_native_gold_mine_zero_nonmine_and_set_readback(native_special_actions, tmp_path):
    mine = run_native(native_special_actions, tmp_path / "mine", 314)
    assert mine[:4] == (2, 0, 0, 0)
    other = run_native(native_special_actions, tmp_path / "other", 314, 1)
    assert other[3] == 0xFFFFFFFFFFFFFFFF and other[6] == 0
    changed = run_native(native_special_actions, tmp_path / "set", 314, 2)
    assert changed[:4] == (2, 0, 0, 777) and changed[6] == 1


def test_native_victory_call_order(native_special_actions, tmp_path):
    values = run_native(native_special_actions, tmp_path / "victory", 315)
    assert values[:4] == (2, 0, 0, 8) and values[9] == 1234


def test_native_infernal_cast_and_failed_order_cleanup(native_special_actions, tmp_path):
    values = run_native(native_special_actions, tmp_path / "infernal", 312)
    assert values[:4] == (2, 0, 0, 55) and values[6:9] == (1, 0, 852224)
    failed = run_native(native_special_actions, tmp_path / "infernal-fail", 312, 1)
    assert failed[0] == 3 and failed[1] == failed[2] != 0 and failed[7] == 1
