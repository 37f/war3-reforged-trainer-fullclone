"""Presentation-only entry locations for quests, including pre-created quests.

No live activation inference: the existing helper does not return discovered
state. Creation/discovery paths describe possible entry points, not execution.
"""
import time
from dataclasses import replace

from war3_quest_locations import QuestLocation
from war3_quest_location_links import walk,MAX_RESULTS


class QuestPretriggerLocations:
    def __init__(self,owner):
        self.o=owner;self.links=owner.links;self.program=owner.program
        self.aliases={};self.constructors={};self.sites={};self.incoming={}
        self.callback_keys={};self.events={};self.conditions={};self.executes={};self.dialogs={};self.results={}
        self.deadline=time.monotonic()+20
        quests=owner.reader.report.quests
        for q in quests:
            for name in q.aliases:
                if not name.startswith('bj_'):self.aliases.setdefault(name,set()).add(q.key)
            parts=q.key.rsplit(':',2)
            if len(parts)==3:
                try:self.constructors[(int(parts[1]),int(parts[2]))]=q.key
                except ValueError:pass
        callbacks=[]
        for frame in self.links.frames:
            self.check();call,fn,line,branches,root=frame;name=str(call.value);a=call.args
            if name in self.program.functions:
                self.incoming.setdefault(name,[]).append(frame);continue
            if name.startswith('TriggerRegister') and len(a)>1:
                self.events.setdefault(self.links.key(a[0],fn),[]).append(frame)
            if name in ('TriggerAddAction','TriggerAddCondition') and len(a)>1:
                for node in walk(a[1]):
                    if node.kind=='function_ref':
                        key=self.links.key(a[0],fn);callbacks.append((node.value,key))
                        if name=='TriggerAddCondition':self.conditions.setdefault(key,[]).append(node.value)
            if name in ('TriggerExecute','ConditionalTriggerExecute','TriggerExecuteBJ'):
                for target in a:
                    if target.kind=='variable' and self.o.types.get(target.value)=='trigger':
                        self.executes.setdefault(self.links.key(target,fn),[]).append(frame)
            if name=='DialogDisplay' and len(a)>1:
                if len(a)<3 or a[2].kind!='bool' or a[2].value:
                    self.dialogs.setdefault(self.links.key(a[1],fn),[]).append(frame)
            if name in ('QuestSetDiscovered','QuestSetDiscoveredBJ') and len(a)>=2:
                matches=[(i,self.quest_keys(e)) for i,e in enumerate(a[:2])]
                matched=[(i,keys) for i,keys in matches if len(keys)==1]
                if len(matched)!=1:continue
                i,keys=matched[0];flag=a[1-i]
                if flag.kind=='bool' and not flag.value:continue
                key=next(iter(keys));self.sites.setdefault(key,[]).append(frame)
        for fn,key in callbacks:self.callback_keys.setdefault(fn,set()).add(key)
        timed_out=False
        for q in quests:
            if timed_out:
                self.results[q.key]=(QuestLocation('point','触发前位置未展开',None,None,via='触发前关联分析超过上限'),);continue
            try:self.results[q.key]=self.resolve(q)
            except ValueError:
                timed_out=True;self.results[q.key]=(QuestLocation('point','触发前位置未展开',None,None,via='触发前关联分析超过上限'),)

    def check(self):
        if self.o.cancelled():raise RuntimeError('触发前位置解析已取消')
        if time.monotonic()>self.deadline:raise ValueError('触发前位置关联超过时间上限')

    def quest_keys(self,e):
        if e.kind=='variable':return self.aliases.get(e.value,set())
        if e.kind=='call' and e.value in ('CreateQuest','CreateQuestBJ'):
            key=self.constructors.get((e.line,e.column));return {key} if key else set()
        return set()

    def condition_refs(self,fn,env=None,stack=()):
        if fn in stack or len(stack)>=8 or fn not in self.program.functions:return []
        result=[];pending=list(self.program.functions[fn].body)
        while pending:
            self.check();s=pending.pop();pending.extend(s.body+s.otherwise)
            for value in s.exprs:
                e=self.o.freeze(value,fn,s.line,env);result.extend(self.links.references(e,fn,s.line))
                for n in walk(e):
                    target=self.program.functions.get(n.value) if n.kind=='call' else None
                    if target and target.return_type=='boolean' and len(n.args)==len(target.params):
                        binding={param:arg for (_type,param),arg in zip(target.params,n.args)}
                        result.extend(self.condition_refs(target.name,binding,stack+(fn,)))
        return result

    def prefix_refs(self,fn,line,branches):
        """Only direct statements before this start/caller site, not a whole init graph."""
        result=[]
        for call,context,before,block in self.links.by_fn.get(fn,()):
            if before>line or branches[:len(block)]!=block:continue
            call=self.o.freeze(call,context,before)
            result.extend(self.links.references(call,context,before))
            result.extend(self.links.action_sources((call,context,before,block,fn)))
        # A branch can name a quest giver without passing it to a native call.
        pending=list(self.program.functions[fn].body)
        branch_lines={n for n,_side in branches}
        while pending:
            s=pending.pop();pending.extend(s.body+s.otherwise)
            if s.kind=='if' and s.line in branch_lines:
                result.extend(self.links.references(self.o.freeze(s.exprs[0],fn,s.line),fn,s.line))
        return result

    def entry_refs(self,frame,key):
        _call,fn,line,branches,root=frame;queue=[(fn,line,branches,root,0,())];seen=set();result=[]
        while queue and len(seen)<128:
            self.check();current,before,block,origin,depth,clues=queue.pop(0)
            identity=(current,before,block,origin,clues)
            if identity in seen or current not in self.program.functions or depth>12:continue
            seen.add(identity)
            # Defer helper-prefix clues until an event entry is established.
            # Otherwise an initialization helper would expose unrelated spawns.
            if current not in ('main','config'):
                clues=tuple(dict.fromkeys(clues+tuple(self.prefix_refs(current,before,block))))[:MAX_RESULTS]
            registrations=[]
            for trigger in self.callback_keys.get(current,()):
                registrations.extend(self.events.get(trigger,()))
                for cond in self.conditions.get(trigger,()):result.extend(self.condition_refs(cond))
                for predecessor in self.executes.get(trigger,()):
                    _c,context,at,scope,ancestor=predecessor;queue.append((context,at,scope,ancestor,depth+1,clues))
            if registrations:
                result.extend(clues)
                for event,context,at,_scope,_ancestor in registrations:
                    result.extend(self.links.references(event,context,at))
                    if event.value=='TriggerRegisterDialogEvent' and len(event.args)>1:
                        for display in self.dialogs.get(self.links.key(event.args[1],context),()):
                            _c,context,at,scope,ancestor=display;queue.append((context,at,scope,ancestor,depth+1,clues))
            # Follow exact script callers and explicit timer callbacks. Never
            # collect all objects in main/config or a registration initializer.
            for caller in self.incoming.get(current,()):
                call,context,at,scope,ancestor=caller
                params=self.program.functions[current].params
                task_args=set().union(*(self.quest_keys(arg) for (kind,_param),arg in zip(params,call.args) if kind=='quest'))
                if task_args and key not in task_args:continue
                queue.append((context,at,scope,ancestor,depth+1,clues))
            for context,at,scope in self.links.timer_callbacks.get(current,()):
                # A timer callback is a real entry, even if it is started at init.
                result.extend(clues)
                queue.append((context,at,scope,context,depth+1,clues))
        return result

    @staticmethod
    def mark(place):
        # Keep more specific evidence (candidate/build/drop/teleport); do not
        # relabel a future build-order destination as an NPC's initial position.
        source=place.source
        if source in ('','initial'):
            if place.kind=='region':source='pre-region'
            elif place.kind=='unit':source='pre-npc'
            elif place.kind=='point' and not source:source='pre-point'
        return replace(place,source=source,via='触发前脚本线索'+('；'+place.via if place.via else ''))

    def resolve(self,q):
        result=[]
        for rule in q.created:
            for path in rule.paths:
                self.check()
                # Native task creation in initialization has no implied pickup
                # point. Retain only explicit event/guard references from it.
                for text in [path.guard]+[v[3:] for v in path.events if v.startswith('事件 ')]:
                    try:result.extend(self.links.references(self.o.reader.parse(text)))
                    except ValueError:continue
                # Constructor sites can be inside a later event action.
                fn=rule.evidence.function;at=rule.evidence.line
                result.extend(self.entry_refs((None,fn,at,self.o.blocks.get((fn,at),()),fn),q.key))
        for site in self.sites.get(q.key,()):result.extend(self.entry_refs(site,q.key))
        values=tuple(dict.fromkeys(self.mark(p) for p in result))
        if len(values)>MAX_RESULTS:
            values=values[:MAX_RESULTS-1]+(QuestLocation('point','部分触发前位置未展开',None,None,via='触发前位置超过关联上限'),)
        return values

    def for_quest(self,q):return self.results.get(q.key,())
