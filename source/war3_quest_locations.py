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
    x:float
    y:float
    bounds:tuple[float,float,float,float]=()
    rawcode:str=''

    def describe(self,en=False):
        point=f'X={self.x:g}, Y={self.y:g}'
        name=self.name.removeprefix('gg_rct_').removeprefix('gg_unit_').removeprefix('udg_').replace('_',' ')
        if self.kind=='region':
            lo_x,lo_y,hi_x,hi_y=self.bounds
            return (f'Region “{name}”: center ({point}), X {lo_x:g}…{hi_x:g}, Y {lo_y:g}…{hi_y:g} (script bounds)'
                if en else f'区域“{name}”：中心（{point}），范围 X {lo_x:g}～{hi_x:g}、Y {lo_y:g}～{hi_y:g}（脚本定义）')
        if self.kind=='unit':
            unit_id=f' [ID: {self.rawcode}]' if self.rawcode else ''
            return (f'Unit “{name}”{unit_id}: script initial position ({point})' if en else
                f'单位“{name}”{unit_id}：脚本初始位置（{point}）')
        return f'Point “{name}” ({point}) (script definition)' if en else f'地点“{name}”（{point}，脚本定义）'


class QuestLocations:
    def __init__(self,report,cancelled=lambda:False):
        self.reader=QuestText(report);self.assignments={};self.locals={};self.regions={};self.types=dict(report.variable_types)
        self.cache={};self.cancelled=cancelled
        program=parse_jass(report.snapshot.script.decode('utf-8-sig'),cancelled)
        for g in program.globals:
            if g.exprs and g.exprs[0].kind!='null':self.assignments.setdefault(g.name,[]).append((g.exprs[0],'',g.line,False))
        for fn in program.functions.values():
            self.locals[fn.name]={p for _t,p in fn.params}
            self._walk(fn.body,fn.name)

    def _walk(self,body,fn,conditional=False):
        for s in body:
            if self.cancelled():raise RuntimeError('位置解析已取消')
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
            self._walk(s.body,fn,conditional or s.kind in ('if','loop'))
            self._walk(s.otherwise,fn,True)

    def _value(self,name,fn='',line=10**9,seen=frozenset()):
        key=(fn,name) if name in self.locals.get(fn,()) else name
        if key in seen or len(seen)>=32:return None
        values=self.assignments.get(key,())
        if isinstance(key,tuple):
            values=[v for v in values if v[2]<line]
            if not values or any(v[3] for v in values):return None
            values=values[-1:] # Straight-line generated local u = CreateUnit; gg_unit = u.
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
        if name in ('Rect','Location') and len(a)==(4 if name=='Rect' else 2):
            values=tuple(self._resolve(x,fn,line,seen) for x in a)
            if not self._coordinates(values):return None
            if name=='Rect' and (values[0]>values[2] or values[1]>values[3]):return None
            return ('rect' if name=='Rect' else 'point',values,'')
        if name in ('CreateUnit','CreateUnitAtLoc') and len(a)>=4:
            if name=='CreateUnit':
                values=tuple(self._resolve(x,fn,line,seen) for x in a[2:4])
            else:
                point=self._resolve(a[2],fn,line,seen)
                values=point[1] if isinstance(point,tuple) and point[0]=='point' else ()
            if not self._coordinates(values) or len(values)!=2:return None
            return ('unit',values,str(a[1].value) if a[1].kind=='rawcode' else '')
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
            elif kind in ('unit','point'):result.append(QuestLocation(kind,name,*values,rawcode=rawcode))
        # A region can be composed of multiple rectangles; preserve each one.
        if self.types.get(name)=='region':
            for e,fn,line in self.regions.get(name,()):
                rect=self._resolve(e,fn,line)
                if isinstance(rect,tuple) and rect[0]=='rect':
                    x1,y1,x2,y2=rect[1]
                    result.append(QuestLocation('region',str(e.value) if e.kind=='variable' else name,
                        (x1+x2)/2,(y1+y2)/2,rect[1]))
        return tuple(dict.fromkeys(result))

    def paths(self,paths):
        result=[]
        for p in paths:
            expressions=[p.guard]+[e[3:] for e in p.events if e.startswith('事件 ')]
            for text in expressions:
                try:pending=[self.reader.parse(text)]
                except ValueError:continue
                while pending:
                    e=pending.pop()
                    if e.kind=='variable' and self.types.get(e.value) in ('rect','region','unit','location'):
                        result.extend(self.named(str(e.value)))
                    pending.extend(reversed(e.args))
        return tuple(dict.fromkeys(result))

    def rule(self,rule):
        key=id(rule)
        if key not in self.cache:self.cache[key]=self.paths(rule.paths)
        return self.cache[key]
