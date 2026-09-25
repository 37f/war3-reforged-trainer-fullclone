"""Verify the v1.0.19 FullClone R16 frozen package without opening Warcraft III."""
from __future__ import annotations

import hashlib
import json
import marshal
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types

import pefile
from PyInstaller.archive.readers import CArchiveReader


ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "War3ReforgedTrainer-v1.0.19-FullClone-R16.exe"
EXPECTED_OPERATIONS = {
    "NATIVE_HELPER_OP_EXT_VALIDATE_PLAYER_TARGET": 300,
    "NATIVE_HELPER_OP_EXT_SET_UNIT_OWNER_PLAYER": 301,
    "NATIVE_HELPER_OP_EXT_CREATE_UNIT_PLAYER": 302,
    "NATIVE_HELPER_OP_EXT_CLONE_SELECTED_WITH_OWNER": 303,
    "NATIVE_HELPER_OP_EXT_SHARE_SELECTED_OWNER_CONTROL": 304,
    "NATIVE_HELPER_OP_EXT_REVIVE_SELECTED_OWNER_HEROES": 305,
    "NATIVE_HELPER_OP_EXT_FILL_UNIT_VITALS": 306,
    "NATIVE_HELPER_OP_EXT_SET_SELECTED_OWNER_TEAM": 307,
    "NATIVE_HELPER_OP_EXT_RESTORE_SELECTED_OWNER_TEAM": 308,
    "NATIVE_HELPER_OP_EXT_SET_UNIT_COLOR": 309,
    "NATIVE_HELPER_OP_EXT_SET_SELECTED_OWNER_COLOR": 310,
    "NATIVE_HELPER_OP_EXT_REPLACE_UNIT": 311,
    "NATIVE_HELPER_OP_EXT_CAST_INFERNAL": 312,
    "NATIVE_HELPER_OP_EXT_ADD_HERO_ATTRIBUTES": 313,
    "NATIVE_HELPER_OP_EXT_GOLD_MINE": 314,
    "NATIVE_HELPER_OP_EXT_LOCAL_VICTORY": 315,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def code_matches(left: object, right: object) -> bool:
    """Compare compiled source semantically, ignoring marshal reference-table flags."""
    if isinstance(left, types.CodeType) and isinstance(right, types.CodeType):
        scalar_fields = (
            "co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
            "co_stacksize", "co_flags", "co_code", "co_names", "co_varnames",
            "co_filename", "co_name", "co_qualname", "co_firstlineno", "co_linetable",
            "co_exceptiontable", "co_freevars", "co_cellvars",
        )
        return all(getattr(left, name) == getattr(right, name) for name in scalar_fields) and (
            len(left.co_consts) == len(right.co_consts)
            and all(code_matches(a, b) for a, b in zip(left.co_consts, right.co_consts))
        )
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == len(right) and all(
            code_matches(a, b) for a, b in zip(left, right)
        )
    return type(left) is type(right) and left == right


def main() -> int:
    require(EXE.is_file(), f"FullClone EXE not found: {EXE}")
    source_bytes = (ROOT / "war3_reforged_trainer.py").read_bytes()
    source_text = source_bytes.decode("utf-8")
    require('APP_VERSION = "1.0.19"' in source_text, "application version mismatch")
    require(re.search(r"NATIVE_HELPER_VERSION\s*=\s*73\b", source_text) is not None,
            "native protocol is not 73")
    for name, value in EXPECTED_OPERATIONS.items():
        require(re.search(rf"{name}\s*=\s*{value}\b", source_text) is not None,
                f"operation mismatch: {name}")

    archive = CArchiveReader(str(EXE))
    main_code = marshal.loads(archive.extract("war3_reforged_trainer"))
    require(
        code_matches(
            main_code,
            compile(
                source_bytes,
                main_code.co_filename,
                "exec",
                optimize=0,
                dont_inherit=True,
            ),
        ),
        "packaged trainer source does not match the working source",
    )
    pyz_key = next(key for key in archive.toc if key.endswith(".pyz"))
    pyz = archive.open_embedded_archive(pyz_key)
    for module_name in ("war3_ui_i18n", "war3_runtime_check"):
        packaged_code = pyz.extract(module_name)
        module_bytes = (ROOT / f"{module_name}.py").read_bytes()
        require(
            code_matches(
                packaged_code,
                compile(
                    module_bytes,
                    packaged_code.co_filename,
                    "exec",
                    optimize=0,
                    dont_inherit=True,
                ),
            ),
            f"packaged {module_name} source does not match",
        )

    normalized_entries = {key.replace("\\", "/").lower(): key for key in archive.toc}
    helper_name = "tools/war3_native_helper.dll"
    require(helper_name in normalized_entries, "persistent native helper is missing")
    helper_bytes = (ROOT / helper_name).read_bytes()
    require(archive.extract(normalized_entries[helper_name]) == helper_bytes,
            "packaged persistent helper does not match")
    helper_entries = sorted(
        name for name in normalized_entries
        if name.endswith("helper.dll") and name != helper_name
    )
    require(not helper_entries, f"legacy helper DLLs are present: {helper_entries}")

    pe = pefile.PE(str(EXE))
    info = pe.VS_FIXEDFILEINFO[0]
    require((info.FileVersionMS, info.FileVersionLS) == (65536, 19 << 16),
            "file version is not 1.0.19.0")
    require(pe.FILE_HEADER.Machine == 0x8664, "EXE is not x86-64")
    require(pe.OPTIONAL_HEADER.Subsystem == 2, "EXE is not a GUI application")
    pe.close()

    with tempfile.TemporaryDirectory(prefix="war3-fullclone-selftest-") as temp_dir:
        runtime_path = Path(temp_dir) / "runtime-self-test.json"
        environment = os.environ.copy()
        environment["__COMPAT_LAYER"] = "RunAsInvoker"
        subprocess.run(
            [str(EXE), "--runtime-self-test", str(runtime_path)],
            env=environment,
            check=True,
            timeout=60,
        )
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    require(runtime.get("ok") is True and runtime.get("frozen") is True,
            "offline frozen runtime self-test failed")
    require(runtime.get("helper_sha256", "").upper() == sha256(helper_bytes),
            "runtime helper hash mismatch")

    report = {
        "ok": True,
        "app_version": "1.0.19",
        "native_protocol": 73,
        "extension_operations": EXPECTED_OPERATIONS,
        "legacy_helpers": helper_entries,
        "required_helper": helper_name,
        "helper_sha256": sha256(helper_bytes),
        "exe": str(EXE),
        "exe_bytes": EXE.stat().st_size,
        "exe_sha256": sha256(EXE.read_bytes()),
        "bundled_sources_match": True,
        "offline_runtime": runtime,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PACKAGE VERIFICATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
