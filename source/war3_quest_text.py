"""R24 read-only player-facing explanations; unsupported meanings stay explicit."""
from __future__ import annotations
import re
from functools import lru_cache
from war3_jass import parse_jass


def clean_text(value):
    text=re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',str(value))
    text=re.sub(r'\|T[^|]*\|t','[图标]',text)
    return text.replace('|n','\n')


def quest_kind(quest,en=False):
    if quest.required is True:return 'Main quest' if en else '主线任务'
    if quest.required is False:return 'Side quest' if en else '支线任务'
    return 'Unconfirmed type' if en else '类型未确认'


@lru_cache(maxsize=512)
def _parse(value):
    if len(value)>20000:raise ValueError('Condition too long')
    code='function R24Condition takes nothing returns boolean\nreturn '+value+'\nendfunction'
    return parse_jass(code).functions['R24Condition'].body[0].exprs[0]


class QuestText:
    def __init__(self,report,en=False):
        self.report,self.en=report,en;self.labels={};self.types={};self.handles={}
        if report is not None:
            for q in report.quests:
                title='“'+clean_text(q.title)+'”'
                self.labels.update({name:title for name in q.aliases})
                self.handles[q.key]=title
                for item in q.items:self.handles[item.key]='“'+clean_text(item.description or '未命名目标')+'”'
            self.types=dict(report.variable_types)

    def text(self,zh,en):return en if self.en else zh

    def parse(self,value):
        # Analyzer handles are evidence identities, not valid JASS identifiers.
        for i,(handle,label) in enumerate(self.handles.items()):
            name='__r24_handle_'+str(i)
            if handle in value:
                value=re.sub(re.escape(handle)+r'(?![A-Za-z_0-9:])',name,value)
                self.labels[name]=label
        value=re.sub(r'\b[TQI]:[A-Za-z_][A-Za-z_0-9]*:\d+:\d+',
            lambda m:'__r24_'+re.sub(r'[^A-Za-z_0-9]','_',m.group()),value)
        return _parse(value)

    def name(self,name):
        if name in self.labels:return self.labels[name]
        label=name
        if name.startswith('gg_rct_'):return self.text('区域“','Region “')+name[7:].replace('_',' ')+'”'
        kind=self.types.get(name)
        labels={'integer':('计数','Counter'),'real':('数值','Value'),'boolean':('标记','Flag'),
                'unit':('单位','Unit'),'group':('单位组','Unit group'),'rect':('区域','Region'),'timer':('计时器','Timer')}
        if kind in labels:return self.text(*labels[kind])+'“'+label+'”'
        return self.text('脚本变量“','Script variable “')+label+'”'

    def expr(self,e):
        value=str(e.value);a=e.args
        if e.kind=='variable':
            constants={'true':'是','false':'否','GAME_DIFFICULTY_EASY':'简单难度',
                'GAME_DIFFICULTY_NORMAL':'普通难度','GAME_DIFFICULTY_HARD':'困难难度',
                'MAP_CONTROL_USER':'真人玩家','MAP_CONTROL_COMPUTER':'电脑玩家'}
            return constants[value] if not self.en and value in constants else self.name(value)
        if e.kind in ('number','rawcode'):return value
        if e.kind=='string':return '“'+clean_text(value)+'”'
        if e.kind=='bool':return self.text('是','true') if e.value else self.text('否','false')
        if e.kind=='null':return self.text('不存在','none')
        if e.kind=='index':return self.expr(a[0])+self.text('的第 ',' entry ')+self.expr(a[1])+self.text('项','')
        if e.kind=='unary':
            if value=='not' and a[0].kind=='variable' and self.types.get(a[0].value)=='boolean':
                return self.name(a[0].value)+self.text('为否（未满足）',' is false')
            return self.text('不满足：','NOT: ')+self.expr(a[0]) if value=='not' else value+self.expr(a[0])
        if e.kind=='binary':
            if value in ('and','or'):
                nodes=[];seen=set()
                def shape(node):return (node.kind,node.value,tuple(shape(child) for child in node.args))
                def has_call(node):return node.kind=='call' or any(has_call(child) for child in node.args)
                def collect(node):
                    if node.kind=='binary' and node.value==value:
                        collect(node.args[0]);collect(node.args[1])
                    else:
                        text=self.expr(node)
                        key=shape(node)
                        # Unknown calls can share wording while testing different
                        # arguments, and may depend on mutable script state.
                        if has_call(node) or key not in seen:nodes.append(text);seen.add(key)
                collect(a[0]);collect(a[1])
                prefix=self.text('全部满足：','ALL: ') if value=='and' else self.text('满足任一项：','ANY: ')
                return prefix+'（'+'；'.join(nodes)+'）'
            ops={'==':('等于','equals'),'!=':('不等于','differs from'),'>=':('不少于','at least'),
                 '<=':('不多于','at most'),'>':('大于','greater than'),'<':('小于','less than'),
                 '+':('加','plus'),'-':('减','minus'),'*':('乘','times'),'/':('除以','divided by')}
            if value in ops:return self.expr(a[0])+' '+self.text(*ops[value])+' '+self.expr(a[1])
        if e.kind=='call':
            if value=='Player' and len(a)==1 and a[0].kind=='number':
                try:return self.text('玩家 ','Player ')+str(int(str(a[0].value))+1)
                except ValueError:pass
            if value=='GetLocalPlayer':return self.text('本地玩家','local player')
            if value in ('GetTriggerUnit','GetEnteringUnit','GetDyingUnit','GetKillingUnit','GetKillingUnitBJ','GetTriggerPlayer','GetTriggeringTrigger'):
                return self.text({'GetTriggerUnit':'触发这次事件的单位','GetEnteringUnit':'进入区域的单位',
                    'GetDyingUnit':'死亡单位','GetKillingUnit':'击杀者','GetKillingUnitBJ':'击杀者',
                    'GetTriggerPlayer':'触发这次事件的玩家','GetTriggeringTrigger':'当前触发器'}[value],value)
            if value in ('GetTriggerEvalCount','GetTriggerExecCount') and len(a)==1:
                return self.expr(a[0])+self.text('的条件检查次数' if value=='GetTriggerEvalCount' else '的执行次数',
                    ' condition-check count' if value=='GetTriggerEvalCount' else ' execution count')
            if value=='IsUnitType' and len(a)==2:
                flags={'UNIT_TYPE_SAPPER':'工兵','UNIT_TYPE_HERO':'英雄','UNIT_TYPE_DEAD':'死亡',
                    'UNIT_TYPE_STRUCTURE':'建筑','UNIT_TYPE_SUMMONED':'召唤','UNIT_TYPE_UNDEAD':'不死族'}
                if a[1].value in flags:return self.expr(a[0])+self.text('具有“'+flags[a[1].value]+'”类型标记',' has type flag '+str(a[1].value))
            if value=='GetPlayerState' and len(a)==2:
                fields={'PLAYER_STATE_RESOURCE_GOLD':('金币','gold'),'PLAYER_STATE_RESOURCE_LUMBER':('木材','lumber'),
                        'PLAYER_STATE_RESOURCE_FOOD_USED':('已用人口','food used'),'PLAYER_STATE_RESOURCE_FOOD_CAP':('人口上限','food cap')}
                if a[1].value in fields:return self.expr(a[0])+self.text('的',' ')+self.text(*fields[a[1].value])
            unary={'IsUnitDeadBJ':('已死亡','is dead'),'IsUnitAliveBJ':('仍存活','is alive'),
                'IsUnitGroupDeadBJ':('中的全部单位已死亡',' has no living units'),
                'CountUnitsInGroup':('的单位数量',' unit count'),
                'IsQuestCompleted':('已完成','is completed'),'IsQuestFailed':('已失败','has failed'),
                'IsQuestItemCompleted':('目标已完成','objective is completed'),'IsQuestDiscovered':('已被发现','is discovered'),
                'GetHeroLevel':('的英雄等级',' hero level'),'GetUnitTypeId':('的单位ID',' unit ID'),
                'GetOwningPlayer':('的所属玩家',' owning player'),'GetWidgetLife':('的生命值',' life')}
            if value in unary and len(a)==1:return self.expr(a[0])+' '+self.text(*unary[value])
            if value in ('IsUnitEnemy','IsUnitAlly') and len(a)==2:
                return self.expr(a[0])+self.text('敌对于' if value=='IsUnitEnemy' else '同盟于', ' is enemy/allied to ')+self.expr(a[1])
            if value in ('GetEventPlayerChatString','GetEventPlayerChatStringMatched'):return self.text('本次输入的聊天内容','entered chat text')
            if value=='GetGameDifficulty':return self.text('当前游戏难度','game difficulty')
            if value=='AllowVictoryDefeat':return self.text('标准胜败结算已获允许（许可状态未实时读取）','standard result permission is enabled (not read live)')
            if value in ('RegistrationOccurred','UnconfirmedRegistration'):
                return self.text('此前的事件注册需要实际发生，当前无法确认','earlier event registration must have occurred; unconfirmed')
            return self.text('尚无法解释的脚本条件（','Unexplained script condition (')+value+')'
        return self.text('尚无法解释的脚本条件','Unexplained script condition')

    def event(self,value):
        if value.startswith('脚本初始化入口 '):return self.text('地图初始化时检查','Checked during map initialization')
        if not value.startswith('事件 '):return self.text('入口尚未确认','Entry unconfirmed')
        try:e=self.parse(value[3:])
        except ValueError:return self.text('事件含义尚无法解释；可查看脚本依据','Event meaning unavailable; see script evidence')
        name=str(e.value);a=e.args
        events={'EVENT_PLAYER_UNIT_DEATH':('有单位死亡时','when a unit dies'),
                'EVENT_UNIT_DEATH':('指定单位死亡时','when the specified unit dies'),
                'EVENT_PLAYER_UNIT_PICKUP_ITEM':('有单位拾取物品时','when a unit picks up an item'),
                'EVENT_PLAYER_UNIT_CONSTRUCT_FINISH':('建筑完成建造时','when construction finishes'),
                'EVENT_PLAYER_UNIT_RESCUED':('有单位获救时','when a unit is rescued'),
                'EVENT_PLAYER_LEAVE':('玩家离开游戏时','when a player leaves')}
        for arg in a:
            if arg.kind=='variable' and arg.value in events:return self.text(*events[arg.value])
        if name in ('TriggerRegisterEnterRectSimple','TriggerRegisterEnterRegion') and len(a)>1:
            return self.text('有单位进入','When a unit enters ')+self.expr(a[1])+self.text('时','')
        if name=='TriggerRegisterDeathEvent' and len(a)>1:return self.expr(a[1])+self.text('死亡时',' dies')
        if name in ('TriggerRegisterTimerEvent','TriggerRegisterTimerEventSingle','TriggerRegisterTimerEventPeriodic') and len(a)>1:
            periodic=name.endswith('Periodic') or (len(a)>2 and a[2].kind=='bool' and a[2].value)
            return self.text('每隔 ' if periodic else '计时达到 ','Every ' if periodic else 'After ')+self.expr(a[1])+self.text(' 秒检查',' seconds')
        if name=='TriggerRegisterPlayerChatEvent' and len(a)>2:
            exact=len(a)>3 and a[3].kind=='bool' and a[3].value
            return self.expr(a[1])+self.text('输入完全匹配的聊天内容 ' if exact else '输入包含以下文字的聊天内容 ', ' enters exact/containing chat text ')+self.expr(a[2])
        return self.text('事件含义尚无法解释（','Unexplained event (')+name+')'

    def rule(self,rule):
        lines=[]
        if not rule.paths:return [self.text('尚未确认此条件能从哪个事件触发。','No confirmed event path for this condition.')]
        groups={}
        for p in rule.paths:
            events=tuple(self.event(x) for x in p.events)
            known=events and not any('尚未' in x or '尚无法' in x or 'unconfirmed' in x or 'Unexplained' in x for x in events)
            key=(p.guard,events if known else p.events)
            if key not in groups:groups[key]=[p,0,False]
            groups[key][1]+=1;groups[key][2]|=bool(p.issues)
        for i,(p,count,has_issues) in enumerate(groups.values(),1):
            if len(groups)>1:lines.append(self.text('方式 {0}（满足任一方式即可到达此设置点）：','Alternative {0}:').format(i))
            if count>1:lines.append(self.text('{0} 条脚本路径共用以下条件，对应事件任一触发时检查：','{0} script paths share these requirements; check on any corresponding event:').format(count))
            lines.append(self.text('触发时机：','When: ')+('；'.join(self.event(x) for x in p.events) if p.events else self.text('尚未确认','unconfirmed')))
            if p.guard=='true':lines.append(self.text('触发后：脚本没有额外条件，随后进入此任务状态。','After the event: no additional test before this quest state.'))
            else:
                try:meaning=self.expr(self.parse(p.guard))
                except ValueError:meaning=self.text('尚无法解释此脚本条件，可查看脚本依据。','Condition unavailable; see script evidence.')
                lines.append(self.text('还需要：','Requires: ')+meaning)
            if has_issues:lines.append(self.text('注意：这条路径仍有未确认部分，不能据此保证游戏里一定触发。','Note: this path has unresolved parts; triggering is not guaranteed.'))
        return lines

    def quest(self,q):
        lines=[clean_text(q.title),'【'+quest_kind(q,self.en)+'】',
            self.text('分类依据：地图脚本的必需／可选标记；类型未知时不推测。','Type follows the script required/optional flag; unknown stays unconfirmed.'),
            '',self.text('任务目标','Objectives'),clean_text(q.description) or self.text('地图未提供任务说明。','No quest description supplied.')]
        for item in q.items:lines.append('• '+clean_text(item.description or self.text('未命名目标','Unnamed objective')))
        lines.extend(('',self.text('完成条件','Completion conditions')))
        for rule in q.completed:lines.extend(self.rule(rule))
        if not q.completed:lines.append(self.text('未找到明确的任务完成条件；可能由尚未解析的自定义逻辑处理。','No explicit completion rule found; custom logic may handle it.'))
        lines.extend(('',self.text('失败条件','Failure conditions')))
        for rule in q.failed:lines.extend(self.rule(rule))
        if not q.failed:lines.append(self.text('未找到明确的任务失败条件。这不表示任务不会失败；请同时查看“整关失败条件”。','No explicit quest failure rule found. This does not mean failure is impossible; see map defeat rules.'))
        for item in q.items:
            if item.completed:
                lines.extend(('',self.text('子目标：','Objective: ')+clean_text(item.description)))
                for rule in item.completed:lines.extend(self.rule(rule))
        lines.extend(('',self.text('以上解释来自地图脚本，不是当前进度。计数、存活状态和注册状态的当前值未读取。','These are script rules, not live progress; counters, life and registration state were not read.')))
        return '\n'.join(lines)
