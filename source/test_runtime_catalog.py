import json
import war3_runtime_check


def test_offline_runtime_checks_bundled_catalog_dependency(tmp_path):
    output=tmp_path/'runtime.json'
    assert war3_runtime_check.run(output)==0
    report=json.loads(output.read_text(encoding='utf8'))
    assert report['catalog_parser_ok'] is True
    assert report['stormlib_sha256']=='93321f6f030be5d7d79eb4cbf433d6ef7e83ce20d47d8963717f207d54afbe16'
