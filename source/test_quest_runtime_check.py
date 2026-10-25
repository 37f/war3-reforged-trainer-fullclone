"""The frozen check must exercise the parser/model without opening a game."""
def test_offline_quest_selfcheck_covers_source_model_semantics_and_controller():
    from war3_runtime_check import quest_self_check
    result=quest_self_check()
    assert result=={'quest_source_model_ok':True,'quest_analysis_ok':True,'quest_controller_ok':True}
