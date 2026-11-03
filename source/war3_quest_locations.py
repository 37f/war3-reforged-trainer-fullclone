"""Task presentation only: resolve script locations without reading game memory.

Coordinates describe script definitions/initial spawns, never a moving unit's
live position. Ambiguous assignments and dynamic expressions are left unknown.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from war3_jass import parse_jass
from war3_quest_text import QuestText


@dataclass(frozen=True)
class QuestLocation:
    kind:str
    name:str
    x:float|None
    y:float|None
    bounds:tuple[float,float,float,float]=()
    rawcode:str=''
    source:str=''
    via:str=''

    @property
    def locatable(self):
        return all(isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<=1000000 for v in (self.x,self.y))

    def describe(self,en=False):
        name=self.name
        for prefix in ('gg_rct_','gg_unit_','gg_item_','gg_dest_','gg_cam_','udg_'):name=name.removeprefix(prefix)
        name=name.replace('_',' ')
        labels={'unit':('单位／建筑','Unit / building'),'item':('物品','Item'),
            'destructable':('可破坏物','Destructible'),'camera':('镜头预设','Camera preset'),
            'point':('地点','Point'),'region':('区域','Region')}
        kind=labels.get(self.kind,labels['point'])[bool(en)]
        ident=f' [ID: {self.rawcode}]' if self.rawcode else ''
        origins={'drop':('掉落来源对象的脚本初始位置，非实时；实际掉落随死亡位置','drop source initial position, not live; actual drop follows death position'),
            'drop-fixed':('脚本掉落目标点','script drop destination'),'spawn':('脚本创建／刷新点','script spawn point'),
            'spawn-region':('刷新坐标引用的区域中心，具体刷新点未确认','region referenced by spawn coordinates; exact spawn unresolved'),
            'near-object':('刷新坐标引用对象的脚本初始位置，非实时；实际刷新随对象位置','spawn source object initial position, not live; actual spawn follows the object'),
            'vendor':('商店／NPC 售卖位置：脚本初始位置，非实时','shop / NPC stock: script initial position, not live'),
            'delivery':('上交／交付位置：脚本初始位置，非实时','delivery target: script initial position, not live'),
            'holder':('脚本发放／持有者初始位置，非实时；不能据此认定掉落','script item holder initial position, not live; not proof of a drop'),
            'camera':('镜头预设点','camera preset destination'),'observation':('脚本固定观察点','script observation point'),
            'teleport':('脚本传送落点','script teleport destination'),'build':('脚本建造指令目标点','script build-order destination'),
            'order':('脚本移动／点目标指令位置（护送路径线索）','script move / point-order destination (escort route clue)'),
            'candidate':('类型匹配的脚本候选位置，非实时','type-matched script candidate, not live'),
            'pre-region':('触发区域中心（脚本定义）','entry region center (script definition)'),
            'pre-npc':('触发／接取单位或 NPC：脚本初始位置，非实时','entry / quest giver: script initial position, not live'),
            'pre-point':('触发前脚本接取点／前置落点','script entry / predecessor destination'),
            'initial':('脚本初始位置，非实时','script initial position, not live')}
        origin=origins.get(self.source,('', ''))[bool(en)]
        extra=('；'+self.via if self.via else '')
        if not self.locatable:
            return f'{kind} “{name}”{ident}: No location'+(f' ({origin})' if origin else '')+extra if en else f'{kind}“{name}”{ident}：无位置'+(f'（{origin}）' if origin else '')+extra
        point=f'X={self.x:g}, Y={self.y:g}'
        if self.source:
            if self.bounds:
                x1,y1,x2,y2=self.bounds
                extra+=f'; X {x1:g}…{x2:g}, Y {y1:g}…{y2:g}' if en else f'；范围 X {x1:g}～{x2:g}、Y {y1:g}～{y2:g}'
            return f'{kind} “{name}”{ident}: {origin} ({point})'+extra if en else f'{kind}“{name}”{ident}：{origin}（{point}）'+extra
        if self.kind=='region':
            lo_x,lo_y,hi_x,hi_y=self.bounds
            return (f'Region “{name}”: center ({point}), X {lo_x:g}…{hi_x:g}, Y {lo_y:g}…{hi_y:g} (script bounds)'
                if en else f'区域“{name}”：中心（{point}），范围 X {lo_x:g}～{hi_x:g}、Y {lo_y:g}～{hi_y:g}（脚本定义）')
        if self.kind=='unit':
            unit_id=f' [ID: {self.rawcode}]' if self.rawcode else ''
            return (f'Unit “{name}”{unit_id}: script initial position, not live ({point})' if en else
                f'单位“{name}”{unit_id}：脚本初始位置，非实时（{point}）')
        return f'Point “{name}” ({point}) (script definition)' if en else f'地点“{name}”（{point}，脚本定义）'


class QuestLocations:
    def __init__(self,report,cancelled=lambda:False):
        self.reader=QuestText(report);self.assignments={};self.locals={};self.regions={};self.types=dict(report.variable_types)
        self.cache={};self.cancelled=cancelled;self.calls=[];self.blocks={}
        program=parse_jass(report.snapshot.script.decode('utf-8-sig'),cancelled)
        self.program=program
        for g in program.globals:
            if g.exprs and g.exprs[0].kind!='null':self.assignments.setdefault(g.name,[]).append((g.exprs[0],'',g.line,False))
        for fn in program.functions.values():
            self.locals[fn.name]={p for _t,p in fn.params}
            self._walk(fn.body,fn.name)
        from war3_quest_location_links import QuestLocationLinks
        self.links=QuestLocationLinks(self)
        from war3_quest_pretrigger import QuestPretriggerLocations
        self.pretrigger=QuestPretriggerLocations(self)

    def _walk(self,body,fn,conditional=False,branches=()):
        for s in body:
            if self.cancelled():raise RuntimeError('位置解析已取消')
            self.blocks[(fn,s.line)]=branches
            pending=list(s.exprs)
            while pending:
                e=pending.pop()
                if e.kind=='call':self.calls.append((e,fn,s.line,branches))
                pending.extend(e.args)
            if s.kind=='local':
                self.locals[fn].add(s.name)
                if s.exprs and s.exprs[0].kind!='null':self.assignments.setdefault((fn,s.name),[]).append((s.exprs[0],fn,s.line,conditional))
            if s.kind=='set' and s.exprs[0].kind=='variable':
                name=s.exprs[0].value;key=(fn,name) if name in self.locals[fn] else name
                if s.exprs[1].kind!='null':self.assignments.setdefault(key,[]).append((s.exprs[1],fn,s.line,conditional))
            if s.kind=='call':
                call=s.exprs[0]
                if call.value=='RegionAddRect' and len(call.args)==2 and call.args[0].kind=='variable':
                    self.regions.setdefault(call.args[0].value,[]).append((call.args[1],fn,s.line))
            self._walk(s.body,fn,conditional or s.kind in ('if','loop'),branches+((s.line,True if s.kind=='if' else 'loop'),) if s.kind in ('if','loop') else branches)
            self._walk(s.otherwise,fn,True,branches+((s.line,False),) if s.kind=='if' else branches)

    def stable_local(self,rows,fn,line):
        if not rows:return None
        row=rows[-1]
        if row[3]:
            written=self.blocks.get((fn,row[2]),());used=self.blocks.get((fn,line),())
            if not written or used[:len(written)]!=written:return None
        return row

    def freeze(self,e,fn='',line=10**9,env=None,seen=frozenset()):
        """Substitute explicit wrapper parameters/straight-line locals only."""
        from dataclasses import replace
        env=env or {}
        if len(seen)>32:return e
        if e.kind=='variable':
            if e.value in env:return env[e.value]
            key=(fn,e.value)
            if e.value in self.locals.get(fn,()) and key not in seen:
                rows=[v for v in self.assignments.get(key,()) if v[2]<line]
                row=self.stable_local(rows,fn,line)
                if row:
                    value,context,before,_=row
                    return self.freeze(value,context,before,env,seen|{key})
        return replace(e,args=tuple(self.freeze(a,fn,line,env,seen) for a in e.args))

    def _value(self,name,fn='',line=10**9,seen=frozenset()):
        key=(fn,name) if name in self.locals.get(fn,()) else name
        if key in seen or len(seen)>=32:return None
        values=self.assignments.get(key,())
        if isinstance(key,tuple):
            values=[v for v in values if v[2]<line]
            row=self.stable_local(values,fn,line)
            if row is None:return None
            values=[row] # A later unconditional write supersedes older branches.
        resolved=[]
        for e,context,before,_conditional in values:
            value=self._resolve(e,context,before,seen|{key})
            if value is None:return None
            if value not in resolved:resolved.append(value)
        return resolved[0] if len(resolved)==1 else None

    def _resolve(self,e,fn='',line=10**9,seen=frozenset()):
        if e.kind=='variable':return self._value(str(e.value),fn,line,seen)
        if e.kind=='number':
            try:
                value=str(e.value)
                return float(int(value[1:],16) if value.startswith('$') else int(value,16) if value.lower().startswith('0x') else float(value))
            except (ValueError,OverflowError):return None
        if e.kind=='unary' and e.value in ('-','+'):
            v=self._resolve(e.args[0],fn,line,seen)
            return (-v if e.value=='-' else v) if isinstance(v,(int,float)) else None
        if e.kind=='binary' and e.value in ('+','-','*','/'):
            a,b=(self._resolve(x,fn,line,seen) for x in e.args)
            if not isinstance(a,(int,float)) or not isinstance(b,(int,float)):return None
            try:return {'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b}[e.value]()
            except (ZeroDivisionError,OverflowError):return None
        if e.kind!='call':return None
        name=str(e.value);a=e.args
        if name in self.program.functions:
            function=self.program.functions[name]
            returns=[s for s in function.body if s.kind=='return' and s.exprs]
            marker=('return',name)
            if len(returns)!=1 or len(a)!=len(function.params) or marker in seen or len(seen)>=32:return None
            env={param:self.freeze(arg,fn,line) for (_type,param),arg in zip(function.params,a)}
            value=self.freeze(returns[0].exprs[0],name,returns[0].line,env)
            return self._resolve(value,name,returns[0].line,seen|{marker})
        if name in ('Rect','Location') and len(a)==(4 if name=='Rect' else 2):
            values=tuple(self._resolve(x,fn,line,seen) for x in a)
            if not self._coordinates(values):return None
            if name=='Rect' and (values[0]>values[2] or values[1]>values[3]):return None
            return ('rect' if name=='Rect' else 'point',values,'')
        if name in ('CreateUnit','BlzCreateUnitWithSkin','CreateUnitAtLoc','CreateUnitAtLocSaveLast') and len(a)>=4:
            if name in ('CreateUnit','BlzCreateUnitWithSkin'):
                values=tuple(self._resolve(x,fn,line,seen) for x in a[2:4])
            else:
                point=self._resolve(a[2],fn,line,seen)
                values=point[1] if isinstance(point,tuple) and point[0]=='point' else ()
            if not self._coordinates(values) or len(values)!=2:return None
            return ('unit',values,str(a[1].value) if a[1].kind=='rawcode' else '')
        if name in ('CreateItem','CreateItemLoc') and len(a)>=2:
            point=self._resolve(a[1],fn,line,seen) if name.endswith('Loc') else None
            values=point[1] if isinstance(point,tuple) and point[0]=='point' else tuple(self._resolve(x,fn,line,seen) for x in a[1:3]) if name=='CreateItem' else ()
            if len(values)==2 and self._coordinates(values):return ('item',values,str(a[0].value) if a[0].kind=='rawcode' else '')
        if name in ('CreateDestructable','CreateDestructableZ','CreateDeadDestructable','CreateDeadDestructableZ','BlzCreateDestructableWithSkin','BlzCreateDestructableZWithSkin','BlzCreateDeadDestructableWithSkin') and len(a)>=3:
            values=tuple(self._resolve(x,fn,line,seen) for x in a[1:3])
            if self._coordinates(values):return ('destructable',values,str(a[0].value) if a[0].kind=='rawcode' else '')
        if name=='GetRectCenter' and len(a)==1:
            target=self._resolve(a[0],fn,line,seen)
            if not isinstance(target,tuple):return None
            if target[0]=='rect':
                x1,y1,x2,y2=target[1];return ('point',((x1+x2)/2,(y1+y2)/2),'')
        # GetUnitX/Y/Loc depend on runtime motion. Do not substitute the unit's
        # initial spawn for a point captured later by the map script.
        axes={'GetRectCenterX':0,'GetRectCenterY':1,'GetLocationX':0,'GetLocationY':1}
        if name in axes and len(a)==1:
            target=self._resolve(a[0],fn,line,seen)
            if not isinstance(target,tuple):return None
            if name.startswith('GetRect') and target[0]=='rect':return (target[1][axes[name]]+target[1][axes[name]+2])/2
            if name.startswith('GetLocation') and target[0]=='point':return target[1][axes[name]]
        return None

    @staticmethod
    def _coordinates(values):
        return bool(values) and all(isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<=1000000 for v in values)

    def named(self,name):
        value=self._value(name)
        result=[]
        if isinstance(value,tuple):
            kind,values,rawcode=value
            if kind=='rect':
                x1,y1,x2,y2=values;result.append(QuestLocation('region',name,(x1+x2)/2,(y1+y2)/2,values))
            elif kind in ('unit','point','item','destructable'):result.append(QuestLocation(kind,name,*values,rawcode=rawcode,source='initial' if kind in ('item','destructable') else ''))
        # A region can be composed of multiple rectangles; preserve each one.
        if self.types.get(name)=='region':
            for e,fn,line in self.regions.get(name,()):
                rect=self._resolve(e,fn,line)
                if isinstance(rect,tuple) and rect[0]=='rect':
                    x1,y1,x2,y2=rect[1]
                    result.append(QuestLocation('region',str(e.value) if e.kind=='variable' else name,
                        (x1+x2)/2,(y1+y2)/2,rect[1]))
        if self.types.get(name)=='camerasetup' and getattr(self,'links',None):result.extend(self.links.camera(name))
        return tuple(dict.fromkeys(result))

    def paths(self,paths):
        key=('paths',tuple(id(p) for p in paths))
        if key not in self.cache:self.cache[key]=self.links.paths(paths)
        return self.cache[key]

    def rule(self,rule):
        key=id(rule)
        if key not in self.cache:self.cache[key]=self.paths(rule.paths)
        return self.cache[key]

    def before(self,q):return self.pretrigger.for_quest(q)
