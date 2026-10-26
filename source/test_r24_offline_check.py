"""The read-only release has no quest mutation model or runtime bridge."""
import ctypes
from pathlib import Path
import war3_runtime_check

def test_helper_protocol_matches_readonly_release_without_hooking_a_game():
    helper=ctypes.WinDLL(str(Path(__file__).parent/'tools/war3_native_helper.dll'))
    protocol=helper.War3NativeProtocol;protocol.restype=ctypes.c_uint32;protocol.argtypes=[]
    assert protocol()==80

def test_offline_check_exercises_user_readable_conditions_only():
    assert war3_runtime_check.quest_text_self_check()=={'quest_readable_text_ok':True}
