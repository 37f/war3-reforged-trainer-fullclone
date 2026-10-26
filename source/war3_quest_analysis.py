"""R22 conservative JASS quest analysis. Data only: never run map code.

Standard BJ adapters are deliberately small and disabled for map-defined names.
Their verified bodies/signatures are documented in docs/r22-jass-adapters.md.
"""
from __future__ import annotations

from dataclasses import dataclass,field
import re
import time

from war3_jass import Expr,parse_jass,JassParseError
from war3_custom_objects import parse_wts

MAX_DEPTH=64
MAX_PATHS=128
MAX_TASKS=10000
MAX_SECONDS=30
MAX_EXPRESSION_DEPTH=128


class AnalysisUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Evidence:
    function:str
    line:int
    source:str
    role:str


@dataclass(frozen=True)
class ConditionPath:
    guard:str
    events:tuple[str,...]
    callers:tuple[str,...]
    evidence:tuple[Evidence,...]
    variables:tuple[Evidence,...]=()
    issues:tuple[str,...]=()
    explanation:tuple[str,str]=()


@dataclass(frozen=True)
class Rule:
    kind:str
    target:str
    paths:tuple[ConditionPath,...]
    evidence:Evidence


@dataclass(frozen=True)
class QuestItem:
    key:str
    description:str
    completed:tuple[Rule,...]
    resets:tuple[Rule,...]


@dataclass(frozen=True)
class QuestDefinition:
    key:str
    title:str
    description:str
    required:bool|None
    discovered:bool|None
    aliases:tuple[str,...]
    items:tuple[QuestItem,...]
    created:tuple[Rule,...]
    completed:tuple[Rule,...]
    failed:tuple[Rule,...]
    resets:tuple[Rule,...]


@dataclass(frozen=True)
class QuestReport:
    snapshot:object
    quests:tuple[QuestDefinition,...]
    outcomes:tuple[Rule,...]
    unassociated:tuple[Rule,...]
    issues:tuple[str,...]
    functions:int
    variable_types:tuple[tuple[str,str],...]=()

    @property
    def partial(self):
        rules=list(self.outcomes)+list(self.unassociated)
        for q in self.quests:
            rules.extend(q.created+q.completed+q.failed+q.resets)
            for item in q.items:rules.extend(item.completed+item.resets)
        return bool(self.issues or any(p.issues for rule in rules for p in rule.paths))


_TRUE=Expr('bool',True)
_FALSE=Expr('bool',False)


def expression(e):
    """Stable original-language expression, with parentheses preserving precedence."""
    if e.kind in ('variable','function_ref','number','handle'):return str(e.value)
    if e.kind=='string':return '"'+str(e.value).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')+'"'
    if e.kind=='rawcode':return "'"+str(e.value)+"'"
    if e.kind=='bool':return 'true' if e.value else 'false'
    if e.kind=='null':return 'null'
    if e.kind=='call':return str(e.value)+'('+', '.join(expression(a) for a in e.args)+')'
    if e.kind=='index':return expression(e.args[0])+'['+expression(e.args[1])+']'
    if e.kind=='unary':return str(e.value)+(' ' if e.value=='not' else '')+expression(e.args[0])
    if e.kind=='binary':return '('+expression(e.args[0])+' '+str(e.value)+' '+expression(e.args[1])+')'
    return str(e.value)


def _same(a,b):return expression(a)==expression(b)


def _neg(a):
    if a.kind=='bool':return _TRUE if not a.value else _FALSE
    if a.kind=='unary' and a.value=='not':return a.args[0]
    if a.kind=='binary' and a.value in ('==','!=','>','<','>=','<='):
        return Expr('binary',{'==':'!=','!=':'==','>':'<=','<':'>=','>=':'<','<=':'>'}[a.value],a.args,a.line)
    return Expr('unary','not',(a,),a.line)


def _logic(op,a,b):
    if op=='and':
        if a==_FALSE or b==_FALSE:return _FALSE
        if a==_TRUE:return b
        if b==_TRUE:return a
    else:
        if a==_TRUE or b==_TRUE:return _TRUE
        if a==_FALSE:return b
        if b==_FALSE:return a
    if _same(a,b):return a
    if _same(_neg(a),b) or _same(_neg(b),a):return _FALSE if op=='and' else _TRUE
    # Join sibling branches without exponentially repeating their shared prefix.
    other='and' if op=='or' else 'or'
    if a.kind=='binary' and a.value==other and b.kind=='binary' and b.value==other:
        for i in (0,1):
            for j in (0,1):
                if _same(a.args[i],b.args[j]) and _same(_neg(a.args[1-i]),b.args[1-j]):return a.args[i]
    for whole,part in ((a,b),(b,a)):
        if part.kind=='binary' and part.value==other and any(_same(whole,x) for x in part.args):return whole
    return Expr('binary',op,(a,b),a.line)


def _sub(e,env):
    if e.kind=='variable' and e.value in env:return env[e.value]
    return Expr(e.kind,e.value,tuple(_sub(a,env) for a in e.args),e.line,e.column)


def _walk_expr(e):
    pending=[e]
    while pending:
        node=pending.pop();yield node;pending.extend(reversed(node.args))


def _unique(values):return tuple(dict.fromkeys(values))


def _description(e,en=False):
    """Explain only syntax and a few known atoms; never guess map variable meanings."""
    if e.kind=='bool':return ('No additional boolean test' if en else '没有额外布尔判断') if e.value else ('False branch' if en else '恒假分支')
    if e.kind=='binary':
        if e.value in ('and','or'):
            op=(' AND ' if e.value=='and' else ' OR ') if en else ('，并且' if e.value=='and' else '，或者')
            return '('+_description(e.args[0],en)+op+_description(e.args[1],en)+')'
        words={'==':('等于','equals'),'!=':('不等于','differs from'),'>=':('不少于','is at least'),
            '<=':('不多于','is at most'),'>':('大于','is greater than'),'<':('小于','is less than')}
        if e.value in words:return expression(e.args[0])+' '+words[e.value][int(en)]+' '+expression(e.args[1])
    if e.kind=='unary' and e.value=='not':return ('NOT ' if en else '不满足：')+_description(e.args[0],en)
    if e.kind=='call':
        if e.value=='IsUnitDeadBJ' and e.args:return expression(e.args[0])+(' is dead' if en else ' 已死亡')
        if e.value=='IsQuestItemCompleted' and e.args:return ('Quest item ' if en else '任务条目 ')+expression(e.args[0])+(' is complete' if en else ' 已完成')
        if e.value=='IsUnitEnemy' and len(e.args)>1:return expression(e.args[0])+(' is an enemy of ' if en else ' 敌对于 ')+expression(e.args[1])
        if e.value=='AllowVictoryDefeat':return ('Standard-library result permission (not read live): ' if en else '标准库允许结算（许可状态未实时读取）：')+expression(e)
    return ('Script test: ' if en else '脚本判断：')+expression(e)


@dataclass(frozen=True)
class _Point:
    function:str
    call:Expr
    guard:Expr
    issues:tuple[str,...]
    preceding:tuple[Evidence,...]


@dataclass
class _State:
    guard:Expr=_TRUE
    env:dict=field(default_factory=dict)
    lastq:Expr=Expr('variable','bj_lastCreatedQuest')
    lasti:Expr=Expr('variable','bj_lastCreatedQuestItem')
    issues:tuple[str,...]=()
    preceding:tuple[Evidence,...]=()

    def branch(self,guard):
        return _State(guard,dict(self.env),self.lastq,self.lasti,self.issues,self.preceding)


class _Analyzer:
    def __init__(self,snapshot,cancelled):
        self.snapshot=snapshot;self.cancelled=cancelled;self.deadline=time.monotonic()+MAX_SECONDS
        self.issues=[];self.points=[];self.assignments=[];self.aliases={};self.returns={}
        self.created={};self.items={};self.triggers={};self.incoming={};self.lines=[]
        self.check()
        if snapshot.language!='jass':raise AnalysisUnavailable('不支持的脚本语言：'+snapshot.language)
        try:
            self.text=snapshot.script.decode('utf-8-sig');self.lines=self.text.splitlines()
            self.program=parse_jass(self.text,cancelled)
            self.strings=parse_wts(snapshot.strings_data) if snapshot.strings_data else {}
        except (ValueError,UnicodeError) as exc:raise AnalysisUnavailable(str(exc)) from exc
        self.globals={g.name:g for g in self.program.globals}
        # Pratt parsing can produce very deep left-associated trees without nested
        # parentheses; reject those before recursive expression transforms/rendering.
        statements=list(self.program.globals)+[s for f in self.program.functions.values() for s in f.body]
        while statements:
            self.check();stmt=statements.pop();statements.extend(stmt.body+stmt.otherwise)
            pending=[(e,1) for e in stmt.exprs]
            while pending:
                node,depth=pending.pop()
                if depth>MAX_EXPRESSION_DEPTH:raise AnalysisUnavailable('表达式树超过深度上限，无法完整分析')
                pending.extend((a,depth+1) for a in node.args)

    def check(self):
        if self.cancelled():raise AnalysisUnavailable('任务条件分析已取消')
        if time.monotonic()>self.deadline:raise AnalysisUnavailable('任务条件分析超过时间上限')

    def issue(self,message):
        if message not in self.issues:self.issues.append(message)

    def evidence(self,fn,line,role):
        return Evidence(fn,line,self.lines[line-1].strip() if 0<line<=len(self.lines) else '',role)

    def external(self,name):return name not in self.program.functions

    def point(self,fn,call,state):
        self.points.append(_Point(fn,call,state.guard,state.issues,state.preceding))

    def handle(self,kind,fn,e):
        return Expr('handle',f'{kind}:{fn}:{e.line}:{e.column}',(),e.line,e.column)

    def rewrite(self,e,state,fn):
        if e.kind=='bool':return _TRUE if e.value else _FALSE
        if e.kind=='variable' and e.value in state.env:return state.env[e.value]
        if e.kind=='binary' and e.value in ('and','or'):
            # JASS short-circuits: RHS calls do not share the LHS evaluation guard.
            left=self.rewrite(e.args[0],state,fn)
            right_state=state.branch(_logic('and',state.guard,left if e.value=='and' else _neg(left)))
            args=(left,self.rewrite(e.args[1],right_state,fn))
        else:args=tuple(self.rewrite(a,state,fn) for a in e.args)
        e=Expr(e.kind,e.value,args,e.line,e.column)
        if e.kind!='call':return e
        self.point(fn,e,state)
        if not self.external(e.value):
            # Map calls can change BJ globals. Do not retain a stale local
            # last-created assumption across a function with unknown effects.
            state.lastq=Expr('variable','bj_lastCreatedQuest',(),e.line)
            state.lasti=Expr('variable','bj_lastCreatedQuestItem',(),e.line)
            return e
        if e.value in ('CreateQuest','CreateQuestBJ'):
            handle=self.handle('Q',fn,e)
            if handle.value not in self.created and len(self.created)>=MAX_TASKS:
                self.issue('任务定义数量超过上限，后续任务未展开');return Expr('variable','超限任务',(),e.line)
            self.created.setdefault(handle.value,(fn,e))
            # Native constructors return a handle; only BJ wrappers update BJ globals.
            if e.value=='CreateQuestBJ':
                state.lastq=handle
                self.aliases.setdefault('bj_lastCreatedQuest',[]).append(handle)
            return handle
        if e.value in ('QuestCreateItem','CreateQuestItemBJ'):
            handle=self.handle('I',fn,e);self.items.setdefault(handle.value,(fn,e))
            if e.value=='CreateQuestItemBJ':
                state.lasti=handle;self.aliases.setdefault('bj_lastCreatedQuestItem',[]).append(handle)
            return handle
        if e.value=='CreateTrigger':return self.handle('T',fn,e)
        if e.value=='GetLastCreatedQuestBJ':return state.lastq
        if e.value=='GetLastCreatedQuestItemBJ':return state.lasti
        return e

    def scan(self):
        for g in self.program.globals:
            if g.exprs:self.assignments.append((g.name,g.exprs[0],_TRUE,self.evidence('globals',g.line,'变量初始定义')))
        for fn in self.program.functions.values():
            self.check();local_names={name for _,name in fn.params}
            def block(stmts,states,loop=False):
                for stmt in stmts:
                    self.check();out=[]
                    for state in states:
                        if state.guard==_FALSE:continue
                        if stmt.kind in ('local','global'):
                            local_names.add(stmt.name)
                            if stmt.exprs:state.env[stmt.name]=self.rewrite(stmt.exprs[0],state,fn.name)
                        elif stmt.kind=='set':
                            lhs,rhs=stmt.exprs;rhs=self.rewrite(rhs,state,fn.name)
                            lhs=_sub(lhs,state.env) if lhs.kind=='index' else lhs
                            if lhs.kind=='variable' and lhs.value in local_names:state.env[lhs.value]=rhs
                            else:
                                name=expression(lhs);self.aliases.setdefault(name,[]).append(rhs)
                                self.assignments.append((name,rhs,state.guard,self.evidence(fn.name,stmt.line,'变量赋值（静态定义）')))
                                if lhs.kind=='variable' and self.globals.get(lhs.value) and self.globals[lhs.value].type_name=='trigger':
                                    state.env[lhs.value]=rhs
                        elif stmt.kind=='call':
                            self.rewrite(stmt.exprs[0],state,fn.name)
                            if stmt.exprs[0].value in ('TriggerSleepAction','PolledWait'):
                                state.preceding+= (self.evidence(fn.name,stmt.line,'执行前等待'),)
                        elif stmt.kind=='if':
                            guard=self.rewrite(stmt.exprs[0],state,fn.name)
                            out.extend(block(stmt.body,[state.branch(_logic('and',state.guard,guard))],loop))
                            out.extend(block(stmt.otherwise,[state.branch(_logic('and',state.guard,_neg(guard)))],loop));continue
                        elif stmt.kind=='return':
                            value=self.rewrite(stmt.exprs[0],state,fn.name) if stmt.exprs else Expr('null',None)
                            self.returns.setdefault(fn.name,[]).append((state.guard,value));continue
                        elif stmt.kind=='loop':
                            inner=state.branch(state.guard);inner.issues+=('循环次数与退出条件未展开，保留循环体中的调用线索',)
                            self.issue('存在循环，循环内任务条件的迭代与顺序需人工核对')
                            block(stmt.body,[inner],True)
                        elif stmt.kind=='exitwhen':
                            guard=self.rewrite(stmt.exprs[0],state,fn.name)
                            state=state.branch(_logic('and',state.guard,_neg(guard)))
                        elif stmt.kind=='debug':
                            inner=state.branch(state.guard);inner.issues+=('debug 语句是否启用未确认',)
                            block(stmt.body,[inner],loop)
                        out.append(state)
                    states=self.merge(out)
                return states
            block(fn.body,[_State()])

    def merge(self,states):
        groups={}
        for s in states:
            key=(tuple(sorted((k,expression(v)) for k,v in s.env.items())),expression(s.lastq),expression(s.lasti),s.issues,s.preceding)
            if key in groups:groups[key].guard=_logic('or',groups[key].guard,s.guard)
            else:groups[key]=s
        if len(groups)>MAX_PATHS:self.issue('函数分支路径超过上限，部分路径未展开')
        return list(groups.values())[:MAX_PATHS]

    def resolve(self,e,kind,seen=()):
        self.check()
        if len(seen)>MAX_DEPTH:return set(),True
        if e.kind=='handle':return ({e.value},False) if e.value.startswith(kind+':') else (set(),True)
        if e.kind=='null':return set(),False
        if e.kind in ('variable','index'):
            name=expression(e)
            if (e.kind=='index' and e.args[1].kind!='number') or ('[' in name and not re.fullmatch(r'\w+\[\d+\]',name)):
                return set(),True
            if name in seen:return set(),True
            values=self.aliases.get(name,())
            result=set();unknown=not bool(values)
            for value in values:
                found,partial=self.resolve(value,kind,seen+(name,));result|=found;unknown|=partial
            return result,unknown
        if e.kind=='call' and e.value in self.program.functions:
            fn=self.program.functions[e.value]
            if e.value in seen:return set(),True
            env={name:value for (_,name),value in zip(fn.params,e.args)}
            result=set();unknown=not bool(self.returns.get(e.value))
            for guard,value in self.returns.get(e.value,()):
                found,partial=self.resolve(_sub(value,env),kind,seen+(e.value,));result|=found;unknown|=partial
            return result,unknown
        return set(),True

    def one(self,e,kind):
        values,unknown=self.resolve(e,kind)
        return next(iter(values)) if len(values)==1 and not unknown else None

    def trigger(self,e):
        # Text equality is not trigger identity when a variable has multiple handles.
        key=self.one(e,'T')
        if key is None:return None
        origin=key.split(':',2)[1];pending=[origin];seen=set()
        while pending:
            fn=pending.pop()
            if fn in ('main','config'):continue
            if fn in seen or len(seen)>=MAX_DEPTH:return None
            seen.add(fn);links=self.incoming.get(fn,())
            sites={(p.function,p.call.line,p.call.column) for p,_,_ in links}
            if len(sites)!=1 or any(action for _,_,action in links):return None
            pending.extend(p.function for p,_,_ in links)
        return key

    def build_graph(self):
        # Resolve registration callers against a complete direct-call index.
        for p in self.points:
            if p.call.value in self.program.functions:
                self.incoming.setdefault(p.call.value,[]).append((p,None,False))
        for p in self.points:
            c=p.call;n=c.value;a=c.args
            if n in self.program.functions:continue
            if n=='ExecuteFunc':
                if a and a[0].kind=='string' and a[0].value in self.program.functions:
                    self.incoming.setdefault(a[0].value,[]).append((p,None,False))
                else:self.issue('ExecuteFunc 动态函数名或函数体无法确认：'+expression(c))
            if n=='TimerStart' and len(a)>=4:
                callback=a[3]
                if callback.kind=='function_ref':
                    key=f'timer-callback:{p.function}:{c.line}:{c.column}'
                    self.triggers[key]={'events':[p],'conditions':[],'actions':[],'gates':[],'execute':[]}
                    self.incoming.setdefault(callback.value,[]).append((p,key,True))
                elif callback.kind!='null':self.issue('计时回调函数无法确定：'+expression(callback))
            relevant=n.startswith('TriggerRegister') or n in ('TriggerAddCondition','TriggerAddAction',
                'DisableTrigger','EnableTrigger','TriggerExecute','ConditionalTriggerExecute','TriggerExecuteBJ')
            if not a or not relevant:continue
            key=self.trigger(a[0])
            if key is None:
                self.issue('触发器身份无法唯一确认，不合并不同注册点：'+expression(c))
                key=f'unknown-trigger:{p.function}:{c.line}:{c.column}:{n}'
            t=self.triggers.setdefault(key,{'events':[],'conditions':[],'actions':[],'gates':[],'execute':[]})
            if n.startswith('TriggerRegister'):t['events'].append(p)
            elif n=='TriggerAddCondition' and len(a)>1:
                cond=a[1]
                if cond.kind=='call' and cond.value in ('Condition','Filter') and cond.args:cond=cond.args[0]
                t['conditions'].append((p,cond))
            elif n=='TriggerAddAction' and len(a)>1:
                t['actions'].append((p,a[1]))
            elif n in ('DisableTrigger','EnableTrigger'):t['gates'].append(p)
            elif n in ('TriggerExecute','ConditionalTriggerExecute','TriggerExecuteBJ'):
                check=_TRUE if n=='ConditionalTriggerExecute' else _FALSE
                if n=='TriggerExecuteBJ':check=a[1] if len(a)>1 else Expr('variable','unknownCheckConditions')
                t['execute'].append((p,check))
        for key,t in self.triggers.items():
            for registration,action in t['actions']:
                if action.kind=='function_ref':self.incoming.setdefault(action.value,[]).append((registration,key,True))
                else:self.issue('触发器动作函数无法静态确定：'+expression(action))
        for key,(fn,call) in self.created.items():
            sites={(p.function,p.call.line,p.call.column) for p,_,_ in self.incoming.get(fn,())}
            if len(sites)>1:self.issue('任务创建包装有多个调用位置；同一脚本定义可能产生多个运行时实例：'+fn)

    def expand(self,e,seen=()):
        """Inline bounded boolean return formulas; unknown native atoms remain literal."""
        self.check()
        if e.kind=='bool':return (_TRUE if e.value else _FALSE),(),()
        if len(seen)>=MAX_DEPTH:return e,('条件调用深度超过上限',),()
        args=[];issues=[];evidence=[]
        for arg in e.args:
            expanded,missing,proof=self.expand(arg,seen);args.append(expanded);issues.extend(missing);evidence.extend(proof)
        e=Expr(e.kind,e.value,tuple(args),e.line,e.column)
        if e.kind=='call' and e.value in self.program.functions:
            fn=self.program.functions[e.value]
            if fn.return_type!='boolean':return e,tuple(issues),tuple(evidence)
            if e.value in seen:return e,tuple(issues)+('递归条件未展开：'+str(e.value),),tuple(evidence)
            env={name:value for (_,name),value in zip(fn.params,e.args)}
            formula=_FALSE
            returns=self.returns.get(e.value,())
            if not returns:return e,tuple(issues)+('条件函数无可解析返回：'+str(e.value),),tuple(evidence)
            for guard,value in returns:
                branch=_logic('and',_sub(guard,env),_sub(value,env))
                formula=_logic('or',formula,branch)
            result,missing,proof=self.expand(formula,seen+(e.value,))
            evidence.append(self.evidence(fn.name,fn.line,'条件函数'))
            for node in _walk_expr(formula):
                if node.line>0:evidence.append(self.evidence(fn.name,node.line,'条件表达式'))
            return result,_unique(issues+list(missing)),_unique(evidence+list(proof))
        if e.kind=='call' and e.value=='TriggerEvaluate' and e.args:
            key=self.trigger(e.args[0])
            if key is None:return e,_unique(issues+['触发器身份无法唯一确认：'+expression(e.args[0])]),tuple(evidence)
            result,missing,proof,callers=self.trigger_condition(key,seen)
            return result,_unique(issues+list(missing)),_unique(evidence+list(proof))
        if e.kind=='call' and self.external(e.value) and e.value not in self.program.natives:
            # These atoms are retained, never evaluated. Unknown wrappers get a visible gap.
            if e.value not in _PREDICATES:
                issues.append('缺少条件函数体或已验证规则：'+str(e.value))
        if e.kind=='unary' and e.value=='not':e=_neg(e.args[0])
        elif e.kind=='binary' and e.value in ('and','or'):e=_logic(e.value,*e.args)
        elif e.kind=='binary' and e.value in ('==','!='):
            a,b=e.args
            if b.kind=='bool':e=a if bool(b.value)==(e.value=='==') else _neg(a)
            elif a.kind=='bool':e=b if bool(a.value)==(e.value=='==') else _neg(b)
        return e,_unique(issues),_unique(evidence)

    def trigger_condition(self,key,seen=()):
        guard=_TRUE;issues=[];proof=[];callers=[]
        t=self.triggers.get(key,{})
        for point,cond in t.get('conditions',()):
            if cond.kind!='function_ref':issues.append('触发条件函数无法确认：'+expression(cond));continue
            call=Expr('call',cond.value,(),cond.line)
            expanded,missing,evidence=self.expand(call,seen)
            registered,registration_proof,registration_issues=self.registration_state(point)
            # A condition that was not registered does not filter the trigger.
            expanded=_logic('or',_neg(registered),_logic('and',registered,expanded))
            guard=_logic('and',guard,expanded);issues.extend(missing);proof.extend(evidence)
            issues.extend(registration_issues);proof.extend(registration_proof)
            proof.append(self.evidence(point.function,point.call.line,'条件注册'));callers.append(str(cond.value))
        return guard,_unique(issues),_unique(proof),_unique(callers)

    def registration_state(self,point):
        """Historical registration provenance; no runtime-state constant folding.

        Direct initialization callers can be traced. Event-driven, recursive or
        uncalled registration remains a candidate with an explicit unknown gate.
        This helper never recursively enters trigger-condition expansion.
        """
        def roots(p,stack):
            self.check();proof=(self.evidence(p.function,p.call.line,'注册调用来源'),)
            if p.function in stack or len(stack)>=MAX_DEPTH:
                return [(p.guard,proof,('注册调用递归或深度超限，历史状态未确认',))]
            if p.function in ('main','config'):return [(p.guard,proof,p.issues)]
            links=self.incoming.get(p.function,());out=[]
            if not links:return [(p.guard,proof,('注册函数没有已确认的调用入口：'+p.function,))]
            fn=self.program.functions[p.function]
            for caller,key,is_action in links:
                if is_action:
                    out.append((p.guard,proof+(self.evidence(caller.function,caller.call.line,'历史动作注册'),),
                        ('注册由触发动作执行，历史可达性和执行次数未确认',)))
                else:
                    env={name:value for (_,name),value in zip(fn.params,caller.call.args)}
                    for guard,evidence,issues in roots(caller,stack+(p.function,)):
                        out.append((_logic('and',guard,_sub(p.guard,env)),evidence+proof,issues+p.issues))
                if len(out)>MAX_PATHS:
                    self.issue('注册调用路径超过上限，历史状态不完整')
                    return [(g,e,i+('注册调用路径超过上限',)) for g,e,i in out[:MAX_PATHS]]
            return out
        combined=_FALSE;proof=[];issues=[]
        for guard,evidence,missing in roots(point,()):
            if guard==_FALSE:continue
            proof.extend(evidence);issues.extend(missing)
            if missing:
                value=Expr('call','UnconfirmedRegistration',(Expr('string',f'{point.function}:{point.call.line}'),),point.call.line)
            elif guard!=_TRUE:
                value=Expr('call','RegistrationOccurred',(guard,),point.call.line)
                issues.append('注册受历史条件控制，不能当作当前变量值；详见注册调用来源')
            else:value=_TRUE
            combined=_logic('or',combined,value)
        return combined,_unique(proof),_unique(issues)

    def trace(self,point,guard=None,env=None,stack=()):
        """Backward call paths. Disabled triggers are evidence, never assumed unreachable."""
        self.check();env=env or {};name=point.function
        local_guard=_sub(point.guard,env)
        if guard is not None:local_guard=_logic('and',local_guard,_sub(guard,env))
        proof=point.preceding+(self.evidence(name,point.call.line,'调用'),)
        if name in stack or len(stack)>=MAX_DEPTH:
            return [(local_guard,env,(),(name,),proof,point.issues+('递归调用或调用深度超过上限：'+name,))]
        if name in ('main','config'):
            return [(local_guard,env,('脚本初始化入口 '+name,),(name,),proof,point.issues)]
        links=self.incoming.get(name,());out=[]
        if not links:
            return [(local_guard,env,(),(name,),proof,point.issues+('未确认事件或初始化调用入口；不能断言本次执行',))]
        for caller,key,is_action in links:
            self.check()
            if is_action:
                t=self.triggers[key]
                gates=tuple(self.evidence(p.function,p.call.line,'触发器启用/禁用（静态）') for p in t['gates'])
                register_proof=(self.evidence(caller.function,caller.call.line,'动作注册'),)
                cond,missing,cp,cn=self.trigger_condition(key)
                registration_guard,rp,registration_issues=self.registration_state(caller)
                register_proof+=rp
                for event in t['events']:
                    roots=self.trace(event,stack=stack+(name,))
                    for pg,pe,ev,chain,pp,pi in roots:
                        combined=_logic('and',local_guard,_logic('and',pg,_logic('and',cond,registration_guard)))
                        enabled=('事件仅在触发器启用时派发；启停调用已列出，未推算运行时启用状态',) if gates else ()
                        out.append((combined,env,('事件 '+expression(event.call),),chain+cn+(name,),pp+register_proof+cp+gates+proof,pi+missing+point.issues+registration_issues+enabled))
                for execute,check in t['execute']:
                    roots=self.trace(execute,stack=stack+(name,))
                    for pg,pe,ev,chain,pp,pi in roots:
                        execution_gate=_logic('or',_neg(check),_logic('and',check,cond))
                        needs_condition=check!=_FALSE
                        combined=_logic('and',local_guard,_logic('and',pg,_logic('and',execution_gate,registration_guard)))
                        out.append((combined,env,ev,chain+(cn if needs_condition else ())+(name,),pp+register_proof+(cp if needs_condition else ())+gates+proof,pi+(missing if needs_condition else ())+point.issues+registration_issues))
                if not t['events'] and not t['execute']:
                    out.append((_logic('and',local_guard,registration_guard),env,(),(name,),register_proof+gates+proof,
                        point.issues+registration_issues+('触发器没有已确认事件或调用入口',)))
            else:
                params=self.program.functions[name].params
                arguments=caller.call.args if caller.call.value==name else ()
                binding={param:value for (_,param),value in zip(params,arguments)}
                g=_sub(local_guard,binding)
                newenv={k:_sub(v,binding) for k,v in env.items()};newenv.update(binding)
                for pg,pe,ev,chain,pp,pi in self.trace(caller,stack=stack+(name,)):
                    newbinding={k:_sub(v,pe) for k,v in newenv.items()}
                    out.append((_logic('and',_sub(g,pe),pg),newbinding,ev,chain+(name,),pp+proof,pi+point.issues))
            if len(out)>MAX_PATHS:
                self.issue('目标调用路径超过上限，部分路径未展开');return out[:MAX_PATHS]
        return out

    def variable_proof(self,guard):
        names={str(n.value) for n in _walk_expr(guard) if n.kind=='variable'}
        result=[];seen=set()
        for _ in range(MAX_DEPTH):
            added=False
            for lhs,rhs,branch,proof in self.assignments:
                base=lhs.split('[',1)[0]
                if base in names and proof not in seen:
                    seen.add(proof);result.append(proof)
                    names.update(str(n.value) for n in _walk_expr(rhs) if n.kind=='variable')
                    # Keep the branch explaining increments, such as completed quest items.
                    if branch!=_TRUE:result.append(Evidence(proof.function,proof.line,'赋值前提：'+expression(branch),'赋值条件'))
                    expanded,missing,cp=self.expand(branch)
                    if expanded!=branch:
                        result.append(Evidence(proof.function,proof.line,'展开赋值前提：'+expression(expanded),'赋值条件'))
                        result.extend(cp)
                    for issue in missing:self.issue('计数来源：'+issue)
                    added=True
            if not added:break
        return _unique(result)

    def make_rule(self,point,kind,target,extra=_TRUE):
        paths=[];targets=[]
        for guard,env,events,chain,proof,issues in self.trace(point,extra):
            guard,missing,cp=self.expand(guard)
            if guard==_FALSE:continue
            variables=self.variable_proof(guard)
            assigned={lhs.split('[',1)[0] for lhs,_,_,_ in self.assignments}
            unknown={str(n.value) for n in _walk_expr(guard) if n.kind=='variable' and not str(n.value).isupper() and n.value not in assigned}
            missing+=tuple('变量无可解析静态赋值，运行时值未读取：'+name for name in sorted(unknown))
            paths.append(ConditionPath(expression(guard),events,chain,_unique(proof+cp+variables),variables,_unique(issues+missing),
                (_description(guard),_description(guard,True))))
            targets.append(_sub(target,env))
        return Rule(kind,expression(target),tuple(paths),self.evidence(point.function,point.call.line,kind)),targets

    def string(self,e):
        if e.kind=='string':
            match=re.fullmatch(r'TRIGSTR_(\d+)',str(e.value),re.I)
            if match:
                number=int(match[1])
                if number in self.strings:return self.strings[number]
                self.issue('字符串表缺少 '+str(e.value))
            return str(e.value)
        if e.kind=='binary' and e.value=='+' and all(a.kind=='string' for a in e.args):
            return ''.join(self.string(a) for a in e.args)
        self.issue('动态任务文字未求值：'+expression(e));return expression(e)

    def report(self):
        self.scan();self.build_graph();quests={};items={};unassociated=[];outcomes=[];property_values={}
        for key,(fn,c) in self.created.items():
            q={'title':'未命名任务 '+key,'description':'','required':None,'discovered':None,'items':[],
                'created':[],'completed':[],'failed':[],'resets':[]}
            if c.value=='CreateQuestBJ' and len(c.args)>=3:
                q['title']=self.string(c.args[1]);q['description']=self.string(c.args[2])
                kind=expression(c.args[0]);flags=_QUEST_TYPES.get(kind)
                if kind in self.globals:flags=None
                if flags:q['required'],q['discovered']=flags
                else:self.issue('任务类别不能静态确认：'+kind)
            quests[key]=q
        for key,(fn,c) in self.items.items():
            items[key]={'description':self.string(c.args[1]) if c.value=='CreateQuestItemBJ' and len(c.args)>1 else '', 'completed':[],'resets':[]}
            parent=self.one(c.args[0],'Q') if c.args else None
            if parent in quests:quests[parent]['items'].append(key)
            else:self.issue('任务条目归属无法唯一确认：'+key)
        for p in self.points:
            c=p.call;n=c.value;a=c.args
            if not self.external(n):continue
            if n in ('CreateQuest','CreateQuestBJ'):
                key=self.handle('Q',p.function,c).value
                if key in quests:
                    rule,_=self.make_rule(p,'created',Expr('handle',key));quests[key]['created'].append(rule)
            if n in _TEXT_SETTERS and len(a)>=2:
                kind,prop=_TEXT_SETTERS[n];target=self.one(a[0],kind)
                collection=quests if kind=='Q' else items
                if target in collection:
                    value=self.string(a[1]) if prop in ('title','description') else a[1].value if a[1].kind=='bool' else None
                    values=property_values.setdefault((target,prop),[])
                    if value not in values:values.append(value)
                    if len(values)>1:
                        self.issue('任务属性存在多个静态候选，未推算当前值：'+target+' '+prop)
                        value=' / '.join(values) if prop in ('title','description') else None
                    if value is None:self.issue('任务属性值无法唯一确认：'+expression(c))
                    collection[target][prop]=value
                else:self.issue('任务属性归属无法唯一确认：'+expression(c))
            if n in _STATE_SETTERS and len(a)>=2:
                kind,state=_STATE_SETTERS[n]
                for value,ruletype in ((True,state),(False,'resets')):
                    extra=a[1] if value else _neg(a[1])
                    rule,targets=self.make_rule(p,ruletype,a[0],extra)
                    if not rule.paths:continue
                    resolved={self.one(target,kind) for target in targets}
                    collection=quests if kind=='Q' else items
                    if len(resolved)==1 and None not in resolved and next(iter(resolved)) in collection:
                        collection[next(iter(resolved))][ruletype].append(rule)
                    else:
                        self.issue('任务状态写入归属不明确：'+expression(c));unassociated.append(rule)
            if n in ('CustomVictoryBJ','CustomDefeatBJ') and a:
                kind='victory' if n=='CustomVictoryBJ' else 'defeat'
                gate=Expr('call','AllowVictoryDefeat',(Expr('variable','PLAYER_GAME_RESULT_'+kind.upper()),),c.line)
                rule,_=self.make_rule(p,kind,a[0],gate);outcomes.append(rule)
            elif n=='RemovePlayer' and len(a)>1:
                value=expression(a[1])
                kind={'PLAYER_GAME_RESULT_VICTORY':'victory','PLAYER_GAME_RESULT_DEFEAT':'defeat'}.get(value)
                if value in ('PLAYER_GAME_RESULT_NEUTRAL','PLAYER_GAME_RESULT_TIE'):continue
                if kind is None:kind='unknown-result';self.issue('玩家结算类型无法确认：'+value)
                rule,_=self.make_rule(p,kind,a[0]);outcomes.append(rule)
        definitions=[]
        for key,q in quests.items():
            aliases=tuple(name for name in self.aliases if self.one(Expr('variable',name),'Q')==key)
            qi=tuple(QuestItem(ik,items[ik]['description'],tuple(items[ik]['completed']),tuple(items[ik]['resets'])) for ik in q['items'])
            definitions.append(QuestDefinition(key,q['title'],q['description'],q['required'],q['discovered'],aliases,qi,
                tuple(q['created']),tuple(q['completed']),tuple(q['failed']),tuple(q['resets'])))
        if not definitions:self.issue('未识别标准任务定义；地图可能使用自建任务系统，不能据此认定没有任务')
        return QuestReport(self.snapshot,tuple(definitions),tuple(outcomes),tuple(unassociated),_unique(self.issues),len(self.program.functions),
            tuple((g.name,g.type_name) for g in self.program.globals))


_QUEST_TYPES={'bj_QUESTTYPE_REQ_DISCOVERED':(True,True),'bj_QUESTTYPE_REQ_UNDISCOVERED':(True,False),
    'bj_QUESTTYPE_OPT_DISCOVERED':(False,True),'bj_QUESTTYPE_OPT_UNDISCOVERED':(False,False),
    '0':(True,True),'1':(True,False),'2':(False,True),'3':(False,False)}
_TEXT_SETTERS={name:(kind,prop) for kind,names in (('Q',('QuestSetTitle','QuestSetDescription','QuestSetRequired','QuestSetDiscovered')),
    ('I',('QuestItemSetDescription',))) for name in names for prop in (name.replace('QuestItemSet','').replace('QuestSet','').lower(),)}
_TEXT_SETTERS.update({name+'BJ':value for name,value in tuple(_TEXT_SETTERS.items())})
_STATE_SETTERS={'QuestSetCompleted':('Q','completed'),'QuestSetFailed':('Q','failed'),'QuestItemSetCompleted':('I','completed')}
_STATE_SETTERS.update({name+'BJ':value for name,value in tuple(_STATE_SETTERS.items())})
_PREDICATES={'AllowVictoryDefeat','TriggerEvaluate','RegistrationOccurred','UnconfirmedRegistration','IsUnitDeadBJ','IsUnitAliveBJ','IsUnitEnemy','IsUnitAlly',
    'IsQuestCompleted','IsQuestFailed','IsQuestItemCompleted','IsQuestDiscovered','GetTriggerUnit','Player',
    'GetPlayerState','GetUnitTypeId','GetOwningPlayer','GetEnteringUnit','GetDyingUnit','GetKillingUnit',
    'GetGameDifficulty','GetHeroLevel','GetTriggeringTrigger','GetEventPlayerChatString','GetTriggerPlayer'}


def analyze_quests(snapshot,cancelled=lambda:False):
    return _Analyzer(snapshot,cancelled).report()
