"""Use the target process configuration, never assume the host shares its view."""
import pytest
from war3_current_map_script import SourceUnavailable

def test_target_policy_reply_binds_pid_and_creation_time():
    from war3_current_map_script import parse_game_source_policy
    assert parse_game_source_policy((0x31505352,1,5,20,0,0),5)==20

@pytest.mark.parametrize('words',[(0,1,5,20,0,0),(0x31505352,1,6,20,0,0),
    (0x31505352,1,5,0,0,0),(0x31505352,1,5,20,0,1),(0x31505352,1,5,20,0)])
def test_malformed_or_other_process_policy_cannot_authorize_source(words):
    from war3_current_map_script import parse_game_source_policy
    with pytest.raises(ValueError):parse_game_source_policy(words,5)

def test_game_policy_rejection_is_not_overruled_by_host_registry_state():
    from war3_current_map_script import parse_game_source_policy
    with pytest.raises(SourceUnavailable,match='游戏进程'):
        parse_game_source_policy((0x31505352,1,5,20,50,0),5)

def test_official_reader_checks_game_policy_before_reading_storage(tmp_path):
    from war3_current_map_script import RuntimeScriptSource,MapSourceMetadata
    metadata=MapSourceMetadata(7,'proof','Campaign/Classic/ROC/Human01.w3m','',False)
    def denied():raise SourceUnavailable('游戏进程实际覆盖设置未通过')
    source=RuntimeScriptSource(lambda:metadata,lambda:(),lambda path:None,lambda:1,
        casc_root=lambda:tmp_path,source_policy=denied)
    with pytest.raises(SourceUnavailable,match='游戏进程'):source.query()

def test_trainer_policy_bridge_is_read_only_and_has_its_own_operation():
    from unittest.mock import Mock
    import war3_reforged_trainer as module
    trainer=object.__new__(module.War3Trainer);trainer.pid=5
    trainer._run_native_helper_ops=Mock(return_value=[module.NativeHelperOpResult(323,0,
        extra_results=(0x31505352,1,5,20,0,0))])
    assert trainer.current_map_source_policy()==20
    trainer._run_native_helper_ops.assert_called_once_with(0,((323,0,0,0,0),),timeout_ms=5000)
