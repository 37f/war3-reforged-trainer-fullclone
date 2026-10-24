"""Verify R21 matched protocol, frozen source/dependencies and offline runtime."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PyInstaller.archive.readers import CArchiveReader
from war3_campaign_catalog import STORMLIB_SHA256


def main():
    spec=importlib.util.spec_from_file_location('base_verifier',ROOT/'analysis/verify-fullclone-package.py')
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    verifier.EXE=ROOT/'dist/War3ReforgedTrainer-v1.0.19-FullClone-R21-Test.exe'
    verifier.EXPECTED_PROTOCOL=78
    verifier.EXPECTED_OPERATIONS.update(NATIVE_HELPER_OP_EXT_QUERY_CATALOG_HEADER=318,NATIVE_HELPER_OP_EXT_QUERY_CATALOG_PAGE=319)
    output=io.StringIO()
    with contextlib.redirect_stdout(output): verifier.main()
    report=json.loads(output.getvalue());archive=CArchiveReader(str(verifier.EXE));pyz=archive.open_embedded_archive('PYZ.pyz')
    modules=('war3_custom_objects','war3_campaign_catalog','war3_custom_catalog_ui','war3_current_map_catalog','war3_runtime_check')
    for name in modules:
        code=pyz.extract(name)
        verifier.require(verifier.code_matches(code,compile((ROOT/f'{name}.py').read_bytes(),code.co_filename,'exec',dont_inherit=True)),f'Packaged source mismatch: {name}')
    entries={name.replace('\\','/').lower():name for name in archive.toc}
    for name in ('tools/StormLib.dll','third_party/StormLib/LICENSE.txt','third_party/StormLib/PROVENANCE.md'):
        verifier.require(name.lower() in entries,f'Missing dependency/notice: {name}')
        verifier.require(archive.extract(entries[name.lower()])==(ROOT/name).read_bytes(),f'Packaged bytes mismatch: {name}')
    verifier.require(report['offline_runtime'].get('stormlib_sha256')==STORMLIB_SHA256,'Frozen archive dependency check missing')
    verifier.require(report['offline_runtime'].get('current_map_parser_ok') is True,'Frozen current-map parser check missing')
    report.update(edition='R21-Test',catalog_modules=modules,current_map_sources_match=True,stormlib_sha256=STORMLIB_SHA256)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
