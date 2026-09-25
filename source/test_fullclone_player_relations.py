from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import war3_reforged_trainer as module


def candidate():
    return SimpleNamespace(unit_address=0x5000, handle=0x6000, owner_address=0x7000)


def result(kind=0, result=0, arg0=0, arg1=0, extras=()):
    return module.NativeHelperOpResult(
        kind=kind, result=result, arg0=arg0, arg1=arg1, extra_results=tuple(extras)
    )


def team_metadata(original, slot, peers, allied=0, virtual=False):
    return original | (slot << 8) | (peers << 16) | (allied << 24) | (int(virtual) << 32)


def relationship(peer, forward, reverse, assigned_forward, assigned_reverse, team=0):
    return (
        forward | (reverse << 6) | (team << 12) | (peer << 18)
        | (assigned_forward << 23) | (assigned_reverse << 29) | (1 << 35)
    )


def trainer_with_responses(*responses):
    trainer = module.War3Trainer.__new__(module.War3Trainer)
    trainer.pid = 4321
    trainer._player_control_snapshots = {}
    trainer._player_team_snapshots = {}
    trainer._direct_selected_context = Mock(return_value=(candidate(), 0x6000))
    trainer._run_native_helper_ops = Mock(side_effect=responses)
    return trainer


def test_first_team_snapshot_survives_repeated_switches():
    original = relationship(1, 1, 2, 3, 4, team=5)
    changed = relationship(1, 3, 4, 6, 7, team=8)
    first = [result(extras=(original,)), result(result=0, arg0=0x111,
        arg1=team_metadata(5, 24, 1, virtual=True))]
    second = [result(extras=(changed,)), result(result=7, arg0=0x111,
        arg1=team_metadata(0, 24, 1))]
    trainer = trainer_with_responses(first, second)

    trainer.set_selected_owner_team(0)
    trainer.set_selected_owner_team(7)

    saved = trainer._player_team_snapshots[(4321, 24)]
    assert saved.original_team == 5
    assert saved.assigned_team == 7
    assert saved.relationships[0] & module.PLAYER_TEAM_SNAPSHOT_BASE_MASK == (
        original & module.PLAYER_TEAM_SNAPSHOT_BASE_MASK
    )
    assert saved.relationships[0] & module.PLAYER_TEAM_SNAPSHOT_ASSIGNED_MASK == (
        changed & module.PLAYER_TEAM_SNAPSHOT_ASSIGNED_MASK
    )


def test_failed_restore_keeps_snapshot_for_retry():
    snap = module.PlayerTeamSnapshot(4321, 2, 0x111, 3, 4, (relationship(1, 1, 2, 3, 4),))
    trainer = trainer_with_responses(RuntimeError("readback failed"))
    trainer._player_team_snapshots[(4321, 2)] = snap
    with pytest.raises(RuntimeError, match="readback failed"):
        trainer.restore_selected_owner_team(snap)
    assert trainer._player_team_snapshots[(4321, 2)] is snap


def test_control_snapshot_is_process_and_player_scoped():
    query = [result(), result(result=0x111, arg0=1, arg1=24)]
    enable = [result(), result(result=0x111, arg0=1, arg1=24)]
    restore = [result(), result(result=0x111, arg0=3, arg1=24)]
    trainer = trainer_with_responses(query, enable, query, restore)
    assert trainer.toggle_selected_owner_shared_control() == (0x111, 3)
    assert trainer._player_control_snapshots == {(4321, 24): 1}
    assert trainer.toggle_selected_owner_shared_control() == (0x111, 1)
    assert trainer._player_control_snapshots == {}


@pytest.mark.parametrize("method, kind", [
    ("set_selected_unit_display_color", 309),
    ("set_selected_owner_player_color", 310),
])
def test_colors_use_current_persistent_protocol_operations(method, kind):
    op = result(kind=kind, result=4 if kind == 309 else 0x111,
                arg0=3, arg1=3 if kind == 309 else 0)
    trainer = trainer_with_responses([result(), op])
    getattr(trainer, method)(3)
    operations = trainer._run_native_helper_ops.call_args.args[1]
    assert operations[1][0] == kind
    assert not hasattr(trainer, "_native_player_owner_helper_dll_path")


def test_process_change_cleanup_is_present_on_runtime_path():
    source = open(module.__file__, encoding="utf-8").read()
    refresh = source[source.index("    def refresh_window"):source.index("    def _close_native_helper_persistent")]
    assert "self._player_control_snapshots = {}" in refresh
    assert "self._player_team_snapshots = {}" in refresh


def test_relation_ops_are_no_longer_placeholder_dispatch_cases():
    source = open("tools/war3_native_helper.c", encoding="utf-8").read()
    assert "war3_ext_shared_control(&cmd, op, i)" in source
    assert "war3_ext_team(&cmd, op, i, input_extra" in source
    assert "war3_ext_color(&cmd, op, i)" in source
    assert '"GetPlayerAlliance"' in source and '"SetPlayerAlliance"' in source
    assert "war3_repair_control_mask" in source
    assert "war3_repair_alliance_mask" in source
