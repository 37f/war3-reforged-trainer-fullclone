"""R31 task analysis adapter. No task setters or trigger execution exist here."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import tempfile
import threading
import time

from war3_mpq import Archive
from war3_map_objects import decode_text
from war3_quest_analysis import analyze_quests
from war3_quest_text import QuestText,quest_kind,clean_text
from war3_quest_locations import QuestLocations


@dataclass(frozen=True)
class ScriptSnapshot:
    identity:object=None
    session_token:int=0
    origin:str=''
    language:str='jass'
    script:bytes=b''
    strings_data:bytes=b''
    script_sha256:str=''
    strings_sha256:str=''
    validated_at:float=0.
    provenance:tuple=()
    stamp:tuple=()


def _state(api):
    return api.port.value('state').setdefault('fullclone_quests',dict(status='idle',started=False,rows=[],locations=[],generation=0))


def _source(path,chapter):
    path=Path(path).resolve(strict=True)
    if path.suffix.casefold() not in ('.w3n','.w3x','.w3m'):raise ValueError('请选择战役或地图文件')
    before=(path.stat().st_size,path.stat().st_mtime_ns)
    with Archive(path) as a:
        if path.suffix.casefold()=='.w3n':
            from war3_object_tables import campaign_maps
            chapters=campaign_maps(a.read('war3campaign.w3f'))
            if not chapter:return None,list(chapters)
            matches=[p for p in chapters if p.casefold()==chapter.replace('/','\\').casefold()]
            if len(matches)!=1:raise ValueError('请从战役章节列表中选择地图')
            blob=a.read(matches[0]);campaign_wts=a.read('war3campaign.wts',optional=True) or b''
            with tempfile.TemporaryDirectory(prefix='war3-r31-quest-') as folder:
                target=Path(folder)/'chapter.w3x';target.write_bytes(blob)
                with Archive(target) as m:script,wts,language=_members(m)
            if campaign_wts:
                from war3_custom_objects import parse_wts
                values=parse_wts(campaign_wts);values.update(parse_wts(wts) if wts else {})
                wts='\n'.join(f'STRING {k}\n{{\n{v}\n}}' for k,v in values.items()).encode('utf8')
        else:script,wts,language=_members(a)
    if before!=(path.stat().st_size,path.stat().st_mtime_ns):raise RuntimeError('分析期间地图文件已变化，请重新检测')
    return ScriptSnapshot(script=script,strings_data=wts,language=language,origin=str(path)+(f'::{chapter}' if chapter else ''),script_sha256=hashlib.sha256(script).hexdigest()),[]


def _members(archive):
    script=archive.read('war3map.j',optional=True) or archive.read('scripts\\war3map.j',optional=True)
    language='jass'
    if not script:
        script=archive.read('war3map.lua',optional=True) or archive.read('scripts\\war3map.lua',optional=True);language='lua'
    if not script:raise ValueError('未找到地图脚本，可能地图受保护或格式暂不支持')
    if len(script)>32*1024*1024:raise ValueError('脚本超过32MB解析上限')
    script=decode_text(script).encode('utf8')
    return script,archive.read('war3map.wts',optional=True) or b'',language


def render(report):
    reader=QuestText(report);locations=QuestLocations(report);positions=[];rows=[]
    def place(items):
        result=[]
        for p in dict.fromkeys(items):
            idx=len(positions);positions.append(p)
            result.append(dict(index=idx,label=p.describe(),enabled=p.locatable))
        return result
    for q in report.quests:
        entries=place(locations.before(q));conditions=[]
        for label,rules in (('完成条件',q.completed),('失败条件',q.failed)):
            for rule in rules:
                conditions.append(dict(label=label,text='\n'.join(reader.rule(rule)),positions=place(locations.rule(rule))))
        for item in q.items:
            for rule in item.completed:
                conditions.append(dict(label='子目标：'+clean_text(item.description),text='\n'.join(reader.rule(rule)),positions=place(locations.rule(rule))))
        rows.append(dict(key=q.key,title=clean_text(q.title),kind=quest_kind(q),
            description=clean_text(q.description),text=reader.quest(q),conditions=conditions,
            entries=entries,state='状态未确认',stateReason='当前任务运行状态尚未核对'))
    outcomes=[dict(text='\n'.join(reader.rule(r)),positions=place(locations.rule(r))) for r in report.outcomes]
    return rows,positions,outcomes


def start(api,path='',chapter=''):
    s=_state(api)
    if s['status'] in ('reading','analyzing'):return dict(success=True,status=s['status'])
    s['generation']+=1;generation=s['generation'];s.update(status='reading',started=True,rows=[],locations=[],error='',chapters=[])
    def worker():
        try:
            if path:
                snapshot,chapters=_source(path,chapter)
                if snapshot is None:
                    if generation==s['generation']:s.update(status='chapter',chapters=chapters,source=path)
                    return
                proof=None
            else:
                from war3_fullclone_runtime import current_script
                snapshot,proof=current_script(api.app.elephant_trainer())
            if generation!=s['generation']:return
            s['status']='analyzing'
            report=analyze_quests(snapshot);rows,positions,outcomes=render(report)
            if generation!=s['generation']:return
            s.update(status='ready',report=report,rows=rows,locations=positions,outcomes=outcomes,
                     source=snapshot.origin,proof=proof,issues=list(report.issues),last_poll=0.)
        except Exception as exc:
            if generation==s['generation']:s.update(status='failed',error=str(exc),rows=[],locations=[])
    api.app.start_operation_thread(worker,'fullclone-quest-analysis')
    return dict(success=True,status='reading')


def status(api):
    s=_state(api)
    if s['status']=='ready' and s.get('proof'):
        from war3_fullclone_runtime import check_source,quest_states
        try:
            t=api.app.elephant_trainer()
            if not check_source(t,s['proof']):
                s.update(status='stale',rows=[],locations=[],error='地图或连接已改变，请重新检测')
            elif time.monotonic()-s.get('last_poll',0)>1:
                states=quest_states(t,s['report'],s['proof']);s['last_poll']=time.monotonic()
                for row in s['rows']:
                    state=states.get(row['key'],{})
                    row.update(state=state.get('state','状态未确认'),stateReason=state.get('reason','未能唯一绑定运行中的任务'))
        except Exception as exc:
            for row in s['rows']:row.update(state='状态未确认',stateReason=str(exc))
    return dict(success=True,**{k:s.get(k) for k in ('status','started','rows','outcomes','error','source','issues','chapters')})


def camera(api,index):
    s=_state(api)
    if s['status']!='ready' or type(index) is not int or not 0<=index<len(s['locations']):raise ValueError('无位置')
    if not s.get('proof'):raise ValueError('这是离线文件分析，尚未确认与当前地图一致，不能跳转游戏视角')
    from war3_fullclone_runtime import check_source
    t=api.app.elephant_trainer()
    if not check_source(t,s['proof']):raise ValueError('当前地图已改变，请重新检测')
    p=s['locations'][index]
    if not p.locatable:raise ValueError('无位置')
    t.fullclone_action(15,x=p.x,y=p.y,expected_epoch=s['proof']['metadata']['epoch'])
    return dict(success=True,message='本地视角已定位')
