"""The R19 verifier must reject old wire protocols and stale frozen sources."""
import importlib.util
import marshal
from pathlib import Path

import pytest


def verifier():
    path = Path(__file__).parent / "analysis/verify-fullclone-package.py"
    spec = importlib.util.spec_from_file_location("r19_package_verifier", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_for(module, protocol):
    operations = dict(module.EXPECTED_OPERATIONS, NATIVE_HELPER_OP_EXT_QUERY_SELECTED_OWNER_STATUS=317)
    return 'APP_VERSION = "1.0.19"\n' + f"NATIVE_HELPER_VERSION = {protocol}\n" + "".join(
        f"{name} = {value}\n" for name, value in operations.items()
    )


def prepare(module, monkeypatch, tmp_path, protocol):
    exe = tmp_path / "War3ReforgedTrainer-v1.0.19-FullClone-R19.2.exe"
    exe.touch()
    (tmp_path / "war3_reforged_trainer.py").write_text(source_for(module, protocol), encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "EXE", exe)


def test_verifier_targets_separate_r19_name_and_operation():
    module = verifier()
    assert module.EXE.name == "War3ReforgedTrainer-v1.0.19-FullClone-R19.2.exe"
    assert module.EXPECTED_OPERATIONS["NATIVE_HELPER_OP_EXT_QUERY_SELECTED_OWNER_STATUS"] == 317
    spec = (Path(__file__).parent / "魔兽争霸3重制版修改器.spec").read_text(encoding="utf-8")
    assert "name='War3ReforgedTrainer-v1.0.19-FullClone-R19.2'" in spec


def test_verifier_rejects_protocol_75_before_opening_package(monkeypatch, tmp_path):
    module = verifier()
    prepare(module, monkeypatch, tmp_path, 75)
    def unexpected_archive(*args):
        pytest.fail("old protocol reached the package loader")
    monkeypatch.setattr(module, "CArchiveReader", unexpected_archive)
    with pytest.raises(RuntimeError, match="native protocol is not 76"):
        module.main()


def test_verifier_rejects_stale_frozen_source_with_protocol_76(monkeypatch, tmp_path):
    module = verifier()
    prepare(module, monkeypatch, tmp_path, 76)
    class StaleArchive:
        def __init__(self, path):
            pass
        def extract(self, key):
            return marshal.dumps(compile('APP_VERSION = "1.0.18"', "trainer.py", "exec"))
    monkeypatch.setattr(module, "CArchiveReader", StaleArchive)
    with pytest.raises(RuntimeError, match="packaged trainer source does not match"):
        module.main()
