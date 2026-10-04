"""The team monitor must read current state without changing player relations."""
from unittest.mock import Mock
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

import war3_reforged_trainer as module
from test_fullclone_player_relations import candidate, relationship, result
from test_fullclone_protocol import C_HARNESS


def reader(team=3, slot=7, relationships=()):
    trainer = module.War3Trainer.__new__(module.War3Trainer)
    trainer.pid = 4321
    trainer._player_team_snapshots = {}
    trainer._direct_selected_context = Mock(return_value=(candidate(), 0x6000))
    trainer._run_native_helper_ops = Mock(return_value=[
        result(extras=relationships),
        result(kind=316, result=team, arg0=0x111,
               arg1=slot | (len(relationships) << 8)),
    ])
    return trainer


def test_monitor_reads_live_team_instead_of_creating_restore_snapshot():
    trainer = reader()
    status = trainer.query_selected_owner_team()
    assert (status.player_slot, status.native_team, status.assigned_team) == (7, 3, None)
    assert trainer._player_team_snapshots == {}
    assert module.format_player_team_status(status) == "玩家 8：队伍 4"
    operations = trainer._run_native_helper_ops.call_args.args[1]
    assert operations[1] == (316, 0, 0, 0, 0)


def test_neutral_virtual_team_requires_current_alliance_readback():
    saved = relationship(1, 0, 0, 63, 63)
    current = relationship(1, 63, 63, 0, 0)
    trainer = reader(team=24, slot=24, relationships=(current,))
    snapshot = module.PlayerTeamSnapshot(4321, 24, 0x111, 24, 1, (saved,), True)
    trainer._player_team_snapshots[(4321, 24)] = snapshot
    status = trainer.query_selected_owner_team()
    assert status.assigned_team == 1 and status.assignment_verified
    assert "队伍 2（外交模板）" in module.format_player_team_status(status)
    assert "原生队伍编号 24" in module.format_player_team_status(status)
    assert trainer._player_team_snapshots[(4321, 24)] is snapshot


def test_changed_map_relations_do_not_display_stale_virtual_team():
    trainer = reader(team=24, slot=24, relationships=(relationship(1, 0, 0, 0, 0),))
    trainer._player_team_snapshots[(4321, 24)] = module.PlayerTeamSnapshot(
        4321, 24, 0x111, 24, 7, (relationship(1, 0, 0, 63, 63),), True
    )
    status = trainer.query_selected_owner_team()
    assert not status.assignment_verified
    text = module.format_player_team_status(status)
    assert "关系已变化" in text and "队伍 8" not in text


@pytest.mark.parametrize("slot,label", [(24, "中立敌对"), (27, "中立被动")])
def test_neutral_slots_are_not_guessed_as_lobby_teams(slot, label):
    status = reader(team=slot, slot=slot).query_selected_owner_team()
    text = module.format_player_team_status(status)
    assert label in text and f"原生队伍编号 {slot}" in text
    assert f"队伍 {slot + 1}" not in text


@pytest.mark.parametrize("team,slot", [(-1, 7), (64, 7), (3, 28)])
def test_malformed_monitor_metadata_is_rejected(team, slot):
    with pytest.raises(RuntimeError, match="队伍"):
        reader(team=team, slot=slot).query_selected_owner_team()


def test_missing_selection_does_not_send_monitor_query():
    trainer = reader()
    trainer._direct_selected_context.side_effect = RuntimeError("未选中单位")
    with pytest.raises(RuntimeError, match="未选中单位"):
        trainer.query_selected_owner_team()
    trainer._run_native_helper_ops.assert_not_called()


def test_snapshot_from_other_process_is_not_used():
    trainer = reader(team=3)
    trainer._player_team_snapshots[(1234, 7)] = module.PlayerTeamSnapshot(
        1234, 7, 0x111, 3, 9, (), True
    )
    assert trainer.query_selected_owner_team().assigned_team is None


MONITOR_HARNESS = r'''
static uint32_t monitor_writes;
static uint64_t monitor_neutral_owner(uint64_t unit) { return unit == 7 ? 124 : 0; }
static void monitor_set_team(uint64_t player, int32_t team) { ++monitor_writes; }
static void monitor_set_alliance(uint64_t a, uint64_t b, int32_t kind, uint32_t value) { ++monitor_writes; }
__declspec(dllexport) DWORD monitor_read(uint32_t mode, uint64_t *out) {
    NativeCommand cmd = {0};
    NativeOp *op = &cmd.ops[1];
    uint64_t *extras = NULL;
    uint32_t count = 0;
    DWORD error;
    ZeroMemory(protocol_teams, sizeof(protocol_teams));
    ZeroMemory(protocol_alliances, sizeof(protocol_alliances));
    monitor_writes = 0;
    protocol_setup_natives();
    protocol_native("SetPlayerTeam", (uint64_t)(uintptr_t)monitor_set_team);
    protocol_native("SetPlayerAlliance", (uint64_t)(uintptr_t)monitor_set_alliance);
    protocol_teams[7] = mode == 1 ? -1 : 3;
    protocol_teams[24] = 24;
    if (mode == 2) protocol_native("GetOwningPlayer", (uint64_t)(uintptr_t)monitor_neutral_owner);
    if (mode == 3) protocol_native("GetPlayerTeam", 0);
    cmd.op_count = 2; cmd.unit_handle = 7;
    cmd.ops[0].kind = WAR3_NATIVE_OP_VALIDATE_UNIT_IDENTITY;
    op->kind = 316;
    if (mode == 4) op->rawcode = 1;
    error = war3_ext_query_selected_owner_team(&cmd, op, 1, &extras, &count);
    out[0] = op->result; out[1] = op->arg0; out[2] = op->arg1;
    out[3] = count; out[4] = monitor_writes;
    if (extras) HeapFree(GetProcessHeap(), 0, extras);
    return error;
}
'''


@pytest.fixture(scope="module")
def native_monitor():
    compiler = shutil.which("clang")
    if not compiler:
        pytest.skip("Microsoft-SEH-capable clang required")
    with tempfile.TemporaryDirectory(prefix="war3-team-monitor-") as temporary:
        root = Path(temporary)
        source = root / "monitor.c"
        helper = Path(__file__).parent / "tools" / "war3_native_helper.c"
        source.write_text(C_HARNESS.replace("HELPER_SOURCE", helper.as_posix()) + MONITOR_HARNESS,
                          encoding="utf-8")
        library = root / "monitor.dll"
        subprocess.run([compiler, "-shared", "-O2", "-Wno-microsoft-goto", str(source),
                        "-o", str(library), "-luser32", "-lkernel32"],
                       check=True, capture_output=True, timeout=60)
        native = ctypes.CDLL(str(library))
        native.monitor_read.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint64)]
        native.monitor_read.restype = ctypes.c_uint32
        yield native
        import _ctypes
        _ctypes.FreeLibrary(native._handle)


@pytest.mark.parametrize("mode,team,slot", [(0, 3, 7), (2, 24, 24)])
def test_compiled_native_query_reports_live_team_without_setter_calls(native_monitor, mode, team, slot):
    values = (ctypes.c_uint64 * 5)()
    assert native_monitor.monitor_read(mode, values) == 0
    assert values[0] == team and values[2] & 255 == slot
    assert values[3] == 25 and values[4] == 0


@pytest.mark.parametrize("mode,error", [(1, 13), (3, 127), (4, 13)])
def test_compiled_native_query_rejects_invalid_state_without_writes(native_monitor, mode, error):
    values = (ctypes.c_uint64 * 5)()
    assert native_monitor.monitor_read(mode, values) == error
    assert values[4] == 0


def test_real_gui_team_controls_read_without_changing_destination(monkeypatch):
    import tkinter as tk
    from tkinter import messagebox

    real_tk = tk.Tk
    query = Mock(return_value=module.PlayerTeamStatus(4321, 7, 0x111, 3))
    popup = Mock()

    def hidden_root():
        root = real_tk()
        root.withdraw()
        return root

    def fake_init(self):
        self.pid = 4321

    def exercise(root, *args):
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)

        widgets = list(walk(root))
        by_text = {str(w.cget("text")): w for w in widgets if "text" in w.keys()}
        by_text["连接/刷新进程"].invoke()
        root.update()
        team_box = next(w for w in widgets if "values" in w.keys()
                        and "恢复原队伍" in str(w.cget("values")))
        current_label = next(w for w in widgets if "textvariable" in w.keys()
                             and str(w.cget("textvariable"))
                             and str(root.getvar(w.cget("textvariable"))).startswith("选中玩家队伍："))
        before = team_box.get()
        by_text["读取队伍"].invoke()
        root.update()
        assert root.getvar(current_label.cget("textvariable")) == "玩家 8：队伍 4"
        assert team_box.get() == before
        # A disabled monitor must discard its already queued read completion.
        by_text["监视队伍（每秒刷新）"].invoke()
        by_text["监视队伍（每秒刷新）"].invoke()
        root.update()
        assert "已关闭" in root.getvar(current_label.cget("textvariable"))
        query.side_effect = RuntimeError("未选中单位")
        by_text["读取队伍"].invoke()
        root.update()
        assert "未选中单位" in root.getvar(current_label.cget("textvariable"))
        popup.assert_not_called()
        root.destroy()

    monkeypatch.setattr(module, "detect_ui_language", lambda: "zh")
    monkeypatch.setattr(tk, "Tk", hidden_root)
    monkeypatch.setattr(tk.Misc, "mainloop", exercise)
    monkeypatch.setattr(module.War3Trainer, "__init__", fake_init)
    monkeypatch.setattr(module.War3Trainer, "refresh_window", lambda self, **kwargs: None)
    monkeypatch.setattr(module.War3Trainer, "query_selected_owner_team", query)
    monkeypatch.setattr(module.threading.Thread, "start", lambda self: self.run())
    monkeypatch.setattr(messagebox, "showerror", popup)
    module.run_gui()
