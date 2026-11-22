"""Current-map entry for the author's existing static object catalogue."""
from pathlib import Path,PureWindowsPath
import tempfile


def start(api):
    from war3_fullclone_source import current_script,check_source
    from war3_services.map_catalog import scan_map_catalog,KINDS
    trainer=api.app.elephant_trainer();snapshot,proof=current_script(trainer);source=proof['source']
    previous=getattr(api,'_fullclone_catalog_temp',None)
    if previous:
        if api._map_catalog_jobs.snapshot().get('status') in ('running','cancelling'):raise ValueError('正在读取目录，请先等待完成')
        previous.cleanup();api._fullclone_catalog_temp=None
    if source['kind']=='file':path=source['path']
    else:
        from war3_fullclone_casc import read_build_identity,CascArchive
        root=Path(source['root'])
        with CascArchive(root,read_build_identity(root)) as archive:raw=archive.read(source['member'])
        if not raw:raise ValueError('当前地图本地档案无法读取')
        folder=tempfile.TemporaryDirectory(prefix='war3-r31-id-');api._fullclone_catalog_temp=folder
        path=Path(folder.name)/PureWindowsPath(proof['metadata']['map_path']).name;path.write_bytes(raw)
    def scan(bound_path,**kwargs):
        if not check_source(trainer,proof):raise ValueError('目录读取前地图已变化')
        result=scan_map_catalog(bound_path,**kwargs)
        if not check_source(trainer,proof):raise ValueError('目录读取期间地图已变化，请重新检索')
        if Path(bound_path).suffix.casefold()=='.w3n':
            allowed={'战役共用',proof['metadata']['map_path'].replace('/','\\').casefold()}
            result['rows']=[r for r in result['rows'] if r['scope'].replace('/','\\').casefold() in allowed]
            result['scopes']=[s for s in result['scopes'] if s.replace('/','\\').casefold() in allowed]
            result['counts']={k:sum(r['kind']==k for r in result['rows']) for k in KINDS}
        result['source']=snapshot.origin
        result['notice']+=' 当前地图已自动定位；只列当前章节及战役共用数据。'
        return result
    result=api._map_catalog_jobs.start(path,scanner=scan)
    api._fullclone_catalog_proof=proof
    return result


def invalidate(api):
    proof=getattr(api,'_fullclone_catalog_proof',None)
    if not proof:return
    from war3_fullclone_source import check_source
    try:valid=check_source(api.app.elephant_trainer(),proof)
    except Exception:valid=False
    if valid:return
    jobs=api._map_catalog_jobs;jobs.cancel()
    with jobs.lock:
        jobs.result=None;jobs.search_index={}
        if jobs.job:jobs.job.update(status='failed',error='当前地图或连接已改变，请重新检索',rowCount=0,counts={},scopes=[])
    api._fullclone_catalog_proof=None
