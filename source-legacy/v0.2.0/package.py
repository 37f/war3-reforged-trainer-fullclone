"""Package the committed source and verified EXE; preserve existing releases."""
from pathlib import Path
import hashlib,json,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parent
GAME=Path(r'E:\Games\Warcraft III (Legacy)')
NAME='War3LegacyTrainer-v0.2.0-Test'
def sha(data):return hashlib.sha256(data).hexdigest()
def copy_new(source,target):
    if target.exists():
        if sha(target.read_bytes())!=sha(source.read_bytes()):raise RuntimeError(f'Refusing to overwrite different existing file: {target}')
        return
    shutil.copyfile(source,target)
def main():
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():raise RuntimeError('Commit source first; package must match a clean tree.')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf8').strip('\0').split('\0')
    files={n:(ROOT/n).read_bytes() for n in names}
    manifest=dict(source_commit=commit,files={n:dict(bytes=len(data),sha256=sha(data)) for n,data in files.items()})
    archive=ROOT/'dist'/(NAME+'-source.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for n,data in files.items():z.writestr(n,data)
        z.writestr('SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for n,data in files.items():assert sha(z.read(n))==sha(data),n
    folder=GAME/'LegacyTrainer-v0.2.0-Test';folder.mkdir(exist_ok=True)
    exe=ROOT/'dist'/(NAME+'.exe');verification=json.loads((ROOT/'VERIFICATION.json').read_text('utf8'))
    assert sha(exe.read_bytes())==verification['frozen_build']['exe_sha256']
    copy_new(exe,GAME/exe.name);copy_new(archive,folder/archive.name)
    for name in ('使用说明.md','README.md','VERIFICATION.json'):copy_new(ROOT/name,folder/name)
    report=dict(ok=True,source_commit=commit,source_files=len(files),source_zip_sha256=sha(archive.read_bytes()),exe_sha256=sha(exe.read_bytes()),
        exe_path=str(GAME/exe.name),source_zip_path=str(folder/archive.name),archive_readback_verified=True)
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    (ROOT/'dist'/'PACKAGE_VERIFICATION.json').write_text(encoded,'utf8')
    copy_new(ROOT/'dist'/'PACKAGE_VERIFICATION.json',folder/'PACKAGE_VERIFICATION.json')
    checksum='\n'.join([sha(exe.read_bytes())+'  ..\\'+exe.name,sha(archive.read_bytes())+'  '+archive.name])+ '\n'
    checksum_path=ROOT/'dist'/'SHA256SUMS.txt';checksum_path.write_text(checksum,'utf8');copy_new(checksum_path,folder/'SHA256SUMS.txt')
    print(encoded)

if __name__=='__main__':main()
