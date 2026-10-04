"""R18 regressions: real helper dispatch, no Warcraft process required."""
import ast
import ctypes
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import war3_reforged_trainer as module
from test_native_ability_actions import ACTIONS
from test_native_identity_guard import HARNESS
from test_native_snapshot_binding import make_candidate, make_snapshot


PRESETS = r'''
static int32_t preset_limit,preset_capacity;
static unsigned preset_fault,preset_enforce,preset_gets;
static int32_t preset_inventory(uint64_t unit) {
    action_check(unit);
    if(preset_fault==42) ++*(uint64_t *)(object+0x18);
    return action_present[0]?preset_capacity:0;
}
static uint64_t preset_levels(uint64_t ability,uint32_t field) {
    if(ability!=100 || field!=0x616c6576u) ++bad_arguments;
    ++preset_gets;
    if(preset_fault==43) ++*(uint64_t *)(object+0x18);
    if(preset_fault==44) {
        ++*(uint64_t *)(action_data[0]+0x18);++*(uint64_t *)(action_wrappers[0]+0x20);
    }
    return (uint32_t)preset_limit;
}
'''

EXPORT = r'''
__declspec(dllexport) DWORD preset_test(const wchar_t *directory,unsigned action,unsigned initial,
    unsigned target,int32_t limit,unsigned failure,int32_t capacity,unsigned *out) {
    preset_limit=limit;preset_fault=failure;preset_capacity=capacity;
    preset_enforce=action==5;preset_gets=0;
    DWORD error=action_test(directory,action,failure,initial,target,0,out);
    out[7]=preset_gets;return error;
}
'''


@pytest.fixture(scope='module')
def native(request, tmp_path_factory):
    compiler = shutil.which('clang')
    if not compiler:
        pytest.skip('clang required')
    rawcode = {'AInv': '0x41496e76u', 'AHab': '0x41486162u'}[request.param]
    actions = ACTIONS.replace('0x41303031u', rawcode)
    actions = actions.replace('static uint32_t action_set', PRESETS + '\nstatic uint32_t action_set')
    actions = actions.replace('action_check(unit);unsigned n=action_index(id);++action_sets;',
        'action_check(unit);unsigned n=action_index(id);++action_sets;\n'
        '    if(preset_enforce && (level<1 || level>preset_limit)) RaiseException(0xc0000094,0,0,NULL);')
    actions = actions.replace('if(failure==1) ++*(uint64_t *)(object+0x18);',
        'for(unsigned n=0;n<sizeof(g_persistent_natives)/sizeof(g_persistent_natives[0]);++n) {\n'
        '    const char *name=g_persistent_native_names[n];\n'
        '    if(!strcmp(name,"UnitInventorySize")) g_persistent_natives[n].handler=failure==46?0:(uint64_t)(uintptr_t)preset_inventory;\n'
        '    if(!strcmp(name,"BlzGetAbilityIntegerField")) g_persistent_natives[n].handler=failure==45?0:(uint64_t)(uintptr_t)preset_levels;\n'
        '}\nif(failure==1) ++*(uint64_t *)(object+0x18);')
    root = tmp_path_factory.mktemp('preset_' + request.param)
    source, dll = root / 'test.c', root / 'test.dll'
    source.write_text(HARNESS.replace('HELPER_SOURCE', (Path(__file__).parent / 'tools/war3_native_helper.c').as_posix())
                      + actions + EXPORT, encoding='utf8')
    result = subprocess.run([compiler, '-shared', '-O2', '-Wno-microsoft-goto', str(source), '-o', str(dll),
                             '-luser32', '-lkernel32'], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    lib = ctypes.CDLL(str(dll))
    lib.preset_test.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                               ctypes.c_int32, ctypes.c_uint, ctypes.c_int32, ctypes.POINTER(ctypes.c_uint)]
    lib.preset_test.restype = ctypes.c_uint
    yield request.param, lib
    import _ctypes
    _ctypes.FreeLibrary(lib._handle)


def dispatch(native, tmp_path, *, action=1, initial=1, target=0, limit=3, fault=0, capacity=6):
    _id, lib = native
    out = (ctypes.c_uint * 8)()
    assert lib.preset_test(str(tmp_path) + '\\', action, initial, target, limit, fault, capacity, out) == 0
    assert out[6] == 0, 'wrong native arguments or write after identity invalidation'
    payload = (tmp_path / f'war3_reforged_native_{os.getpid()}.bin').read_bytes()
    trainer = module.War3Trainer.__new__(module.War3Trainer)
    return list(out), trainer, payload


@pytest.mark.parametrize('initial', [0, 1])
@pytest.mark.parametrize('native', ['AInv'], indirect=True)
def test_inventory_ensure_does_not_remove_or_set_existing_backpack(native, tmp_path, initial):
    out, trainer, payload = dispatch(native, tmp_path, initial=initial)
    result = trainer._parse_native_helper_results(payload, 2)[1]
    assert result.result == 1 - initial
    assert out[:3] == [1 - initial, 0, 0]
    assert out[3] == 1


@pytest.mark.parametrize('action,target', [(2, 0), (3, 3), (4, 0), (5, 112), (1, 3)])
@pytest.mark.parametrize('native', ['AInv'], indirect=True)
def test_inventory_base_component_other_actions_still_rejected(native, tmp_path, action, target):
    out, trainer, payload = dispatch(native, tmp_path, action=action, target=target)
    with pytest.raises(RuntimeError):
        trainer._parse_native_helper_results(payload, 2)
    assert out[:3] == [0, 0, 0]


@pytest.mark.parametrize('fault,capacity', [(0, -1), (0, 7), (0, 0), (42, 6), (46, 6)])
@pytest.mark.parametrize('native', ['AInv'], indirect=True)
def test_inventory_invalid_size_or_identity_never_mutates(native, tmp_path, fault, capacity):
    out, trainer, payload = dispatch(native, tmp_path, fault=fault, capacity=capacity)
    with pytest.raises(RuntimeError):
        trainer._parse_native_helper_results(payload, 2)
    # A present AInv with zero usable slots must not be re-added.
    assert out[:3] == [0, 0, 0]


@pytest.mark.parametrize('initial', [0, 1])
@pytest.mark.parametrize('limit,want', [(1, 1), (3, 3), (112, 112), (200, 112)])
@pytest.mark.parametrize('native', ['AHab'], indirect=True)
def test_preset_never_sets_level_beyond_map_definition(native, tmp_path, initial, limit, want):
    out, trainer, payload = dispatch(native, tmp_path, action=5, initial=initial, target=112, limit=limit)
    result = trainer._parse_native_helper_results(payload, 2)[1]
    assert result.result == 1 - initial and result.arg1 == want
    assert out[:3] == [1 - initial, 0, 1]
    assert out[4] == want and out[7] == 1


@pytest.mark.parametrize('limit,fault', [(0, 0), (-1, 0), (100001, 0), (3, 43), (3, 44), (3, 45)])
@pytest.mark.parametrize('native', ['AHab'], indirect=True)
def test_preset_invalid_limit_or_recycled_identity_stops_before_set(native, tmp_path, limit, fault):
    out, trainer, payload = dispatch(native, tmp_path, action=5, target=112, limit=limit, fault=fault)
    with pytest.raises(RuntimeError):
        trainer._parse_native_helper_results(payload, 2)
    assert out[:3] == [0, 0, 0]


@pytest.mark.parametrize('native', ['AHab'], indirect=True)
def test_manual_level_setting_keeps_original_strict_request(native, tmp_path):
    out, trainer, payload = dispatch(native, tmp_path, action=3, target=7, limit=3)
    result = trainer._parse_native_helper_results(payload, 2)[1]
    assert result.result == 7 and out[4] == 7 and out[7] == 0


@pytest.mark.parametrize('name,expected_ids', [
    ('elephant_add_standard_auras', ['AHab','AHad','AOr2','AUau','AUav','AEar','AEah','Aabr','ACac']),
    ('elephant_add_standard_passives', ['AInv','AHbh','AOcr','Acdb','ACce','ACes','ACrn','ACpv']),
])
def test_gui_presets_use_bounded_native_actions(name, expected_ids):
    # Execute the actual nested GUI function and actual bundle serializer;
    # replace only the external game transport with deterministic replies.
    tree = ast.parse(Path(module.__file__).read_text(encoding='utf8'))
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)
    trainer = module.War3Trainer.__new__(module.War3Trainer)
    candidate = make_candidate(make_snapshot())
    trainer._direct_selected_context = lambda: (candidate, candidate.native_snapshot.handle)
    commands = []
    def transport(handle, ops):
        commands.extend(ops[1:])
        return [module.NativeHelperOpResult(136,1)] + [module.NativeHelperOpResult(156,1,arg1=3) for _ in ops[1:]]
    trainer._run_native_helper_ops = transport
    namespace = {'elephant_trainer': lambda: trainer, 'elephant_batch': lambda run, label: [run()],
                 'elephant_batch_suffix': lambda: ''}
    exec(compile(ast.Module(body=[function],type_ignores=[]), module.__file__, 'exec'), namespace)
    assert '1 个单位' in namespace[name]()
    assert [op[1] for op in commands] == [int.from_bytes(value.encode('ascii'),'big') for value in expected_ids]
    assert [op[2] for op in commands] == ([5]*7+[1]*2 if name.endswith('auras') else [1]+[5]*3+[1]*4)
