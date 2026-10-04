"""AEsb cleanup: retire owned work without overwriting newer map/user work."""
import ctypes
import faulthandler
from pathlib import Path
import shutil
import subprocess

import pytest
from test_native_ability_actions import ACTIONS
from test_native_direct_transaction import DIRECT
from test_native_effect_lifecycle import LIFECYCLE, TIMER_API
from test_native_identity_guard import HARNESS


RETRY = r'''
__declspec(dllexport) DWORD starfall_test(const wchar_t *directory,unsigned initial,unsigned failure,uint64_t *out) {
    DWORD error=lifecycle_test(directory,initial,2,3,1,failure,out);if(error) return error;
    out[26]=0;
    for(unsigned n=0;n<16;++n) if(g_ability_effects[n].token) ++out[26];
    if(out[0]!=WAR3_NATIVE_STATUS_OK || out[7]!=WAR3_NATIVE_STATUS_OK) return 0;
    NativeCommand cmd={0};
    cmd.magic=WAR3_NATIVE_MAGIC;cmd.version=WAR3_NATIVE_VERSION;cmd.status=WAR3_NATIVE_STATUS_PENDING;cmd.op_count=3;cmd.unit_handle=7;
    cmd.ops[0].kind=WAR3_NATIVE_OP_VALIDATE_UNIT_IDENTITY;cmd.ops[0].handler=(uint64_t)(uintptr_t)object;
    cmd.ops[0].arg0=full;cmd.ops[0].arg1=(uint64_t)(uintptr_t)owner;
    cmd.ops[1].kind=WAR3_NATIVE_OP_START_ABILITY_EFFECT;cmd.ops[1].rawcode=action_ids[0];cmd.ops[1].handler=2;cmd.ops[1].arg0=1;
    cmd.ops[2].kind=WAR3_NATIVE_OP_ABILITY_EFFECT_OPTIONS;cmd.ops[2].rawcode=3;
    cmd.ops[2].arg0=0x47c35000u;cmd.ops[2].arg1=12000;
    life_fault=0;
    error=life_submit(&cmd);if(error) return error;
    out[27]=cmd.status;out[28]=cmd.last_error;
    uint64_t token=cmd.ops[1].result;
    if(cmd.status==WAR3_NATIVE_STATUS_OK) {
        cmd.status=WAR3_NATIVE_STATUS_PENDING;cmd.op_count=2;cmd.ops[1]=(NativeOp){0};
        cmd.ops[1].kind=WAR3_NATIVE_OP_FINISH_ABILITY_EFFECT;cmd.ops[1].handler=token;
        error=life_submit(&cmd);if(error) return error;
        out[29]=cmd.status;out[30]=cmd.last_error;
    }
    return 0;
}
'''


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    compiler = shutil.which('clang')
    if not compiler:
        pytest.skip('clang required')
    root = tmp_path_factory.mktemp('starfall_cleanup')
    source, dll = root / 'test.c', root / 'test.dll'
    harness = HARNESS.replace('#include "HELPER_SOURCE"', TIMER_API + '\n#include "HELPER_SOURCE"')
    actions = ACTIONS.replace('0x41303031u', '0x41457362u')
    lifecycle = LIFECYCLE.replace('|| failure==41 || failure==42)', '|| failure==41 || failure==42 || failure==43 || failure==44)')
    lifecycle = lifecycle.replace('if(failure==41) action_present[0]=0;',
        'if(failure==43) ++life_order;\nif(failure==44) life_area=0x44000000u;\nif(failure==41) action_present[0]=0;')
    source.write_text(harness.replace('HELPER_SOURCE', (Path(__file__).parent / 'tools/war3_native_helper.c').as_posix())
                      + actions + DIRECT + lifecycle + RETRY, encoding='utf8')
    build = subprocess.run([compiler, '-shared', '-O2', '-Wno-microsoft-goto', str(source), '-o', str(dll),
                            '-luser32', '-lkernel32'], capture_output=True, text=True, timeout=60)
    assert build.returncode == 0, build.stderr
    lib = ctypes.CDLL(str(dll))
    lib.starfall_test.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint64)]
    lib.starfall_test.restype = ctypes.c_uint
    yield lib
    import _ctypes
    _ctypes.FreeLibrary(lib._handle)


def run(native, tmp_path, initial=0, fault=0):
    out = (ctypes.c_uint64 * 31)()
    enabled = faulthandler.is_enabled()
    if enabled:
        faulthandler.disable()
    try:
        assert native.starfall_test(str(tmp_path) + '\\', initial, fault, out) == 0
    finally:
        if enabled:
            faulthandler.enable()
    assert out[14] == 0, 'stale identity or wrong native arguments'
    return list(out)


@pytest.mark.parametrize('initial', [0, 1])
@pytest.mark.parametrize('fault', [0, 15, 16, 35, 43, 44])
def test_starfall_cleanup_retires_token_and_allows_another_cast(native, tmp_path, initial, fault):
    out = run(native, tmp_path, initial, fault)
    assert out[0] == out[7] == 2 and out[1] == out[8] == 0
    assert out[26] == 0, 'finished starfall must not leave the unit permanently busy'
    assert out[27:31] == [2, 0, 2, 0]
    assert out[16] == initial and out[10] == 1 - initial
    assert out[12] == (0 if fault in (15, 35, 43) else 1)
    if initial:
        assert out[17] == (0x44000000 if fault in (16, 44) else 0x43800000)
    else:
        assert out[11] == 1, 'do not restore fields on a temporary ability about to be deleted'
    if fault in (43, 44):
        assert out[19:22] == [0 if fault == 43 else 1, 1 - initial, 1]


@pytest.mark.parametrize('fault', [6, 7, 13, 14, 25, 37, 39])
def test_starfall_real_stop_failures_or_recycled_objects_remain_errors(native, tmp_path, fault):
    out = run(native, tmp_path, fault=fault)
    assert out[0] == 2 and out[7] == 3 and out[8] != 0
    assert out[10] == 0 and out[26] == 1
    if fault in (13, 14, 25, 37):
        assert out[12] == 0


def test_existing_starfall_restore_failure_is_reported_then_retry_succeeds(native, tmp_path):
    out = run(native, tmp_path, initial=1, fault=34)
    assert out[24] == 3 and out[25] != 0
    assert out[7] == 2 and out[26] == 0
    assert out[17] == 0x43800000 and out[10] == 0


def test_temporary_starfall_removal_throw_can_be_retried_without_double_remove(native, tmp_path):
    out = run(native, tmp_path, fault=33)
    assert out[24] == 3 and out[25] != 0
    assert out[7] == 2 and out[26] == 0
    assert out[10] == 1 and out[16] == 0
