"""R12 UI/hotkey contract on top of the v1.0.19 interface."""
from pathlib import Path

import war3_reforged_trainer as module


def specs():
    return {item.name: item for item in module.ELEPHANT_HOTKEY_SPECS}


def test_established_extension_hotkeys_are_registered():
    expected = {
        "revive_selected_owner_heroes": "Ctrl+F+H",
        "fill_selected_unit_vitals": "Ctrl+空格",
        "give_to_player": "Ctrl+I+U",
        "control_selected_player": "Ctrl+I+O",
        "set_selected_player_team": "Ctrl+F1",
        "replace_unit": "Ctrl+U+8",
        "summon_infernal": "Ctrl+F2",
        "gold_mine": "Alt+空格",
    }
    actual = specs()
    for name, combo in expected.items():
        assert name in actual
        assert actual[name].label.startswith(combo)


def test_r12_defaults_and_modes_are_preserved_in_gui_source():
    source = Path(module.__file__).read_text(encoding="utf-8")
    for fragment in (
        'elephant_hotkey_hero_fixed = tk.BooleanVar(value=False)',
        'elephant_hotkey_attributes_fixed = tk.BooleanVar(value=False)',
        'elephant_victory_mode = tk.StringVar(value="cheat")',
        'elephant_replace_unit_rawcode = tk.StringVar(value="zhyd")',
        'elephant_gold_mine = tk.StringVar(value="100000")',
        'text="玩家直接胜利"',
        'silent_empty: bool = False',
        'elif silent_empty:',
    ):
        assert fragment in source
    assert "使用选中的玩家单位" not in source


def test_game_speed_panel_and_callback_are_removed():
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "elephant_game_speed" not in source
    assert "elephant_set_game_speed" not in source
    assert 'text="设置游戏速度"' not in source


def test_extension_callbacks_use_persistent_controller_methods():
    source = Path(module.__file__).read_text(encoding="utf-8")
    callback_region = source[source.index("    hotkey_callbacks:"):
                             source.index("    hotkey_specs_by_name")]
    expected = {
        '"hero_level"': "elephant_hotkey_hero_level",
        '"hero_attributes"': "elephant_hotkey_hero_attributes",
        '"gold_mine"': "elephant_gold_mine_set",
        '"revive_selected_owner_heroes"': "elephant_revive_selected_owner_heroes",
        '"fill_selected_unit_vitals"': "elephant_fill_selected_unit_vitals",
        '"replace_unit"': "elephant_replace_unit",
        '"summon_infernal"': "elephant_summon_infernal",
        '"instant_victory"': "elephant_instant_victory",
        '"ignore_collision"': "elephant_toggle_unit_pathing",
    }
    for key, callback in expected.items():
        assert key in callback_region and callback in callback_region
