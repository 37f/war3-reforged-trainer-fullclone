"""R23 immutable, conservative original quest-completion plans.

This module only inspects syntax. Eligibility is a static precondition, never
permission to dispatch: the native client must still bind the current quest,
trigger actions, VM and source before an explicit user execution request.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time

from war3_jass import parse_jass
from war3_native_profile import NATIVE_NAMES
from war3_quest_analysis import expression

MAX_PLAN_SECONDS=30
MAX_FLOW_FUNCTIONS=256
MAX_FLOW_CALLS=20000

# Existing R22 adapters and queue wrappers were checked against this build's
# installed blizzard.j (docs/r23-runtime-feasibility.md). Map definitions take
# precedence and are traversed instead of trusting a same-named adapter.
_ADAPTERS=frozenset(('QuestSetCompletedBJ','QuestSetFailedBJ','QuestMessageBJ',
    'ConditionalTriggerExecute','TriggerExecuteBJ','QueuedTriggerAddBJ',
    'QueuedTriggerRemoveBJ'))
_NATIVES=frozenset(NATIVE_NAMES)
_DISPATCH=frozenset(('TriggerExecute','TriggerExecuteWait','ConditionalTriggerExecute',
    'TriggerExecuteBJ','QueuedTriggerAddBJ'))
_EVENT_RESPONSES=frozenset(('GetTriggerUnit','GetEnteringUnit','GetLeavingUnit',
    'GetDyingUnit','GetKillingUnit','GetTriggerPlayer','GetAttacker',
    'GetManipulatingUnit','GetManipulatedItem','GetOrderedUnit','GetOrderPointX',
    'GetOrderPointY','GetOrderTarget','GetOrderTargetUnit','GetSpellAbilityUnit',
    'GetSpellTargetUnit','GetSpellTargetX','GetSpellTargetY','GetEnumUnit',
    'GetFilterUnit','GetEnumPlayer','GetFilterPlayer','GetExpiredTimer',
    'GetEventPlayerChatString','GetEventPlayerChatStringMatched',
    'GetEventDamage','GetEventDamageSource','GetTriggerEventId','GetResearched',
    'GetResearchingUnit','GetTrainedUnit','GetTrainedUnitType','GetConstructedStructure',
    'GetCancelledStructure','GetSummonedUnit','GetSummoningUnit','GetLearnedSkill',
    'GetLearnedSkillLevel','GetIssuedOrderId','GetSoldUnit','GetSellingUnit',
    'GetBuyingUnit','GetSoldItem','GetDetectedUnit','GetLoadedUnit','GetTransportUnit',
    'GetLevelingUnit','GetRevivableUnit','GetRevivingUnit','GetChangingUnit',
    'GetChangingUnitPrevOwner','GetDecayingUnit','GetRescuer'))


@dataclass(frozen=True)
class CompletionEvidence:
    function:str
    line:int
    source:str
    role:str


@dataclass(frozen=True)
class CompletionPlan:
    snapshot_identity:object
    snapshot_token:int
    origin:str
    script_sha256:str
    strings_sha256:str
    quest_key:str
    quest_title:str
    quest_alias:str
    entry_trigger:str|None
    entry_function:str|None
    chain_functions:tuple[str,...]
    trigger_bindings:tuple[tuple[str,tuple[str,...]],...]
    recognized_calls:tuple[str,...]
    evidence:tuple[CompletionEvidence,...]
    root_conditions:tuple[str,...]
    eligible:bool
    reasons:tuple[str,...]


def _unique(values):return tuple(dict.fromkeys(values))


def _statements(body):
    pending=list(reversed(body))
    while pending:
        statement=pending.pop();yield statement
        pending.extend(reversed(statement.otherwise))
        pending.extend(reversed(statement.body))


def _expressions(expr):
    pending=[expr]
    while pending:
        node=pending.pop();yield node
        pending.extend(reversed(node.args))


def _calls(body):
    for statement in _statements(body):
        for expr in statement.exprs:
            yield from (node for node in _expressions(expr) if node.kind=='call')


def _global_name(expr,globals_,kind):
    if expr.kind!='variable':return None
    declaration=globals_.get(expr.value)
    return str(expr.value) if declaration and declaration.type_name==kind and not declaration.array else None


def build_completion_plan(report,quest_key,cancelled=lambda:False)->CompletionPlan:
    """Bind one exact static quest definition to its whole original action root.

    A registered event root must be unique. Direct map calls and explicit
    trigger/queue dispatches are followed; event response values, dynamic calls,
    action-local branches, loops and unknown wrappers keep execution disabled.
    Root trigger conditions keep execution disabled: TriggerExecute runs
    actions directly and cannot synthesize their original prerequisite event.
    """
    snapshot=report.snapshot
    matches=[quest for quest in report.quests if quest.key==quest_key]
    if len(matches)!=1:raise ValueError('任务脚本键不是唯一的现有任务定义')
    quest=matches[0];reasons=[];deadline=time.monotonic()+MAX_PLAN_SECONDS
    def check():
        if cancelled():raise RuntimeError('任务完成入口分析已取消')
        if time.monotonic()>deadline:raise TimeoutError('任务完成入口分析超过时间上限')
    def result(alias='',entry=None,functions=(),bindings=(),calls=(),proof=(),conditions=()):
        return CompletionPlan(snapshot.identity,snapshot.session_token,snapshot.origin,
            snapshot.script_sha256,snapshot.strings_sha256,quest.key,quest.title,alias,
            entry[0] if entry else None,entry[1] if entry else None,tuple(functions),
            tuple(bindings),_unique(calls),tuple(proof),tuple(conditions),not reasons,_unique(reasons))
    check()
    if (hashlib.sha256(snapshot.script).hexdigest()!=snapshot.script_sha256 or
        hashlib.sha256(snapshot.strings_data).hexdigest()!=snapshot.strings_sha256):
        reasons.append('任务快照内容与记录的哈希不一致');return result()
    if snapshot.language!='jass':
        reasons.append('当前脚本语言不支持完成入口：'+snapshot.language);return result()
    program=parse_jass(snapshot.script.decode('utf-8-sig'),cancelled)
    globals_={item.name:item for item in program.globals}
    aliases=[name for name in quest.aliases if name in globals_ and
        globals_[name].type_name=='quest' and not globals_[name].array]
    if len(aliases)!=1:
        reasons.append('没有唯一的标量 quest 全局变量可绑定当前任务');return result()
    alias=aliases[0]
    if any(alias in other.aliases for other in report.quests if other.key!=quest.key):
        reasons.append('该任务全局变量关联多个静态任务实例');return result(alias)
    all_calls={};straight_calls=set();straight_sets=set()
    for name,fn in program.functions.items():
        check();all_calls[name]=tuple(_calls(fn.body))
        for statement in fn.body:
            if statement.kind=='call':
                call=statement.exprs[0];straight_calls.add((name,call.line,call.column))
            elif statement.kind=='set':straight_sets.add((name,statement.line))
    setters=set()
    setter_lines={(rule.evidence.function,rule.evidence.line) for rule in quest.completed}
    for name,calls in all_calls.items():
        check()
        for call in calls:
            if (call.value in ('QuestSetCompleted','QuestSetCompletedBJ') and len(call.args)==2 and
                call.args[0].kind=='variable' and call.args[0].value==alias and
                call.args[1].kind=='bool' and call.args[1].value is True and
                (name,call.line) in setter_lines):setters.add(name)
    if not setters:
        reasons.append('未确认该任务的明确完成状态写入')
        if any(call.value=='ExecuteFunc' for calls in all_calls.values() for call in calls):
            reasons.append('动态或间接 ExecuteFunc 不能作为已校验的完成入口')
        return result(alias)

    # Only unconditional direct initialization from main proves registration.
    initialized=set();pending=['main']
    while pending:
        check();name=pending.pop()
        if name in initialized or name not in program.functions:continue
        initialized.add(name)
        for statement in program.functions[name].body:
            if statement.kind=='call':
                call=statement.exprs[0]
                if call.value in program.functions:pending.append(call.value)
    triggers={};creation_sites={};trigger_writes={};trigger_mutations=set()
    for name,fn in program.functions.items():
        check()
        for statement in _statements(fn.body):
            if statement.kind=='set':
                left,right=statement.exprs
                target=_global_name(left,globals_,'trigger')
                if target:trigger_writes.setdefault(target,[]).append((name,statement.line))
                if target and right.kind=='call' and right.value=='CreateTrigger':
                    creation_sites.setdefault(target,[]).append((name,statement.line))
        for call in all_calls[name]:
            if not call.args:continue
            trigger=_global_name(call.args[0],globals_,'trigger')
            if not trigger:continue
            if call.value in ('TriggerClearActions','TriggerRemoveAction','DestroyTrigger'):
                trigger_mutations.add(trigger)
            item=triggers.setdefault(trigger,{'actions':[],'events':[],'conditions':[]})
            if call.value=='TriggerAddAction' and len(call.args)==2:
                item['actions'].append((name,call,call.args[1]))
            elif str(call.value).startswith('TriggerRegister'):
                item['events'].append((name,call))
            elif call.value=='TriggerAddCondition' and len(call.args)==2:
                item['conditions'].append(expression(call.args[1]))

    def flow(root):
        functions=[];proof=[];calls_seen=[];problems=[];bindings=[];visiting=set();visited=set();reaches=False
        def trigger_actions(trigger):
            item=triggers.get(trigger)
            if not item or not item['actions']:
                problems.append('原触发器没有可确认的动作注册：'+str(trigger));return ()
            if len(creation_sites.get(trigger,()))!=1:
                problems.append('原触发器创建位置不唯一：'+trigger)
            elif creation_sites[trigger][0][0] not in initialized:
                problems.append('原触发器初始化未从 main 无条件到达：'+trigger)
            if (len(trigger_writes.get(trigger,()))!=1 or
                any(site not in straight_sets for site in trigger_writes.get(trigger,()))):
                problems.append('原触发器全局变量存在额外或条件赋值：'+trigger)
            if trigger in trigger_mutations:
                problems.append('原触发器动作列表或实例存在后续修改：'+trigger)
            actions=[]
            for init,call,action in item['actions']:
                if (init not in initialized or action.kind!='function_ref' or
                    (init,call.line,call.column) not in straight_calls):
                    problems.append('原触发器动作注册不唯一或未确认初始化：'+trigger)
                if action.kind=='function_ref':actions.append(str(action.value))
            bindings.append((trigger,tuple(actions)))
            return tuple(actions)
        def visit(name):
            nonlocal reaches
            check()
            if name in visiting:
                problems.append('原完成流程存在递归或触发器循环：'+name);return
            if name in visited:return
            if len(functions)>=MAX_FLOW_FUNCTIONS:
                problems.append('原完成流程函数数量超过上限');return
            fn=program.functions.get(name)
            if fn is None:
                problems.append('原动作函数体无法确认：'+name);return
            if name in setters:reaches=True
            if fn.params or fn.return_type!='nothing':
                problems.append('原动作函数签名不是无参数、无返回值：'+name);return
            visiting.add(name);functions.append(name)
            for statement in _statements(fn.body):
                if statement.kind=='if':problems.append('原动作包含尚未校验的分支条件：'+name+':'+str(statement.line))
                if statement.kind in ('loop','exitwhen','debug'):
                    problems.append('原动作包含未支持的循环或 debug 执行上下文：'+name)
                for expr in statement.exprs:
                    if any(node.kind=='function_ref' for node in _expressions(expr)):
                        problems.append('原动作包含未校验的回调上下文：'+name)
            for call in all_calls[name]:
                check();calls_seen.append(str(call.value))
                if len(calls_seen)>MAX_FLOW_CALLS:
                    problems.append('原完成流程调用数量超过上限');break
                proof.append(CompletionEvidence(name,call.line,expression(call),'原动作调用'))
                callee=str(call.value)
                if (callee in _EVENT_RESPONSES or callee.startswith(('GetEvent','GetEnum','GetFilter')) or
                    (callee.startswith('GetTrigger') and callee!='GetTriggeringTrigger')):
                    problems.append('原动作依赖缺失的事件响应／枚举上下文：'+callee)
                if callee=='ExecuteFunc':
                    problems.append('原动作包含动态或间接函数调用 ExecuteFunc');continue
                if callee in program.functions:
                    if call.args:problems.append('原动作调用带参数函数，尚未校验实参上下文：'+callee)
                    visit(callee);continue
                if callee in _DISPATCH:
                    target=_global_name(call.args[0],globals_,'trigger') if call.args else None
                    if not target:
                        problems.append('子触发器身份无法静态绑定：'+expression(call));continue
                    for action in trigger_actions(target):visit(action)
                elif callee not in _NATIVES and callee not in _ADAPTERS:
                    problems.append('原动作调用的函数体或标准接口未确认：'+callee)
                if (callee in ('TimerStart','ForGroup','ForForce') or callee.startswith('Enum') or
                    callee in ('TriggerAddAction','TriggerAddCondition') or callee.startswith('TriggerRegister')):
                    problems.append('原动作会建立未校验的回调或事件上下文：'+callee)
                if callee in ('CreateQuest','CreateQuestBJ','DestroyQuest'):
                    problems.append('原动作会创建或销毁任务实例，无法保持本次任务身份：'+callee)
                if (callee in ('QuestSetCompleted','QuestSetCompletedBJ','QuestSetFailed','QuestSetFailedBJ') and
                    len(call.args)>1 and call.args[0].kind=='variable' and call.args[0].value==alias and
                    (callee.startswith('QuestSetFailed') or call.args[1].kind!='bool' or not call.args[1].value)):
                    problems.append('原动作还会失败或重置同一任务，完成结果不唯一')
                if (callee in ('QuestSetCompleted','QuestSetCompletedBJ') and call.args and
                    not (call.args[0].kind=='variable' and call.args[0].value==alias)):
                    problems.append('原动作还会完成其他任务或无法绑定的任务，不能作为单个任务入口')
            visiting.remove(name);visited.add(name)
        actions=trigger_actions(root)
        if triggers[root]['conditions']:
            problems.append('原入口条件尚未校验，不能跳过条件直接执行动作：'+root)
        if any(init not in initialized or (init,call.line,call.column) not in straight_calls
            for init,call in triggers[root]['events']):
            problems.append('原事件注册不是已确认的无条件初始化：'+root)
        if len(actions)!=1:problems.append('入口触发器的动作函数不唯一：'+root)
        for action in actions:visit(action)
        return reaches,actions,tuple(functions),_unique(bindings),_unique(calls_seen),tuple(proof),_unique(problems)

    candidates=[]
    for trigger,item in triggers.items():
        check()
        if not item['events']:continue
        candidate=flow(trigger)
        if candidate[0]:candidates.append((trigger,candidate))
    if len(candidates)!=1:
        reasons.append('多个原事件入口可完成此任务，无法唯一选择完整流程' if candidates else
            '未找到从原事件触发器到该任务完成状态的完整动作链')
        return result(alias)
    trigger,candidate=candidates[0]
    _,actions,functions,bindings,calls,proof,problems=candidate
    reasons.extend(problems)
    return result(alias,(trigger,actions[0] if len(actions)==1 else ''),functions,bindings,calls,proof,
        triggers[trigger]['conditions'])
