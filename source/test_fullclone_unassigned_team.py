"""Real C and Python regressions for reversible -1 diplomacy, never a live game."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import war3_reforged_trainer as module
from test_fullclone_protocol import C_HARNESS
from test_fullclone_player_relations import candidate, relationship, result, trainer_with_responses


CODEC_HARNESS = r'''
__declspec(dllexport) DWORD ua_codec(int32_t team, uint64_t *out) {
#ifdef WAR3_UNASSIGNED_TEAM_TAG
    War3TeamPeerSnapshot source={0}, decoded={0};
    source.team=team; source.player_index=3;
    source.owner_to_peer_mask=5; source.peer_to_owner_mask=7;
    source.assigned_owner_to_peer_mask=8; source.assigned_peer_to_owner_mask=9;
    out[0]=war3_team_pack_unassigned_peer(&source);
    if(!war3_team_unpack_unassigned_peer(out[0], &decoded))return ERROR_INVALID_DATA;
    out[1]=(uint32_t)decoded.team; out[2]=decoded.player_index;
    out[3]=decoded.owner_to_peer_mask; out[4]=decoded.peer_to_owner_mask;
    return 0;
#else
    (void)team; (void)out; return ERROR_NOT_SUPPORTED;
#endif
}
__declspec(dllexport) DWORD ua_unpack(uint64_t packed) {
#ifdef WAR3_UNASSIGNED_TEAM_TAG
    War3TeamPeerSnapshot decoded;
    return war3_team_unpack_unassigned_peer(packed,&decoded)?0:ERROR_INVALID_DATA;
#else
    (void)packed; return ERROR_NOT_SUPPORTED;
#endif
}
'''

TRANSACTION_HARNESS = r'''
static uint32_t ua_team_calls, ua_calls, ua_at, ua_fault, ua_original[28][28][8];
static uint64_t ua_owner_value;
static uint64_t ua_owner(uint64_t unit) { return unit==7?ua_owner_value:0; }
static void ua_set_team(uint64_t player,int32_t team) {
    ++ua_team_calls; protocol_set_team(player,team);
}
static void ua_set_alliance(uint64_t a,uint64_t b,int32_t kind,uint32_t value) {
    ++ua_calls;
    if(ua_at && (ua_calls==ua_at || (ua_fault==4 && ua_calls>=ua_at))) {
        if(ua_fault==3)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,NULL);
        if(ua_calls==ua_at)protocol_set_alliance(a,b,kind,value^1u);
        return;
    }
    protocol_set_alliance(a,b,kind,value);
}
static void ua_setup(void) {
    protocol_setup_natives(); ua_owner_value=107; ua_team_calls=ua_calls=ua_at=ua_fault=0;
    ua_fail_alloc=0;
    for(int a=0;a<28;++a) {
        protocol_teams[a]=a%12;
        for(int b=0;b<28;++b) for(int k=0;k<8;++k)
            protocol_alliances[a][b][k]=(a+2*b+k)%2;
    }
    protocol_teams[7]=protocol_teams[8]=-1;
    memcpy(ua_original,protocol_alliances,sizeof(ua_original));
    protocol_native("GetOwningPlayer",(uint64_t)(uintptr_t)ua_owner);
    protocol_native("SetPlayerTeam",(uint64_t)(uintptr_t)ua_set_team);
    protocol_native("SetPlayerAlliance",(uint64_t)(uintptr_t)ua_set_alliance);
    ZeroMemory(protocol_object,sizeof(protocol_object));ZeroMemory(protocol_owner,sizeof(protocol_owner));
    *(uint64_t *)(protocol_object+0x18)=protocol_full;
    *(uint64_t *)(protocol_owner+0x18)=0x2b7733752b61676cULL;
    *(uint64_t *)(protocol_owner+0x20)=protocol_full;
    *(uint64_t *)(protocol_owner+0x90)=(uint64_t)(uintptr_t)protocol_object;
    g_persistent_unit_resolver=(uint64_t)(uintptr_t)protocol_unit;
    g_persistent_agent_resolver=(uint64_t)(uintptr_t)protocol_agent;
}
static void ua_command(NativeCommand *cmd,uint32_t target) {
    ZeroMemory(cmd,sizeof(*cmd)); cmd->magic=WAR3_NATIVE_MAGIC;
    cmd->version=WAR3_NATIVE_VERSION;cmd->status=1;cmd->unit_handle=7;cmd->op_count=2;
    cmd->ops[0].kind=136;
    cmd->ops[0].handler=(uint64_t)(uintptr_t)protocol_object;
    cmd->ops[0].arg0=protocol_full;cmd->ops[0].arg1=(uint64_t)(uintptr_t)protocol_owner;
    cmd->ops[1].kind=307;cmd->ops[1].rawcode=target;
    cmd->ops[1].handler=107;cmd->ops[1].arg0=7;
}
static void ua_restore(NativeCommand *cmd,uint32_t target) {
    ua_command(cmd,target);cmd->ops[1].kind=308;cmd->ops[1].rawcode=0xffffffffu;
    cmd->ops[1].handler=target;cmd->ops[1].arg0=7;cmd->ops[1].arg1=107;
}
__declspec(dllexport) DWORD ua_run(uint32_t mode,uint32_t value,uint64_t *out) {
    NativeCommand cmd; uint64_t *extras=NULL,*next=NULL;uint32_t count=0,ncount=0;
    uint64_t restore[28];DWORD error;
    ua_setup();ua_command(&cmd,mode<=1?value:0);
    if(mode>=2 && mode<=4){ua_fault=mode;ua_at=value;}
    if(mode==5)ua_fail_alloc=1;
    if(mode==6)cmd.ops[1].handler=108;
    if(mode==7)cmd.ops[1].arg0=8;
    if(mode==8)cmd.ops[1].rawcode=14;
    if(mode==16){cmd.ops[1].arg1=1;protocol_teams[7]=0;}
    if(mode==17)cmd.ops[1].arg1=1;
    error=war3_ext_team(&cmd,&cmd.ops[1],1,NULL,0,&extras,&count);
    ua_fail_alloc=0;
    if(!error && (mode<=1 || mode>=10)) {
        memcpy(restore,extras,count*8);
        uint32_t assigned=cmd.ops[1].rawcode;
        if(mode==1) {
            assigned=(value+1)%12;ua_command(&cmd,assigned);
            error=war3_ext_team(&cmd,&cmd.ops[1],1,NULL,0,&next,&ncount);
            if(!error && count==ncount)for(uint32_t n=0;n<count;++n)
                restore[n]=(restore[n]&(((1ULL<<23)-1)|(1ULL<<36)))|
                           (next[n]&(((1ULL<<36)-1)^((1ULL<<23)-1)));
        }
        if(!error) {
            ua_restore(&cmd,assigned);
            if(mode>=10) {
                ua_calls=0;memcpy(ua_original,protocol_alliances,sizeof(ua_original));
                if(mode==10){restore[1]=restore[0];}
                if(mode==11){restore[0]=(restore[0]&~(31ULL<<18))|(7ULL<<18);}
                if(mode==12){restore[0]|=1ULL<<37;}
                if(mode==13){protocol_alliances[7][0][0]^=1;
                    memcpy(ua_original,protocol_alliances,sizeof(ua_original));}
                if(mode==14)ua_owner_value=108;
                if(mode==15)protocol_teams[7]=0;
            }
            error=war3_ext_team(&cmd,&cmd.ops[1],1,restore,count,&next,&ncount);
        }
    }
    out[0]=error;out[1]=ua_team_calls;out[2]=ua_calls;out[3]=(uint32_t)protocol_teams[7];
    out[4]=memcmp(ua_original,protocol_alliances,sizeof(ua_original))!=0;
    out[5]=cmd.ops[1].reserved;out[6]=cmd.ops[1].result;
    if(extras)HeapFree(GetProcessHeap(),0,extras);
    if(next)HeapFree(GetProcessHeap(),0,next);
    return 0;
}
static DWORD ua_packet(NativeCommand *cmd,uint64_t *extras,uint32_t count) {
    wchar_t path[MAX_PATH];DWORD bytes;command_path(path,MAX_PATH);
    cmd->reserved=count;
    HANDLE file=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE)return GetLastError();
    BOOL ok=WriteFile(file,cmd,sizeof(*cmd),&bytes,NULL);
    if(ok&&count)ok=WriteFile(file,extras,count*8,&bytes,NULL);
    CloseHandle(file);if(!ok)return ERROR_WRITE_FAULT;
    run_command();
    file=CreateFileW(path,GENERIC_READ,0,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE)return GetLastError();
    ok=ReadFile(file,cmd,sizeof(*cmd),&bytes,NULL);
    if(ok && cmd->reserved<=28 && cmd->reserved)ok=ReadFile(file,extras,cmd->reserved*8,&bytes,NULL);
    CloseHandle(file);DeleteFileW(path);return ok?0:ERROR_READ_FAULT;
}
__declspec(dllexport) DWORD ua_dispatch(const wchar_t *directory,uint32_t stale,uint64_t *out) {
    NativeCommand cmd;uint64_t extras[28];DWORD error;
    if(wcslen(directory)>=MAX_PATH-1)return ERROR_INVALID_PARAMETER;
    wcscpy(test_directory,directory);ua_setup();ua_command(&cmd,1);
    ZeroMemory(protocol_object,sizeof(protocol_object));ZeroMemory(protocol_owner,sizeof(protocol_owner));
    *(uint64_t *)(protocol_object+0x18)=protocol_full;
    *(uint64_t *)(protocol_owner+0x18)=0x2b7733752b61676cULL;
    *(uint64_t *)(protocol_owner+0x20)=protocol_full;
    *(uint64_t *)(protocol_owner+0x90)=(uint64_t)(uintptr_t)protocol_object;
    g_persistent_unit_resolver=(uint64_t)(uintptr_t)protocol_unit;
    g_persistent_agent_resolver=(uint64_t)(uintptr_t)protocol_agent;
    cmd.ops[0].handler=(uint64_t)(uintptr_t)protocol_object;
    cmd.ops[0].arg0=protocol_full^stale;cmd.ops[0].arg1=(uint64_t)(uintptr_t)protocol_owner;
    error=ua_packet(&cmd,extras,0);if(error)return error;
    if(cmd.status==2) {
        uint32_t count=cmd.reserved;NativeOp guard=cmd.ops[0];
        ua_restore(&cmd,1);cmd.ops[0]=guard;
        error=ua_packet(&cmd,extras,count);if(error)return error;
    }
    out[0]=cmd.status;out[1]=cmd.last_error;out[2]=ua_team_calls;
    out[3]=(uint32_t)protocol_teams[7];out[4]=memcmp(ua_original,protocol_alliances,sizeof(ua_original))!=0;
    return 0;
}
__declspec(dllexport) DWORD ua_query(uint64_t *out) {
    NativeCommand cmd;uint64_t *extras=NULL;uint32_t count=0;
    ua_setup();ua_command(&cmd,0);cmd.ops[1].kind=317;
    cmd.ops[1].rawcode=0;cmd.ops[1].handler=cmd.ops[1].arg0=0;
    DWORD error=war3_ext_query_selected_owner_team(&cmd,&cmd.ops[1],1,&extras,&count);
    out[0]=cmd.ops[1].result;out[1]=count;out[2]=ua_calls+ua_team_calls;out[3]=0;
    for(uint32_t n=0;n<count;++n)if(((extras[n]>>18)&31)==8)out[3]=extras[n];
    if(extras)HeapFree(GetProcessHeap(),0,extras);return error;
}
'''


@pytest.fixture(scope="module")
def unassigned_native():
    compiler = shutil.which("clang")
    assert compiler, "Unassigned diplomacy tests require the real SEH compiler"
    with tempfile.TemporaryDirectory(prefix="war3-unassigned-") as folder:
        source = Path(folder) / "unassigned.c"
        helper = Path(__file__).parent / "tools" / "war3_native_helper.c"
        harness = C_HARNESS.replace('#include "HELPER_SOURCE"', r'''
static DWORD ua_fail_alloc;
static LPVOID ua_allocate(HANDLE heap,DWORD flags,SIZE_T size) {
    if(ua_fail_alloc)return NULL;
    return HeapAlloc(heap,flags,size);
}
#define HeapAlloc ua_allocate
#include "HELPER_SOURCE"
#undef HeapAlloc
''')
        source.write_text(harness.replace("HELPER_SOURCE", helper.as_posix())
                          + CODEC_HARNESS + TRANSACTION_HARNESS, encoding="utf8")
        library = Path(folder) / "unassigned.dll"
        build = subprocess.run([compiler, "-shared", "-O2", "-Wno-microsoft-goto", str(source),
                                "-o", str(library), "-luser32", "-lkernel32"],
                               capture_output=True, text=True, timeout=90)
        assert build.returncode == 0, build.stderr
        native = ctypes.CDLL(str(library))
        native.ua_codec.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_uint64)]
        native.ua_codec.restype = ctypes.c_uint32
        native.ua_unpack.argtypes = [ctypes.c_uint64]
        native.ua_unpack.restype = ctypes.c_uint32
        native.ua_run.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint64)]
        native.ua_run.restype = ctypes.c_uint32
        native.ua_dispatch.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint64)]
        native.ua_dispatch.restype = ctypes.c_uint32
        native.ua_query.argtypes = [ctypes.POINTER(ctypes.c_uint64)]
        native.ua_query.restype = ctypes.c_uint32
        yield native
        import _ctypes
        _ctypes.FreeLibrary(native._handle)


@pytest.mark.parametrize("team,field,tag", [(-1, 0, 1 << 36), (0, 0, 0), (63, 63, 0)])
def test_unassigned_peer_roundtrip_distinguishes_minus_one_zero_and_63(unassigned_native, team, field, tag):
    out = (ctypes.c_uint64 * 5)()
    assert unassigned_native.ua_codec(team, out) == 0
    assert out[0] == (5 | (7 << 6) | (field << 12) | (3 << 18)
                      | (8 << 23) | (9 << 29) | (1 << 35) | tag)
    assert tuple(out[1:]) == (team & 0xFFFFFFFF, 3, 5, 7)
    assert module._team_relationships_by_player((out[0],)) == {3: out[0]}


@pytest.mark.parametrize("packed", [1 << 36, (1 << 35) | (1 << 37),
                                    (1 << 35) | (1 << 36) | (1 << 12),
                                    (1 << 35) | (28 << 18)])
def test_peer_tag_rejects_contradictory_or_high_bits(unassigned_native, packed):
    assert unassigned_native.ua_unpack(packed) == 13
    assert module._team_relationships_by_player((packed,)) is None


def test_merge_keeps_first_peer_tag_and_original_masks():
    first = (1 << 35) | (1 << 36) | (3 << 18) | 5 | (7 << 6) | (8 << 23)
    later = (1 << 35) | (3 << 18) | (2 << 12) | 8 | (9 << 29)
    merged = module._merge_player_team_relationship_snapshots((first,), (later,))
    assert merged == ((1 << 35) | (1 << 36) | (3 << 18) | 5 | (7 << 6) | (9 << 29),)
    assert module._team_relationships_by_player((first, first)) is None


def run_native(native, mode, value=1):
    out = (ctypes.c_uint64 * 7)()
    import faulthandler
    enabled = faulthandler.is_enabled()
    try:
        faulthandler.disable()  # the real helper intentionally handles injected SEH
        assert native.ua_run(mode, value, out) == 0
    finally:
        if enabled:
            faulthandler.enable()
    return tuple(out)


@pytest.mark.parametrize("target", [0, 1, 11, 12, 13])
@pytest.mark.parametrize("mode", [0, 1])
def test_unassigned_templates_restore_all_relations_without_set_team(unassigned_native, mode, target):
    error, team_calls, calls, team, changed, rollback, actual = run_native(unassigned_native, mode, target)
    assert error == 0
    assert (team_calls, team, changed, rollback, actual) == (0, 0xFFFFFFFF, 0, 0, 0xFFFFFFFF)
    assert calls > 0


@pytest.mark.parametrize("mode", [5, 6, 7, 8, 10, 11, 12, 13, 14, 15])
def test_unassigned_preflight_rejects_without_writes(unassigned_native, mode):
    values = run_native(unassigned_native, mode)
    assert values[0] != 0
    assert values[1:3] == (0, 0)
    assert values[4] == 0


@pytest.mark.parametrize("mode", [2, 3])
@pytest.mark.parametrize("at", [1, 17, 300])
def test_partial_alliance_failure_rolls_back_and_reports_phase(unassigned_native, mode, at):
    error, team_calls, calls, team, changed, rollback, phase = run_native(unassigned_native, mode, at)
    assert error != 0
    assert calls >= at
    assert (team_calls, team, changed, rollback) == (0, 0xFFFFFFFF, 0, 0)
    assert phase >> 32 == 0x554E4153


def test_failed_rollback_is_not_reported_as_success(unassigned_native):
    values = run_native(unassigned_native, 4, 17)
    assert values[0] != 0 and values[1] == 0 and values[3] == 0xFFFFFFFF
    assert values[4] == 1 and values[5] != 0


@pytest.mark.parametrize("stale,status", [(0, 2), (1, 3)])
def test_actual_dispatcher_preserves_guard_and_roundtrip(unassigned_native, tmp_path, stale, status):
    out = (ctypes.c_uint64 * 7)()
    assert unassigned_native.ua_dispatch(str(tmp_path) + "\\", stale, out) == 0
    assert out[0] == status
    assert tuple(out[2:5]) == (0, 0xFFFFFFFF, 0)


def bound_trainer(*responses):
    trainer = trainer_with_responses(*responses)
    selected = candidate()
    selected.native_snapshot = SimpleNamespace(owner=107, owner_id=7)
    trainer._direct_selected_context = Mock(return_value=(selected, 0x6000))
    return trainer


def ua_reply(assigned, peers, *, restoring=False):
    return [result(extras=peers), result(kind=308 if restoring else 307,
            result=0xFFFFFFFF if restoring else assigned, arg0=107,
            arg1=((assigned if restoring else 255) | (7 << 8) | (len(peers) << 16) | (1 << 32)))]


def test_python_first_unassigned_snapshot_survives_switch_and_verified_restore():
    first = relationship(1, 1, 2, 3, 4)
    second = relationship(1, 3, 4, 5, 6)
    trainer = bound_trainer(ua_reply(1, (first,)), ua_reply(2, (second,)),
                            ua_reply(2, (second,), restoring=True))
    trainer.set_selected_owner_team(1)
    trainer.set_selected_owner_team(2)
    saved = trainer._player_team_snapshots[(4321, 7)]
    assert (saved.original_team, saved.assigned_team, saved.virtual_team) == (-1, 2, True)
    assert saved.relationships[0] & 0xFFF == 129  # first forward=1/reverse=2
    assert trainer.restore_selected_owner_team(saved) == (107, 2, -1, 1)
    assert trainer._player_team_snapshots == {}
    request = trainer._run_native_helper_ops.call_args.args[1][1]
    assert request == (308, 0xFFFFFFFF, 2, 7, 107)
    assert trainer._run_native_helper_ops.call_args_list[1].args[1][1] == (307, 2, 107, 7, 1)


def test_python_owner_mismatch_rejected_before_transport():
    trainer = bound_trainer()
    saved = module.PlayerTeamSnapshot(4321, 7, 108, -1, 1, (), True)
    trainer._player_team_snapshots[(4321, 7)] = saved
    with pytest.raises(RuntimeError, match="玩家"):
        trainer.set_selected_owner_team(2)
    assert trainer._player_team_snapshots[(4321, 7)] is saved
    trainer._run_native_helper_ops.assert_not_called()


def test_python_failed_unassigned_restore_keeps_first_record():
    trainer = bound_trainer(RuntimeError("readback failed"))
    saved = module.PlayerTeamSnapshot(4321, 7, 107, -1, 1, (relationship(1, 1, 2, 3, 4),), True)
    trainer._player_team_snapshots[(4321, 7)] = saved
    with pytest.raises(RuntimeError, match="readback failed"):
        trainer.restore_selected_owner_team(saved)
    assert trainer._player_team_snapshots[(4321, 7)] is saved


def test_prior_unassigned_binding_allows_minus_one_and_refuses_native_team_change(unassigned_native):
    assert run_native(unassigned_native, 17)[0] == 0
    values = run_native(unassigned_native, 16)
    assert values[0] != 0 and values[1:3] == (0, 0)


def test_transport_reports_diplomacy_failure_and_rollback_not_clone_phase():
    trainer = object.__new__(module.War3Trainer)
    packet = bytearray(trainer._native_helper_command_size())
    trainer.NATIVE_HELPER_HEADER_STRUCT.pack_into(packet, 0, trainer.NATIVE_HELPER_MAGIC,
        77, 3, 2, 7, 29, 0)
    trainer.NATIVE_HELPER_OP_STRUCT.pack_into(packet, 80,
        307, 1, 107, 7, 0, (0x554E4153 << 32) | 4, 29, 29)
    with pytest.raises(RuntimeError) as caught:
        trainer._parse_native_helper_results(bytes(packet), 2)
    message = str(caught.value)
    assert "team_phase=4" in message and "team_rollback_error=29" in message
    assert "clone_phase" not in message


def test_unassigned_query_reads_peer_masks_without_any_setter(unassigned_native):
    out = (ctypes.c_uint64 * 4)()
    assert unassigned_native.ua_query(out) == 0
    assert tuple(out[:3]) == (0xFFFFFFFF, 25, 0)
    assert out[3] & (1 << 36) and ((out[3] >> 12) & 63) == 0


@pytest.mark.parametrize("changed", [False, True])
@pytest.mark.parametrize("language", ["zh", "en"])
def test_unassigned_named_monitor_verifies_live_diplomacy_without_changing_record(changed, language):
    from test_fullclone_player_name_monitor import named_reader
    saved = relationship(1, 1, 2, 3, 4)
    current = relationship(1, 0 if changed else 3, 4, 0, 0)
    trainer = named_reader(team=0xFFFFFFFF, slot=7, extras=(current, 1168, 0))
    response = trainer._run_native_helper_ops.return_value
    response[1] = result(kind=317, result=0xFFFFFFFF, arg0=0x111, arg1=7 | (1 << 8))
    snapshot = module.PlayerTeamSnapshot(4321, 7, 0x111, -1, 1, (saved,), True)
    trainer._player_team_snapshots[(4321, 7)] = snapshot
    status = trainer.query_selected_owner_team(include_player_name=True)
    assert status.assignment_verified is not changed
    assert trainer._player_team_snapshots[(4321, 7)] is snapshot
    text = module.format_player_team_status(status, language)
    if changed:
        assert ("关系已变化" if language == "zh" else "Alliances have changed") in text
        assert "外交模板" not in text and "diplomacy template" not in text
    else:
        assert ("队伍 2（外交模板）；原生队伍编号 -1" if language == "zh"
                else "Team 2") in text
        assert "-1" in text


def test_unassigned_virtual_snapshot_does_not_verify_a_changed_native_team():
    saved = relationship(1, 0, 0, 3, 4)
    snapshot = module.PlayerTeamSnapshot(4321, 7, 0x111, -1, 1, (saved,), True)
    assert not module._player_team_snapshot_matches_current_state(
        snapshot, 0, (relationship(1, 3, 4, 0, 0),))
    assert not module._player_team_snapshot_matches_current_state(
        module.PlayerTeamSnapshot(4321, 7, 0x111, -1, 1, (), True), -1, ())


def test_gui_unassigned_team_action_messages_are_not_team_zero(monkeypatch):
    if not os.environ.get("WAR3_R19_3_GUI_CHILD"):
        check = subprocess.run([sys.executable, "-m", "pytest", "-q",
            f"{__file__}::{test_gui_unassigned_team_action_messages_are_not_team_zero.__name__}"],
            env=dict(os.environ, WAR3_R19_3_GUI_CHILD="1"), capture_output=True,
            text=True, encoding="utf8", timeout=60)
        assert check.returncode == 0, check.stdout + check.stderr
        return
    import tkinter as tk
    from tkinter import messagebox
    real_tk = tk.Tk
    selected = [1]
    def hidden_root():
        root = real_tk(); root.withdraw(); return root
    def init(self):
        self.pid = 4321; self._player_team_snapshots = {}
    def set_team(self, target):
        selected[0] = target
        self._player_team_snapshots[(4321, 7)] = module.PlayerTeamSnapshot(4321, 7, 107, -1, target, (), True)
        return 107, -1, target, 1, 1, (), True
    def restore(self, snapshot):
        self._player_team_snapshots.clear()
        return 107, selected[0], -1, 1
    def walk(w):
        yield w
        for child in w.winfo_children(): yield from walk(child)
    def exercise(root, *args):
        widgets = list(walk(root))
        by_text = {str(w.cget("text")): w for w in widgets if "text" in w.keys()}
        by_text["连接/刷新进程"].invoke(); root.update()
        box = next(w for w in widgets if "values" in w.keys() and "恢复原队伍" in str(w.cget("values")))
        button = by_text["把选中玩家加入队伍 (Ctrl+F1)"]
        def texts():
            return "\n".join(str(root.getvar(w.cget("textvariable"))) for w in widgets
                if "textvariable" in w.keys() and str(w.cget("textvariable")))
        for target in ("队伍 2", "队伍 3", "中立被动队伍"):
            box.set(target); button.invoke(); root.update()
            text = texts()
            assert "原生队伍保持 -1" in text and "外交模板" in text and "队伍 0" not in text
            assert target in text
        box.set("恢复原队伍"); button.invoke(); root.update()
        text = texts()
        assert "恢复原始联盟关系" in text and "原生队伍保持 -1" in text and "队伍 0" not in text
        root.destroy()
    monkeypatch.setattr(module, "detect_ui_language", lambda: "zh")
    monkeypatch.setattr(tk, "Tk", hidden_root)
    monkeypatch.setattr(tk.Misc, "mainloop", exercise)
    monkeypatch.setattr(module.War3Trainer, "__init__", init)
    monkeypatch.setattr(module.War3Trainer, "refresh_window", lambda self, **kw: None)
    monkeypatch.setattr(module.War3Trainer, "list_resource_caches", lambda self: [])
    monkeypatch.setattr(module.War3Trainer, "prewarm_selected_unit_cache", lambda self: candidate())
    monkeypatch.setattr(module.War3Trainer, "set_selected_owner_team", set_team)
    monkeypatch.setattr(module.War3Trainer, "restore_selected_owner_team", restore)
    monkeypatch.setattr(module.War3Trainer, "query_selected_owner_shared_control", lambda self: (0, 107, 0))
    monkeypatch.setattr(module.War3Trainer, "query_selected_owner_team", lambda self, **kw:
        module.PlayerTeamStatus(4321, 7, 107, -1))
    monkeypatch.setattr(module.threading.Thread, "start", lambda self: self.run())
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **kw: pytest.fail(str(a)))
    module.run_gui()
