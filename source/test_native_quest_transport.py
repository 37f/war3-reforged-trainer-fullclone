"""Task payload expansion is isolated from all existing helper operations."""
import pytest
import war3_reforged_trainer as module
from war3_native_quest import encode_quest_request,_request
from test_native_quest import _plan

def test_task_request_has_a_paired_protocol_and_dedicated_operation():
    trainer=object.__new__(module.War3Trainer)
    words=encode_quest_request(_request(_plan(),'inspect'))
    payload=trainer._pack_native_helper_command(0,((320,0,0,0,0),),extra_values=words)
    header=trainer.NATIVE_HELPER_HEADER_STRUCT.unpack_from(payload)
    assert header[1]==79 and header[-1]==len(words)
    assert trainer.NATIVE_HELPER_OP_EXT_QUEST_INSPECT==320
    assert trainer.NATIVE_HELPER_OP_EXT_QUEST_EXECUTE==321
    assert trainer.NATIVE_HELPER_OP_EXT_QUEST_STATUS==322

@pytest.mark.parametrize('unit,ops,words',[
    (0,((307,0,0,0,0),),(0,)*29),
    (0,((320,0,0,0,0),(307,0,0,0,0)),(0,)*40),
    (1,((320,0,0,0,0),),(0,)*40),
    (0,((320,0,1,0,0),),(0,)*40),
    (0,((320,0,0,0,0),),(0,)*40),
    (0,((321,0,0,0,0),),encode_quest_request(_request(_plan(),'inspect'))),
])
def test_only_valid_task_envelope_can_use_expanded_input(unit,ops,words):
    trainer=object.__new__(module.War3Trainer)
    with pytest.raises(RuntimeError):trainer._pack_native_helper_command(unit,ops,extra_values=words)
