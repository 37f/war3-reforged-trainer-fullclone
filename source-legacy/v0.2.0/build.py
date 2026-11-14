"""Build only derived files; the supplied Warcraft installation is read-only."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
import pefile
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parent
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);args=parser.parse_args()
    out=ROOT/'dist';native=ROOT/'legacy32';native.mkdir(exist_ok=True)
    def run(*cmd):subprocess.run([str(x) for x in cmd],cwd=ROOT,check=True)
    run(args.compiler,'-shared','-O1','-fno-omit-frame-pointer','legacy_bridge32.c','legacy_core.c','legacy_clone.c','-o',native/'legacy_bridge32_v2.dll','-Wl,--kill-at','-luser32')
    run(args.compiler,'-O1','-municode','legacy_host32.c','-o',native/'legacy_host32_v2.exe','-luser32')
    run(args.compiler,'-O1','-fno-omit-frame-pointer','guard_fixture.c','-o','guard_fixture.exe');run(ROOT/'guard_fixture.exe')
    run(args.compiler,'-O1','core_fixture.c','legacy_core.c','legacy_clone.c','-o','core_fixture.exe');run(ROOT/'core_fixture.exe')
    run(args.compiler,'-O1','clone_fixture.c','legacy_clone.c','-o','clone_fixture.exe');run(ROOT/'clone_fixture.exe')
    schema=json.loads(subprocess.check_output([str(native/'legacy_host32_v2.exe'),'--schema'],text=True));assert schema['packet_bytes']==7300
    run(sys.executable,'-m','unittest','test_legacy.py','-v')
    run(sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
        '--name','War3LegacyTrainer-v0.2.0-Test','--version-file','version-info.txt',
        '--add-data','profile.json;.','--add-data','legacy32/legacy_host32_v2.exe;legacy32','--add-data','legacy32/legacy_bridge32_v2.dll;legacy32','ui.py')
    exe=out/'War3LegacyTrainer-v0.2.0-Test.exe';archive=CArchiveReader(str(exe))
    sha=lambda b:hashlib.sha256(b).hexdigest()
    for member in ('profile.json','legacy32/legacy_host32_v2.exe','legacy32/legacy_bridge32_v2.dll'):
        assert sha(archive.extract(member.replace('/','\\')))==sha((ROOT/member).read_bytes()),member
    pyz=archive.open_embedded_archive(next(n for n in archive.toc if n.lower().endswith('.pyz')))
    code=pyz.extract('legacy_backend');assert code==compile((ROOT/'legacy_backend.py').read_bytes(),code.co_filename,'exec',dont_inherit=True)
    main_code=__import__('marshal').loads(archive.extract('ui'));assert main_code==compile((ROOT/'ui.py').read_bytes(),main_code.co_filename,'exec',dont_inherit=True)
    assert pefile.PE(str(exe),fast_load=True).FILE_HEADER.Machine==0x8664
    assert all(pefile.PE(str(native/name),fast_load=True).FILE_HEADER.Machine==0x14c for name in ('legacy_host32_v2.exe','legacy_bridge32_v2.dll'))
    report=dict(ok=True,exe=exe.name,exe_sha256=sha(exe.read_bytes()),exe_bytes=exe.stat().st_size,version='0.2.0-Test',
        game_version='1.29.2.9231',game_sha256=json.loads((ROOT/'profile.json').read_text('utf8'))['sha256'],outer_machine='x64',helper_machine='x86',
        packet_bytes=schema['packet_bytes'],embedded_originals_match=True,backend_code_matches=True,ui_code_matches=True)
    (out/'BUILD_VERIFICATION.json').write_text(json.dumps(report,indent=2),'utf8');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
