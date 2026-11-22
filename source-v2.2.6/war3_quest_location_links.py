"""Bounded script-reference links for quest locations; never executes map code.

Sources are candidates from explicit constructors/orders/registrations. A stock
entry is not a completed purchase, and a holder is not proof of an item drop.
"""
from dataclasses import replace
import time

from war3_quest_locations import QuestLocation
from war3_quest_analysis import expression

MAX_RESULTS=256
MAX_FRAMES=512
MAX_SOURCES=128
OBJECT_TYPES={'rect':'region','region':'region','unit':'unit','item':'item',
    'destructable':'destructable','location':'point','camerasetup':'camera'}


def walk(e):
    pending=[e]
    while pending:
        n=pending.pop();yield n;pending.extend(reversed(n.args))


class QuestLocationLinks:
    def __init__(self,owner):
        self.o=owner;self.program=owner.program;self.by_fn={};self.sources={};self.camera_points={};self.truncated_sources=set()
        self.callback_events={};self.timer_callbacks={};self.timer_starts={};self.deadline=time.monotonic()+20;self.building=True
        for row in owner.calls:self.by_fn.setdefault(row[1],[]).append(row)
        self.frames=[]
        for fn in self.program.functions:
            self.check()
            if not self.program.functions[fn].params:self.frames.extend(self.function_frames(fn,for_index=True))
            if len(self.frames)>100000:raise ValueError('位置关联调用数量超过上限')
        registrations={};callbacks=[]
        for call,fn,line,branches,root in self.frames:
            name=str(call.value);a=call.args
            if name in self.program.functions:continue
            if name in ('TriggerRegisterUnitEvent','TriggerRegisterDeathEvent','TriggerRegisterEnterRectSimple','TriggerRegisterLeaveRectSimple','TriggerRegisterEnterRegion','TriggerRegisterLeaveRegion','TriggerRegisterTimerExpireEvent') and len(a)>1:
                registrations.setdefault(self.key(a[0],fn),[]).append((name,a[1:],fn))
            if name in ('TriggerAddAction','TriggerAddCondition') and len(a)>1:
                callbacks.extend((self.key(a[0],fn),n.value) for n in walk(a[1]) if n.kind=='function_ref')
            if name=='TimerStart' and len(a)>3:
                self.timer_starts.setdefault(self.key(a[0],fn),[]).append((fn,line,branches))
                if a[3].kind=='function_ref':self.timer_callbacks.setdefault(a[3].value,[]).append((fn,line,branches))
            if name=='CameraSetupSetDestPosition' and len(a)>=3:
                xy=self.xy(a[1:3],fn,line)
                if a[0].kind=='variable':self.camera_points.setdefault(a[0].value,set()).add(xy)
        for key,fn in callbacks:self.callback_events.setdefault(fn,[]).extend(registrations.get(key,()))
        for frame in self.frames:
            self.check()
            for place in self.action_sources(frame):
                if place.rawcode and place.kind in ('item','unit','destructable'):
                    key=(place.kind,place.rawcode);rows=self.sources.setdefault(key,[])
                    if place not in rows:
                        if len(rows)<MAX_SOURCES:rows.append(place)
                        else:self.truncated_sources.add(key)
        self.building=False

    def check(self):
        if self.o.cancelled():raise RuntimeError('位置解析已取消')
        if self.building and time.monotonic()>self.deadline:raise ValueError('位置关联分析超过时间上限')

    @staticmethod
    def key(e,fn):
        return ('variable',e.value) if e.kind=='variable' else (fn,e.line,expression(e))

    def function_frames(self,fn,env=None,root=None,stack=(),for_index=False,scopes=None):
        if fn in stack or len(stack)>=12:return []
        result=[];root=root or fn
        for call,context,line,branches in self.by_fn.get(fn,()):
            if scopes and fn in scopes and not any(self.compatible(branches,b) for b in scopes[fn]):continue
            self.check();call=self.o.freeze(call,context,line,env)
            result.append((call,context,line,branches,root))
            target=self.program.functions.get(call.value)
            if target and (not for_index or target.params) and len(call.args)==len(target.params):
                binding={name:arg for (_type,name),arg in zip(target.params,call.args)}
                result.extend(self.function_frames(target.name,binding,root,stack+(fn,),for_index,scopes))
            if len(result)>=MAX_FRAMES:return result[:MAX_FRAMES]
        return result

    def xy(self,values,fn='',line=10**9):
        xy=tuple(self.o._resolve(v,fn,line) for v in values)
        return xy if len(xy)==2 and self.o._coordinates(xy) else None

    def rawcode(self,e,fn='',line=10**9):
        if e.kind=='rawcode':return str(e.value)
        if e.kind=='variable':
            rows=self.o.assignments.get(e.value,())
            codes={str(v.value) for v,_fn,_line,_conditional in rows if v.kind=='rawcode'}
            if len(codes)==1 and len(codes)==len({expression(v) for v,*_ in rows}):return next(iter(codes))
        value=self.o._resolve(e,fn,line)
        return value[2] if isinstance(value,tuple) and value[0] in ('item','unit','destructable') else ''

    def camera(self,name):
        points=self.camera_points.get(name,set())
        xy=next(iter(points)) if len(points)==1 and None not in points else None
        return (QuestLocation('camera',name,*(xy or (None,None)),source='camera'),)

    def event_units(self,fn,getter='GetTriggerUnit'):
        result=[]
        for name,args,context in self.callback_events.get(fn,()):
            if name=='TriggerRegisterDeathEvent':event='EVENT_UNIT_DEATH'
            elif name=='TriggerRegisterUnitEvent' and len(args)>1:event=str(args[1].value)
            else:continue
            if getter=='GetDyingUnit' and event!='EVENT_UNIT_DEATH':continue
            if getter=='GetSellingUnit' and event not in ('EVENT_UNIT_SELL_ITEM','EVENT_UNIT_SELL'):continue
            result.extend(self.where(args[0],context,source='initial'))
        return tuple(dict.fromkeys(result))

    def where(self,e,fn='',line=10**9,source='',event_fn=None):
        if e.kind=='call' and e.value in ('GetDyingUnit','GetTriggerUnit','GetSellingUnit','GetTriggerWidget'):
            return self.event_units(event_fn or fn,str(e.value))
        if e.kind=='variable':
            places=self.o.named(str(e.value))
            if places:return tuple(replace(p,source=source or p.source) for p in places)
        value=self.o._resolve(e,fn,line)
        if isinstance(value,tuple):
            kind,xy,code=value
            if kind=='rect':
                x1,y1,x2,y2=xy;return (QuestLocation('region',str(e.value),(x1+x2)/2,(y1+y2)/2,xy,source=source),)
            if kind in ('unit','item','destructable','point'):
                return (QuestLocation(kind,code or str(e.value),*xy,rawcode=code,source=source or ('initial' if kind!='point' else '')),)
        kind=OBJECT_TYPES.get(self.o.types.get(e.value,'')) if e.kind=='variable' else None
        return (QuestLocation(kind,str(e.value),None,None,source=source),) if kind else ()

    def item_at(self,code,places,source,via=''):
        if not places:return (QuestLocation('item',code or '物品对象',None,None,rawcode=code,source=source,via=via),)
        return tuple(QuestLocation('item',code or '物品对象',p.x,p.y,bounds=p.bounds,rawcode=code,source=source,
            via=via or p.name) for p in places)

    def action_sources(self,frame):
        call,fn,line,_branches,root=frame;name=str(call.value);a=call.args;result=[]
        # Map-defined wrappers are followed through their real body. A familiar
        # BJ/native name alone is not evidence of the corresponding effect.
        if name in self.program.functions:return ()
        if name in ('CreateUnit','BlzCreateUnitWithSkin','CreateUnitAtLoc','CreateUnitAtLocSaveLast','CreateItem','CreateItemLoc','CreateDestructable','CreateDestructableZ','CreateDeadDestructable','CreateDeadDestructableZ','BlzCreateDestructableWithSkin','BlzCreateDestructableZWithSkin','BlzCreateDeadDestructableWithSkin'):
            result.extend(self.where(call,fn,line,source='spawn' if name.startswith('CreateItem') else 'initial'))
            if name in ('CreateItem','CreateItemLoc') and len(a)>=2 and not result:
                code=self.rawcode(a[0],fn,line)
                getter=next((n for arg in a[1:3] for n in walk(arg) if n.kind=='call' and n.value in ('GetUnitX','GetUnitY','GetWidgetX','GetWidgetY','GetDestructableX','GetDestructableY','GetUnitLoc') and n.args),None)
                if getter:
                    origins=self.where(getter.args[0],fn,line,event_fn=root)
                    result.extend(self.item_at(code,origins,'drop' if any(n.kind=='call' and n.value in ('GetDyingUnit','GetTriggerWidget') for n in walk(getter.args[0])) else 'near-object'))
            if name in ('CreateItem','CreateItemLoc') and not result and a:
                code=self.rawcode(a[0],fn,line);regions=[]
                for argument in a[1:]:
                    for node in walk(argument):
                        if node.kind=='variable' and self.o.types.get(node.value) in ('rect','region'):
                            regions.extend(self.where(node,fn,line))
                result.extend(self.item_at(code,regions,'spawn-region' if regions else 'spawn'))
        if name=='AddItemToStock' and len(a)>=2:
            result.extend(self.item_at(self.rawcode(a[1],fn,line),self.where(a[0],fn,line,event_fn=root),'vendor'))
        if name in ('UnitAddItemById','UnitAddItemByIdSwapped') and len(a)>=2:
            unit,item=(a[0],a[1]) if name=='UnitAddItemById' else (a[1],a[0])
            result.extend(self.item_at(self.rawcode(item,fn,line),self.where(unit,fn,line,event_fn=root),'holder'))
        if name=='UnitDropItem' and len(a)>=2 and name not in self.program.functions:
            result.extend(self.item_at(self.rawcode(a[1],fn,line),self.where(a[0],fn,line,event_fn=root),'drop'))
        if name in ('UnitDropItemPoint','UnitDropItemPointLoc') and len(a)>=3:
            destination=self.where(a[2],fn,line) if name.endswith('Loc') else ()
            xy=self.xy(a[2:4],fn,line) if name=='UnitDropItemPoint' else None
            if xy:destination=(QuestLocation('point','掉落点',*xy),)
            result.extend(self.item_at(self.rawcode(a[1],fn,line),destination,'drop-fixed'))
        if name in ('UnitDropItemTarget','UnitUseItemTarget') and len(a)>=3:
            result.extend(self.item_at(self.rawcode(a[1],fn,line),self.where(a[2],fn,line,event_fn=root),'delivery'))
        if name in ('UnitUseItem','UnitUseItemPoint') and len(a)>=2:
            xy=self.xy(a[2:4],fn,line) if name.endswith('Point') else None
            places=(QuestLocation('point','使用目标点',*xy),) if xy else self.where(a[0],fn,line,event_fn=root)
            result.extend(self.item_at(self.rawcode(a[1],fn,line),places,'delivery'))
        camera_offset=1 if name.endswith('ForPlayer') else 0
        if name in ('PanCameraTo','PanCameraToTimed','SetCameraPosition','PanCameraToTimedForPlayer','SetCameraPositionForPlayer'):
            xy=self.xy(a[camera_offset:camera_offset+2],fn,line)
            result.append(QuestLocation('point','固定观察点',*(xy or (None,None)),source='observation'))
        if name in ('SetUnitPosition','SetUnitPositionLoc','SetUnitPositionLocFacingBJ') and len(a)>=2:
            xy=self.xy(a[1:3],fn,line) if name=='SetUnitPosition' else None
            places=self.where(a[1],fn,line) if name!='SetUnitPosition' else ()
            if xy:places=(QuestLocation('point','传送落点',*xy),)
            result.extend(replace(p,kind='point',source='teleport') for p in places)
        if name in ('IssueBuildOrder','IssueBuildOrderById') and len(a)>=4:
            xy=self.xy(a[2:4],fn,line);code=self.rawcode(a[1],fn,line)
            result.append(QuestLocation('unit',code or str(a[1].value),*(xy or (None,None)),rawcode=code,source='build'))
        if name in ('IssuePointOrder','IssuePointOrderById','IssuePointOrderLoc') and len(a)>=3:
            xy=self.xy(a[2:4],fn,line) if name!='IssuePointOrderLoc' else None
            positions=(QuestLocation('point','指令目标点',*xy),) if xy else self.where(a[2],fn,line) if name=='IssuePointOrderLoc' else ()
            result.extend(replace(p,source='order',via='命令 '+str(a[1].value)) for p in positions)
        if name in ('KillUnit','RescueUnit','RescueUnitBJ','SetUnitOwner','KillDestructable','RemoveDestructable') and a:
            result.extend(self.where(a[0],fn,line,source='initial',event_fn=root))
        # ItemTable drop callbacks can choose among explicitly listed rawcodes.
        if name=='RandomDistAddItem' and a:
            drops=any(c.value=='UnitDropItem' for c,*_ in self.by_fn.get(fn,()))
            if drops:result.extend(self.item_at(self.rawcode(a[0],fn,line),self.event_units(root,'GetDyingUnit'),'drop','随机掉落候选，非保证掉落'))
        return tuple(result)

    def type_refs(self,e):
        refs=[]
        for node in walk(e):
            pairs=[]
            if node.kind=='binary' and node.value=='==':pairs=[node.args,node.args[::-1]]
            for left,right in pairs:
                if left.kind=='call' and left.value in ('GetItemTypeId','GetUnitTypeId','GetDestructableTypeId') and right.kind=='rawcode':
                    kind={'GetItemTypeId':'item','GetUnitTypeId':'unit','GetDestructableTypeId':'destructable'}[left.value]
                    if not left.args or not self.o._resolve(left.args[0]):refs.append((kind,str(right.value)))
            if node.kind=='call' and node.value in ('UnitHasItemOfTypeBJ','GetItemOfTypeFromUnitBJ') and len(node.args)>1:
                code=self.rawcode(node.args[1])
                if code:refs.append(('item',code))
        return tuple(dict.fromkeys(refs))

    def references(self,e,fn='',line=10**9):
        result=[]
        for node in walk(e):
            if node.kind=='variable' and self.o.types.get(node.value) in OBJECT_TYPES:
                result.extend(self.where(node,fn,line))
            if node.kind=='call' and node.value in ('Rect','Location'):
                result.extend(self.where(node,fn,line))
            if node.kind=='call' and node.value=='TriggerRegisterUnitInRange' and len(node.args)>2:
                radius=self.o._resolve(node.args[2],fn,line)
                note=f'触发范围半径 {radius:g}' if isinstance(radius,(int,float)) else '触发范围半径未确认'
                result.extend(replace(p,via=note) for p in self.where(node.args[1],fn,line))
        for kind,code in self.type_refs(e):
            places=self.sources.get((kind,code),())
            result.extend(replace(p,source='candidate' if p.source in ('initial','spawn') and kind!='item' else p.source,
                via='按 ID 匹配的脚本来源候选'+('；'+p.via if p.via else '')) for p in places)
            if not places:result.append(QuestLocation(kind,code,None,None,rawcode=code))
            if (kind,code) in self.truncated_sources:
                result.append(QuestLocation(kind,code,None,None,rawcode=code,via=f'同类脚本来源超过 {MAX_SOURCES} 项，余项未展开'))
        return tuple(result)

    @staticmethod
    def compatible(branches,anchor):
        fixed=dict(anchor)
        return all(line not in fixed or fixed[line]==side for line,side in branches)

    def paths(self,paths):
        result=[]
        for p in paths:
            self.check_path();anchors={};timed=[];roots=set()
            for text in [p.guard]+[e[3:] for e in p.events if e.startswith('事件 ')]:
                try:e=self.o.reader.parse(text)
                except ValueError:continue
                result.extend(self.references(e))
                if e.kind=='call' and e.value=='TriggerRegisterTimerExpireEvent' and len(e.args)>1:
                    timed.extend(self.timer_starts.get(self.key(e.args[1],''),()))
            for proof in p.evidence:
                if proof.role in ('调用','条件表达式'):
                    anchors.setdefault(proof.function,[]).append(self.o.blocks.get((proof.function,proof.line),()))
                if proof.role in ('动作注册','条件注册','历史动作注册'):
                    try:registration=self.o.reader.parse(proof.source.removeprefix('call '))
                    except ValueError:continue
                    roots.update(n.value for n in walk(registration) if n.kind=='function_ref')
                if proof.role=='调用':
                    try:site=self.o.reader.parse(proof.source.removeprefix('call '))
                    except ValueError:continue
                    if site.kind=='call' and site.value in ('QuestSetCompleted','QuestSetFailed','QuestItemSetCompleted','CustomVictoryBJ','CustomDefeatBJ','RemovePlayer'):
                        roots.add(proof.function)
            for fn in p.callers:timed.extend(self.timer_callbacks.get(fn,()))
            for fn,line,branches in timed:
                if fn not in ('main','config'):anchors.setdefault(fn,[]).append(branches);roots.add(fn)
            covered=set()
            ordered=sorted(anchors.items(),key=lambda row:bool(self.program.functions.get(row[0]) and self.program.functions[row[0]].params))
            for fn,contexts in ordered:
                if fn not in self.program.functions or fn not in roots:continue
                if self.program.functions[fn].params and fn in covered:continue
                # Never sweep the entire initialization function for a quest.
                contexts=[c for c in contexts if c] if fn in ('main','config') else contexts
                if not contexts:continue
                frames=self.function_frames(fn,scopes=anchors);covered.update(frame[1] for frame in frames)
                for frame in frames:
                    call,context,line,branches,root=frame
                    if context==fn and not any(self.compatible(branches,anchor) for anchor in contexts):continue
                    result.extend(self.references(call,context,line))
                    result.extend(self.action_sources(frame))
            # Counter provenance can retain regions/targets that were expanded
            # out of the final counter expression. Read only those proof lines.
            for proof in p.variables:
                text=proof.source
                for prefix in ('赋值前提：','展开赋值前提：'):
                    if text.startswith(prefix):
                        try:result.extend(self.references(self.o.reader.parse(text[len(prefix):])))
                        except ValueError:pass
            result=list(dict.fromkeys(result))
            if len(result)>MAX_RESULTS:
                result=result[:MAX_RESULTS-1]+[QuestLocation('point','部分关联结果未展开',None,None,via=f'单条条件超过 {MAX_RESULTS} 项关联上限')]
        return tuple(result)

    def check_path(self):
        # The construction deadline applies only in the background. Later UI
        # lookups retain bounded frame/result limits and cancellation checks.
        if self.o.cancelled():raise RuntimeError('位置解析已取消')
