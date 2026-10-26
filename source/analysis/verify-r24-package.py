"""R24 frozen source/dependency/protocol checks; never discover or hook a game."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PyInstaller.archive.readers import CArchiveReader
from war3_casc_source import CASC_DLL_SHA256

def main():
    spec=importlib.util.spec_from_file_location('base_verifier',ROOT/'analysis/verify-fullclone-package.py')
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    verifier.EXE=ROOT/'dist/War3ReforgedTrainer-v1.0.19-FullClone-R24-Test.exe'
    verifier.EXPECTED_PROTOCOL=80
    verifier.EXPECTED_OPERATIONS.update(NATIVE_HELPER_OP_EXT_QUERY_CATALOG_HEADER=318,
        NATIVE_HELPER_OP_EXT_QUERY_CATALOG_PAGE=319,
        NATIVE_HELPER_OP_EXT_QUERY_SOURCE_POLICY=323)
    output=io.StringIO()
    with contextlib.redirect_stdout(output):verifier.main()
    report=json.loads(output.getvalue());archive=CArchiveReader(str(verifier.EXE))
    pyz=archive.open_embedded_archive('PYZ.pyz')
    modules=('war3_custom_objects','war3_campaign_catalog','war3_custom_catalog_ui','war3_current_map_catalog',
        'war3_current_map_script','war3_casc_source','war3_jass','war3_quest_analysis',
        'war3_quest_text','war3_quest_ui','war3_runtime_check')
    for name in modules:
        code=pyz.extract(name)
        verifier.require(verifier.code_matches(code,compile((ROOT/f'{name}.py').read_bytes(),code.co_filename,
            'exec',dont_inherit=True)),f'Packaged source mismatch: {name}')
    for removed in ('war3_quest_execution','war3_native_quest','war3_quest_completion_ui'):
        verifier.require(removed not in pyz.toc, f'Removed execution module still bundled: {removed}')
    entries={name.replace('\\','/').lower():name for name in archive.toc}
    for name in ('tools/StormLib.dll','third_party/StormLib/LICENSE.txt','third_party/StormLib/PROVENANCE.md',
        'tools/CascLib.dll','third_party/CascLib/LICENSE','third_party/CascLib/BUILD.md'):
        verifier.require(name.lower() in entries,f'Missing dependency/notice: {name}')
        verifier.require(archive.extract(entries[name.lower()])==(ROOT/name).read_bytes(),f'Packaged bytes mismatch: {name}')
    runtime=report['offline_runtime']
    for name in ('current_map_parser_ok','quest_source_model_ok','quest_analysis_ok','quest_controller_ok',
        'quest_readable_text_ok'):
        verifier.require(runtime.get(name) is True,f'Frozen check missing: {name}')
    verifier.require(runtime.get('helper_protocol')==80,'Paired protocol mismatch')
    verifier.require(runtime.get('casclib_sha256')==CASC_DLL_SHA256,'Frozen local CASC dependency mismatch')
    report.update(edition='R24-Test',quest_modules=modules,quest_sources_match=True,
        casclib_sha256=CASC_DLL_SHA256,quest_readonly=True,quest_execution_available=False)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
