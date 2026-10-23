"""Player names belong to the same read-only snapshot as the displayed team."""
import ctypes
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import war3_reforged_trainer as module
from test_fullclone_player_relations import candidate, result
from test_fullclone_protocol import C_HARNESS


def named_reader(data=b"Alpha", *, error=0, slot=7, team=3, extras=None):
    trainer = module.War3Trainer.__new__(module.War3Trainer)
    trainer.pid = 4321
    trainer._player_team_snapshots = {}
    trainer._direct_selected_context = Mock(return_value=(candidate(), 0x6000))
    padded = data + b"\0" * (-len(data) % 8)
    words = struct.unpack(f"<{len(padded) // 8}Q", padded) if padded else ()
    values = (error, len(data), *words) if extras is None else extras
    trainer._run_native_helper_ops = Mock(return_value=[
        result(extras=values), result(kind=317, result=team, arg0=0x111, arg1=slot),
    ])
    return trainer


@pytest.mark.parametrize("name", ["森林巡逻队Alpha", "石塔野生单位", "Neutral Passive", "  Alpha  "])
def test_player_name_is_decoded_without_changing_team_or_creating_snapshot(name):
    trainer = named_reader(name.encode("utf-8"))
    status = trainer.query_selected_owner_team(include_player_name=True)
    assert status.player_name == name and status.player_name_error == 0
    assert (status.player_slot, status.native_team) == (7, 3)
    assert trainer._player_team_snapshots == {}
    assert module.format_player_team_status(status) == f"玩家 8（{name}）：队伍 4"
    assert trainer._run_native_helper_ops.call_args.args[1][1] == (317, 0, 0, 0, 0)


@pytest.mark.parametrize("slot,name", [(24, "中立敌对"), (27, "中立被动")])
def test_neutral_name_keeps_special_slot_identity(slot, name):
    status = named_reader(name.encode(), slot=slot, team=slot).query_selected_owner_team(
        include_player_name=True)
    text = module.format_player_team_status(status)
    assert f"玩家 {slot + 1}" in text and name in text and "槽位" in text
    assert f"原生队伍编号 {slot}" in text and f"队伍 {slot + 1}" not in text


@pytest.mark.parametrize("slot", [24, 27])
@pytest.mark.parametrize("language", ["zh", "en"])
def test_neutral_missing_name_hides_only_unavailable_label(slot, language):
    status = module.PlayerTeamStatus(4321, slot, 0x111, slot, player_name_error=1168)
    text = module.format_player_team_status(status, language)
    assert "名称暂无法读取" not in text and "Name temporarily unavailable" not in text
    assert f"玩家 {slot + 1}" in text if language == "zh" else f"Player {slot + 1}" in text
    assert f"原生队伍编号 {slot}" in text if language == "zh" else f"Native team ID {slot}" in text
    assert "槽位" in text if language == "zh" else "slot" in text
    assert "（）" not in text and "()" not in text


@pytest.mark.parametrize("slot", [0, 23, 25, 26])
def test_other_player_slots_keep_missing_name_label(slot):
    status = module.PlayerTeamStatus(4321, slot, 0x111, 3, player_name_error=1168)
    assert "名称暂无法读取" in module.format_player_team_status(status)
    assert "Name temporarily unavailable" in module.format_player_team_status(status, "en")


@pytest.mark.parametrize("data,error", [(b"", 1168), (b"", 127), (b"", 487)])
def test_name_failure_preserves_current_team_and_marks_name_unavailable(data, error):
    status = named_reader(data, error=error).query_selected_owner_team(include_player_name=True)
    assert status.player_name is None and status.player_name_error == error
    assert "名称暂无法读取" in module.format_player_team_status(status)
    assert "队伍 4" in module.format_player_team_status(status)


@pytest.mark.parametrize("data", [b"\xff", b"\xe6\x9e", b"Alpha\0Other", b"A" * 513])
def test_invalid_name_does_not_destroy_other_current_status(data):
    status = named_reader(data).query_selected_owner_team(include_player_name=True)
    assert status.player_name is None and status.player_name_error != 0
    assert status.native_team == 3


def test_exact_512_byte_utf8_name_is_not_truncated():
    name = "森" * 170 + "AB"
    assert len(name.encode()) == 512
    assert named_reader(name.encode()).query_selected_owner_team(
        include_player_name=True).player_name == name


@pytest.mark.parametrize("extras", [(), (0,), (0, 6), (0, 1, 65, 0), (0, 1, -1),
                                   (1 << 40, 0), (127, 1, 65), (0, 1, 0x4241)])
def test_malformed_name_transport_is_rejected(extras):
    with pytest.raises(RuntimeError, match="名字|名称|队伍"):
        named_reader(extras=extras).query_selected_owner_team(include_player_name=True)


def test_empty_name_is_unavailable_and_selection_failure_does_not_reuse_last_name():
    trainer = named_reader(b"")
    status = trainer.query_selected_owner_team(include_player_name=True)
    assert status.player_name is None and status.player_name_error == 1168
    trainer._direct_selected_context.side_effect = RuntimeError("未选中单位")
    with pytest.raises(RuntimeError, match="未选中单位"):
        trainer.query_selected_owner_team(include_player_name=True)


@pytest.mark.parametrize("change", ["clear", "unit", "generation", "owner", "handle"])
def test_completed_name_query_rejects_selection_changed_while_waiting(change):
    trainer = named_reader("晚到的玩家A".encode())
    response = trainer._run_native_helper_ops.return_value
    def complete(*args, **kwargs):
        if change == "clear":
            trainer._direct_selected_context.side_effect = RuntimeError("未选中单位")
        else:
            current = candidate()
            field = {"unit": "unit_address", "generation": "handle", "owner": "owner_address"}.get(change)
            if field:
                setattr(current, field, getattr(current, field) + 8)
            trainer._direct_selected_context.return_value = (current, 0x6008 if change == "handle" else 0x6000)
        return response
    trainer._run_native_helper_ops.side_effect = complete
    with pytest.raises(RuntimeError, match="选中|选择"):
        trainer.query_selected_owner_team(include_player_name=True)


def test_legacy_316_does_not_add_a_selection_read():
    trainer = named_reader()
    trainer._run_native_helper_ops.return_value = [result(), result(kind=316, result=3, arg0=0x111, arg1=7)]
    trainer.query_selected_owner_team()
    assert trainer._direct_selected_context.call_count == 1


NAME_HARNESS = r'''
#ifdef WAR3_PLAYER_NAME_MAX_BYTES
static uint8_t name_player[0x90], name_storage[0x40];
static uint8_t name_text[1024];
static unsigned name_fault, name_resolves;
static uint64_t name_resolver(uint64_t handle) {
    ++name_resolves;
    if (name_fault == 4 && name_resolves > 1) return 0;
    return handle == 2 ? (uint64_t)(uintptr_t)name_player : 0;
}
static void name_prepare(const char *text, unsigned fault) {
    ZeroMemory(name_player, sizeof(name_player));
    ZeroMemory(name_storage, sizeof(name_storage));
    memset(name_text, 'Z', sizeof(name_text));
    if (text && strlen(text) < sizeof(name_text)) memcpy(name_text, text, strlen(text)+1);
    name_fault=fault; name_resolves=0;
    *(uint64_t *)(name_player+0x80) = fault==2 ? 0 : (uint64_t)(uintptr_t)name_storage;
    *(uint64_t *)(name_storage+0x38) = fault==3 ? 0 : fault==5 ? 1 : (uint64_t)(uintptr_t)name_text;
    g_player_name_module = fault==1 ? NULL : GetModuleHandleW(NULL);
    g_player_name_resolver = fault==1 ? 0 : (uint64_t)(uintptr_t)name_resolver;
}
#endif
__declspec(dllexport) DWORD name_copy(const char *text,unsigned fault,unsigned char *output,uint32_t *length) {
#ifdef WAR3_PLAYER_NAME_MAX_BYTES
    NativeCommand cmd={0}; name_prepare(text,fault);
    protocol_setup_natives();
    ZeroMemory(protocol_object,sizeof(protocol_object)); ZeroMemory(protocol_owner,sizeof(protocol_owner));
    *(uint64_t *)(protocol_object+0x18)=protocol_full;
    *(uint64_t *)(protocol_owner+0x18)=0x2b7733752b61676cULL;
    *(uint64_t *)(protocol_owner+0x20)=protocol_full;
    *(uint64_t *)(protocol_owner+0x90)=(uint64_t)(uintptr_t)protocol_object;
    g_persistent_unit_resolver=(uint64_t)(uintptr_t)protocol_unit;
    g_persistent_agent_resolver=(uint64_t)(uintptr_t)protocol_agent;
    cmd.unit_handle=7;cmd.op_count=2;cmd.ops[0].kind=WAR3_NATIVE_OP_VALIDATE_UNIT_IDENTITY;
    cmd.ops[0].handler=(uint64_t)(uintptr_t)protocol_object;cmd.ops[0].arg0=protocol_full;
    cmd.ops[0].arg1=(uint64_t)(uintptr_t)protocol_owner;
    return war3_read_bound_player_name(&cmd,2,output,512,length);
#else
    (void)text;(void)fault;(void)output;*length=0;return ERROR_NOT_SUPPORTED;
#endif
}
__declspec(dllexport) DWORD name_dispatch(const wchar_t *directory,uint32_t *out) {
#ifdef WAR3_PLAYER_NAME_MAX_BYTES
    name_prepare("Alpha",0);
#endif
    return protocol_dispatch(directory,WAR3_NATIVE_VERSION,317,1,out);
}
'''


@pytest.fixture(scope="module")
def name_native():
    compiler = shutil.which("clang")
    assert compiler, "Name ABI regressions require a real SEH-capable clang"
    with tempfile.TemporaryDirectory(prefix="war3-r19-name-") as directory:
        source = Path(directory) / "name.c"
        helper = Path(__file__).parent / "tools/war3_native_helper.c"
        harness = C_HARNESS.replace("|| kind == 316)", "|| kind == 316 || kind == 317)")
        source.write_text(harness.replace("HELPER_SOURCE", helper.as_posix()) + NAME_HARNESS, encoding="utf8")
        library = Path(directory) / "name.dll"
        build = subprocess.run([compiler, "-shared", "-O2", "-Wno-microsoft-goto", str(source),
                                "-o", str(library), "-luser32", "-lkernel32"],
                               capture_output=True, text=True, timeout=90)
        assert build.returncode == 0, build.stderr
        native = ctypes.CDLL(str(library))
        native.name_copy.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_uint)]
        native.name_copy.restype = ctypes.c_uint
        native.name_dispatch.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint)]
        native.name_dispatch.restype = ctypes.c_uint
        yield native
        import _ctypes
        _ctypes.FreeLibrary(native._handle)


@pytest.mark.parametrize("data", ["森林巡逻队Alpha".encode(), b"A" * 512])
def test_c_reader_copies_existing_utf8_storage(name_native, data):
    output = ctypes.create_string_buffer(512)
    length = ctypes.c_uint()
    assert name_native.name_copy(data, 0, output, ctypes.byref(length)) == 0
    assert length.value == len(data) and output.raw[:length.value] == data


@pytest.mark.parametrize("data,error", [(b"", 1168), (b"\xff", 1113), (b"A" * 513, 122)])
def test_c_reader_rejects_empty_invalid_and_overlong_without_partial_result(name_native, data, error):
    output = ctypes.create_string_buffer(512)
    length = ctypes.c_uint(99)
    assert name_native.name_copy(data, 0, output, ctypes.byref(length)) == error
    assert length.value == 0


@pytest.mark.parametrize("fault", [1, 2, 3, 4, 5])
def test_c_reader_fails_closed_on_unavailable_and_changed_storage(name_native, fault):
    output = ctypes.create_string_buffer(512)
    length = ctypes.c_uint(99)
    assert name_native.name_copy(b"Alpha", fault, output, ctypes.byref(length)) != 0
    assert length.value == 0


def test_new_query_reaches_real_c_dispatcher(name_native, tmp_path):
    out = (ctypes.c_uint * 3)()
    assert name_native.name_dispatch(str(tmp_path) + "\\", out) == 0
    assert tuple(out) == (2, 0, 0)


def test_existing_gui_monitor_refreshes_name_and_clears_stale_results(monkeypatch):
    # Each real Tk workflow owns its interpreter/process. Repeated Tk destruction
    # in one pytest process can tear down Tcl globals during the next Tk init.
    if not os.environ.get("WAR3_R19_NAME_GUI_CHILD"):
        environment = dict(os.environ, WAR3_R19_NAME_GUI_CHILD="1")
        check = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", f"{__file__}::{test_existing_gui_monitor_refreshes_name_and_clears_stale_results.__name__}"],
            env=environment, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert check.returncode == 0, check.stdout + check.stderr
        return
    import tkinter as tk
    from tkinter import messagebox

    real_tk = tk.Tk
    real_query = module.War3Trainer.query_selected_owner_team
    instances = []
    status = [module.PlayerTeamStatus(4321, 7, 0x111, 3, player_name="森林巡逻队Alpha")]
    popup = Mock()

    def hidden_root():
        root = real_tk()
        root.withdraw()
        return root

    def fake_init(self):
        self.pid = 4321
        instances.append(self)

    def query(self, *, include_player_name=False):
        assert include_player_name, "The existing GUI must request actual names"
        if isinstance(status[0], Exception):
            raise status[0]
        if callable(status[0]):
            return status[0]()
        return status[0]

    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    def exercise(root, *args):
        widgets = list(walk(root))
        by_text = {str(w.cget("text")): w for w in widgets if "text" in w.keys()}
        by_text["连接/刷新进程"].invoke()
        root.update()
        current = next(w for w in widgets if "textvariable" in w.keys()
                       and str(w.cget("textvariable"))
                       and str(root.getvar(w.cget("textvariable"))).startswith("选中玩家队伍："))
        value = lambda: str(root.getvar(current.cget("textvariable")))
        by_text["读取队伍"].invoke()
        root.update()
        assert "森林巡逻队Alpha" in value() and "队伍 4" in value()
        # Player names are game data, never input to the UI translator.
        status[0] = module.PlayerTeamStatus(4321, 7, 0x111, 3, player_name="英雄（玩家）")
        by_text["读取队伍"].invoke()
        root.update()
        language = next(w for w in widgets if w.winfo_class() == "TCombobox"
                        and tuple(w.cget("values")) == ("中文", "English"))
        language.set("English")
        language.event_generate("<<ComboboxSelected>>")
        root.update()
        assert "英雄（玩家）" in value() and "Team 4" in value()
        language.set("中文")
        language.event_generate("<<ComboboxSelected>>")
        root.update()
        assert "英雄（玩家）" in value() and "队伍 4" in value()
        by_text["监视队伍（每秒刷新）"].invoke()
        root.update()
        status[0] = module.PlayerTeamStatus(4321, 2, 0x222, 1, player_name="另一玩家")
        tick = next(root.tk.call("after", "info", timer)[0]
                    for timer in root.tk.call("after", "info")
                    if "selected_player_team_monitor_tick" in str(root.tk.call("after", "info", timer)))
        root.tk.call(tick)
        root.update()
        assert "另一玩家" in value() and "森林巡逻队Alpha" not in value()
        assert "队伍 2" in value()
        status[0] = RuntimeError("未选中单位")
        by_text["读取队伍"].invoke()
        root.update()
        assert "未选中单位" in value() and "另一玩家" not in value()
        status[0] = module.PlayerTeamStatus(4321, 7, 0x111, 3, player_name_error=127)
        by_text["读取队伍"].invoke()
        root.update()
        assert "名称暂无法读取" in value() and "队伍 4" in value()
        status[0] = module.PlayerTeamStatus(4320, 7, 0x111, 3, player_name="旧进程名字")
        by_text["读取队伍"].invoke()
        root.update()
        assert "旧进程名字" not in value() and "队伍 4" not in value()
        # A read completion queued before disabling must not restore its name.
        status[0] = module.PlayerTeamStatus(4321, 7, 0x111, 3, player_name="过期名字")
        by_text["读取队伍"].invoke()
        by_text["监视队伍（每秒刷新）"].invoke()
        root.update()
        assert "已关闭" in value() and "过期名字" not in value()
        # Manual read, monitor OFF: selection changes while the helper is pending.
        # Run the real query/parser; the controlled helper completion changes the
        # selection before returning its old A result to the GUI worker.
        for cleared in (False, True):
            delayed = named_reader("晚到的玩家A".encode())
            response = delayed._run_native_helper_ops.return_value
            def complete(*args, **kwargs):
                if cleared:
                    delayed._direct_selected_context.side_effect = RuntimeError("未选中单位")
                else:
                    other = SimpleNamespace(**vars(candidate()))
                    other.unit_address += 8
                    delayed._direct_selected_context.return_value = (other, 0x6008)
                return response
            delayed._run_native_helper_ops.side_effect = complete
            status[0] = lambda: real_query(delayed, include_player_name=True)
            by_text["读取队伍"].invoke()
            root.update()
            assert "晚到的玩家A" not in value() and "选中" in value()
        popup.assert_not_called()
        root.destroy()

    monkeypatch.setattr(module, "detect_ui_language", lambda: "zh")
    monkeypatch.setattr(tk, "Tk", hidden_root)
    monkeypatch.setattr(tk.Misc, "mainloop", exercise)
    monkeypatch.setattr(module.War3Trainer, "__init__", fake_init)
    monkeypatch.setattr(module.War3Trainer, "refresh_window", lambda self, **kwargs: None)
    # Startup timers must not reach a real game through the deliberately minimal fake.
    monkeypatch.setattr(module.War3Trainer, "list_resource_caches", lambda self: [])
    monkeypatch.setattr(module.War3Trainer, "prewarm_selected_unit_cache", lambda self: candidate())
    monkeypatch.setattr(module.War3Trainer, "query_selected_owner_team", query)
    monkeypatch.setattr(module.threading.Thread, "start", lambda self: self.run())
    monkeypatch.setattr(messagebox, "showerror", popup)
    module.run_gui()
