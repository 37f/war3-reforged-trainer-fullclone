# -*- mode: python ; coding: utf-8 -*-
# R23 separate test build, paired with native protocol79; no previous EXE overwritten.
a = Analysis(
    ['war3_reforged_trainer.py'], pathex=[],
    binaries=[('tools/war3_native_helper.dll','tools'),('tools/capstone.dll','capstone/lib'),
              ('tools/StormLib.dll','tools'),('tools/CascLib.dll','tools')],
    datas=[('assets/app_icon.png','assets'),('third_party/StormLib','third_party/StormLib'),
           ('third_party/CascLib/LICENSE','third_party/CascLib'),('third_party/CascLib/BUILD.md','third_party/CascLib')],
    hiddenimports=['capstone','war3_runtime_check','war3_current_map_catalog','war3_current_map_script',
        'war3_casc_source','war3_jass','war3_quest_analysis','war3_quest_execution',
        'war3_native_quest','war3_quest_completion_ui','war3_quest_ui'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,a.scripts,a.binaries,a.datas,[],name='War3ReforgedTrainer-v1.0.19-FullClone-R23-Test',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=True,upx_exclude=[],
    runtime_tmpdir=None,console=False,disable_windowed_traceback=False,uac_admin=True,
    argv_emulation=False,target_arch=None,codesign_identity=None,entitlements_file=None,
    icon='assets/app_icon.ico',version='tools/war3_r23_version_info.txt',
)
