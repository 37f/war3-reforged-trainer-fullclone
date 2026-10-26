"""Package checks cannot query or attach to a game."""
import ctypes
from pathlib import Path
import war3_runtime_check

def test_compiled_helper_reports_the_paired_protocol_without_a_game():
    helper=ctypes.WinDLL(str(Path(__file__).parent/'tools/war3_native_helper.dll'))
    protocol=helper.War3NativeProtocol;protocol.restype=ctypes.c_uint32;protocol.argtypes=[]
    assert protocol()==79

def test_offline_original_flow_model_and_fail_closed_dispatch():
    result=war3_runtime_check.quest_execution_self_check()
    assert result=={'quest_completion_plan_ok':True,'quest_wire_ok':True,
        'quest_execution_guard_ok':True,'quest_native_protocol':79}
