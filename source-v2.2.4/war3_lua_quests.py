"""Bounded Lua syntax for static quest evidence; never execute Lua or imports.

Named straight-line/editor functions use the existing data-only quest AST.
An unsupported function is opaque as a whole, preserving its name so a map
override cannot accidentally enable a standard-library adapter.
"""
from dataclasses import dataclass, replace
from types import MappingProxyType
import re
import time

from war3_jass import Expr, Stmt, JassFunction, JassProgram

MAX_BYTES=32*1024*1024
MAX_TOKENS=2_000_000
MAX_DEPTH=96
MAX_FUNCTIONS=50000
MAX_SECONDS=30


class LuaParseError(ValueError):pass


@dataclass(frozen=True,slots=True)
class Token:
    kind:str
    value:str
    line:int
    column:int


@dataclass(frozen=True)
class LuaProgram(JassProgram):
    issues:tuple=()
    opaque:frozenset=frozenset()
    opaque_writes:frozenset=frozenset()


NAME=re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
NUMBER=re.compile(r'(?:0[xX][0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?\d+)?|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)')
LONG=re.compile(r'\[(=*)\[')
ESC={'a':'\a','b':'\b','f':'\f','n':'\n','r':'\r','t':'\t','v':'\v','\\':'\\','"':'"',"'":"'"}


def tokens(text,check):
    out=[];at=0;line=1;col=1
    def advance(raw):
        nonlocal line,col
        n=raw.count('\n');line+=n;col=len(raw.rsplit('\n',1)[-1])+1 if n else col+len(raw)
    def push(kind,value,ln,cl):
        out.append(Token(kind,value,ln,cl))
        if len(out)>MAX_TOKENS:raise LuaParseError('Lua 词法数量超过上限')
    while at<len(text):
        if len(out)%1024==0:check()
        c=text[at];ln,cl=line,col
        if c in ' \t\r\ufeff':advance(c);at+=1;continue
        if c=='\n':push('newline','\n',ln,cl);advance(c);at+=1;continue
        comment=text.startswith('--',at);start=at+2 if comment else at
        match=LONG.match(text,start)
        if match:
            endmark=']'+match[1]+']';end=text.find(endmark,match.end())
            if end<0:raise LuaParseError(f'Lua 长字符串或注释未闭合（行 {ln}）')
            raw=text[at:end+len(endmark)]
            if not comment:
                value=text[match.end():end]
                if value.startswith('\n'):value=value[1:]
                push('string',value,ln,cl)
            advance(raw);at+=len(raw);continue
        if comment:
            end=text.find('\n',at);end=len(text) if end<0 else end
            advance(text[at:end]);at=end;continue
        if c in ('"',"'"):
            quote=c;start=at;at+=1;value=bytearray()
            while at<len(text) and text[at]!=quote:
                if at%4096==0:check()
                c=text[at]
                if c in '\n\r':raise LuaParseError(f'Lua 字符串未闭合（行 {ln}）')
                if c=='\\':
                    at+=1
                    if at>=len(text):raise LuaParseError('Lua 字符串转义被截断')
                    c=text[at]
                    if c in ESC:value.extend(ESC[c].encode('utf8'))
                    elif c=='x' and re.fullmatch('[0-9a-fA-F]{2}',text[at+1:at+3]):
                        value.append(int(text[at+1:at+3],16));at+=2
                    elif c.isascii() and c.isdigit():
                        number=re.match(r'\d{1,3}',text[at:])[0]
                        if int(number)>255:raise LuaParseError('Lua 字节转义超出范围')
                        value.append(int(number));at+=len(number)-1
                    elif c=='\n':value.extend(b'\n')
                    elif c=='z':
                        at+=1
                        while at<len(text) and text[at].isspace():at+=1
                        continue
                    else:raise LuaParseError(f'Lua 字符串转义暂不支持（行 {ln}）')
                else:value.extend(c.encode('utf8'))
                at+=1
            if at>=len(text):raise LuaParseError(f'Lua 字符串未闭合（行 {ln}）')
            at+=1;advance(text[start:at])
            try:push('string',bytes(value).decode('utf8'),ln,cl)
            except UnicodeDecodeError:push('opaque_string','Lua binary string',ln,cl)
            continue
        match=NAME.match(text,at) or NUMBER.match(text,at)
        if match:
            value=match[0]
            # A numeric literal followed by .. must not consume the first dot.
            if value.endswith('.') and text[match.end():match.end()+1]=='.':value=value[:-1]
            push('name' if NAME.fullmatch(value) else 'number',value,ln,cl)
            at+=len(value);advance(value);continue
        op=next((x for x in ('...','..','~=','==','<=','>=','//','<<','>>','::') if text.startswith(x,at)),c)
        if op not in ('...','..','~=','==','<=','>=','//','<<','>>','::','+','-','*','/','%','^','#','~','&','|','<','>','=','(',')','[',']','{','}',',',';',':','.'):
            raise LuaParseError(f'未知 Lua 字符（行 {ln}）')
        push('symbol',op,ln,cl);at+=len(op);advance(op)
    push('eof','',line,col);return out


class Parser:
    precedence={'or':1,'and':2,'==':3,'~=':3,'<':3,'>':3,'<=':3,'>=':3,'..':4,'+':5,'-':5,'*':6,'/':6,'%':6}
    def __init__(self,text,cancelled):
        self.deadline=time.monotonic()+MAX_SECONDS;self.cancelled=cancelled;self.text=text
        if not text.strip():raise LuaParseError('Lua 脚本为空，无法检索任务')
        if len(text.encode('utf8'))>MAX_BYTES:raise LuaParseError('Lua 脚本超过字节上限')
        self.check();self.ts=tokens(text,self.check);self.pos=0;self.limit=len(self.ts)-1;self.depth=0
        self.issues=[];self.opaque=set();self.opaque_writes=set();self.opaque_text_writes=set();self.functions={};self.globals=[];self.block_depth=0
    def check(self):
        if self.cancelled():raise LuaParseError('Lua 解析已取消')
        if time.monotonic()>self.deadline:raise LuaParseError('Lua 解析超过时间上限')
    @property
    def t(self):return self.ts[min(self.pos,self.limit)]
    @property
    def key(self):return self.t.value if self.t.kind in ('name','symbol') else None
    def take(self,value=None):
        t=self.t
        if value is not None and (t.kind not in ('name','symbol') or t.value!=value):self.error('期望 '+value)
        self.pos+=1;return t
    def error(self,message):raise LuaParseError(f'{message}（行 {self.t.line}，列 {self.t.column}）')
    def lines(self):
        while self.pos<self.limit and self.t.kind=='newline':self.pos+=1
    def end_statement(self):
        if self.key==';':self.take()
        if self.pos>=self.limit or self.t.kind in ('newline','eof') or self.key in ('end','else','elseif','until'):self.lines();return
        self.error('同一行复杂语句暂不支持')
    def name(self):
        if self.t.kind!='name':self.error('期望标识符')
        return self.take().value
    def expr(self,minimum=0):
        self.depth+=1
        try:
            if self.depth>MAX_DEPTH:self.error('Lua 表达式超过深度上限')
            self.lines();t=self.take()
            if t.kind in ('string','number'):left=Expr(t.kind,t.value,(),t.line,t.column)
            elif t.value in ('true','false'):left=Expr('bool',t.value=='true',(),t.line,t.column)
            elif t.value=='nil':left=Expr('null',None,(),t.line,t.column)
            elif t.value=='(':
                left=self.expr();self.lines();self.take(')')
            elif t.value in ('not','-'):
                left=Expr('unary',t.value,(self.expr(7),),t.line,t.column)
            elif t.value=='{':
                self.lines();self.take('}');left=Expr('table','{}',(),t.line,t.column)
            elif t.kind=='name' and t.value not in ('function','local','return','end','if','then','else','elseif','for','while','do','repeat','until','break','goto'):
                left=Expr('variable',t.value,(),t.line,t.column)
            else:self.error('Lua 表达式暂不支持')
            while self.pos<self.limit:
                if self.key=='(':
                    if left.kind!='variable':self.error('Lua 间接调用暂不支持')
                    self.take();self.lines();args=[]
                    if self.key!=')':
                        args.append(self.expr());self.lines()
                        while self.key==',':self.take();args.append(self.expr());self.lines()
                    self.take(')');left=Expr('call',left.value,tuple(args),t.line,t.column);continue
                if self.key=='[':
                    self.take();index=self.expr();self.lines();self.take(']');left=Expr('index','',(left,index),t.line,t.column);continue
                level=self.precedence.get(self.key,-1)
                if level<minimum:break
                op=self.take();right=self.expr(level if op.value=='..' else level+1)
                left=Expr('binary','!=' if op.value=='~=' else op.value,(left,right),op.line,op.column)
            return left
        finally:self.depth-=1
    def block(self,endings):
        self.block_depth+=1
        try:
            out=[];self.lines()
            while self.pos<self.limit and self.key not in endings:
                self.check();out.append(self.statement())
            return tuple(out)
        finally:self.block_depth-=1
    def conditional(self):
        t=self.take();condition=self.expr();self.take('then');body=self.block({'else','elseif','end'});other=()
        if self.key=='elseif':other=(self.conditional(),)
        else:
            if self.key=='else':self.take();other=self.block({'end'})
            self.take('end');self.end_statement()
        return Stmt('if',t.line,(condition,),body,other)
    def statement(self):
        self.depth+=1
        try:
            if self.depth>MAX_DEPTH:self.error('Lua 语句超过深度上限')
            t=self.t
            if t.value=='if':return self.conditional()
            if t.value=='return':
                self.take();values=() if self.t.kind=='newline' or self.key in ('end','else','elseif') else (self.expr(),)
                self.end_statement();return Stmt('return',t.line,values)
            if t.value in ('for','while','repeat','do'):
                kind=self.take().value
                if kind=='for':
                    self.error('Lua for 迭代器及局部作用域暂不展开')
                elif kind=='while':
                    guard=self.expr();self.take('do');inner=self.block({'end'});self.take('end')
                    body=(Stmt('if',t.line,(guard,),inner),)
                elif kind=='repeat':
                    body=self.block({'until'});self.take('until');guard=self.expr()
                    body=body+(Stmt('exitwhen',t.line,(guard,)),)
                else:
                    # Extra local scopes could shadow globals; keep whole function opaque.
                    self.error('Lua do 局部作用域暂不展开')
                self.end_statement();return Stmt('loop',t.line,body=body)
            local=t.value=='local'
            if local:
                if self.block_depth>1:self.error('Lua 分支内局部作用域暂不展开')
                self.take();name=self.name();left=Expr('variable',name,(),t.line,t.column)
            else:left=self.expr()
            if self.key=='=':
                self.take();right=self.expr()
                if left.kind not in ('variable','index'):self.error('Lua 赋值目标暂不支持')
                result=Stmt('local',t.line,(right,),name=str(left.value),type_name='lua') if local else Stmt('set',t.line,(left,right))
            elif local:result=Stmt('local',t.line,(Expr('null',None),),name=str(left.value),type_name='lua')
            elif left.kind=='call':result=Stmt('call',t.line,(left,))
            else:self.error('Lua 语句暂不支持')
            self.end_statement();return result
        finally:self.depth-=1
    def matching_end(self,start):
        stack=[]
        for i in range(start,len(self.ts)):
            if i%2048==0:self.check()
            t=self.ts[i]
            if t.kind!='name':continue
            if t.value in ('function','if','do','repeat'):stack.append(t.value)
            elif t.value in ('end','until'):
                if not stack:raise LuaParseError(f'Lua 控制块闭合无效（行 {t.line}）')
                expected='repeat' if t.value=='until' else None
                if (stack[-1]=='repeat')!=(expected=='repeat'):raise LuaParseError(f'Lua 控制块闭合不同（行 {t.line}）')
                stack.pop()
                if not stack:return i
        raise LuaParseError(f'Lua 函数或控制块未闭合（行 {self.ts[start].line}）')
    def opaque_function(self,name,start,end,reason):
        self.opaque.add(name)
        self.functions[name]=JassFunction(name,(), 'lua-unknown',(),self.ts[start].line,self.ts[end].line)
        self.issues.append(f'Lua 未展开函数 {name}（行 {self.ts[start].line}）：{reason}')
        for i in range(start,end):
            t=self.ts[i]
            if t.kind=='name' and self.ts[i+1].value=='=':self.record_unknown_write(i)
            if t.kind=='name' and t.value=='function' and self.ts[i+1].kind=='name':
                nested=self.ts[i+1].value
                if nested!=name:
                    self.opaque.add(nested);self.functions[nested]=JassFunction(nested,(),'lua-unknown',(),t.line,self.ts[end].line)
    def record_unknown_write(self,i):
        name=self.ts[i].value;self.opaque_writes.add(name)
        if i+3>=len(self.ts):self.opaque_text_writes.add(name);return
        rhs=self.ts[i+2];after=self.ts[i+3]
        empty=(rhs.kind=='string' and not rhs.value) or (rhs.kind=='name' and rhs.value=='nil')
        terminal=after.kind=='newline' or after.kind=='symbol' and after.value==';' or after.kind=='name' and after.value=='end'
        # Static text candidates already omit literal empty initialization/reset
        # values. This is not a claim that the variable currently holds text.
        if not (empty and terminal):self.opaque_text_writes.add(name)
    def function(self):
        start=self.pos;end=self.matching_end(start);saved_limit=self.limit
        name=self.ts[start+1].value
        try:
            self.limit=end+1;self.take('function');name=self.name();self.take('(');params=[];self.lines()
            if self.key!=')':
                params.append(('lua',self.name()));self.lines()
                while self.key==',':self.take();params.append(('lua',self.name()));self.lines()
            self.take(')');body=self.block({'end'});self.take('end')
            if self.pos!=end+1:self.error('Lua 函数解析边界不同')
            if name in self.functions:raise LuaParseError('函数存在重复定义')
            self.functions[name]=JassFunction(name,tuple(params),'lua',body,self.ts[start].line,self.ts[end].line)
        except LuaParseError as exc:self.opaque_function(name,start,end,str(exc))
        finally:self.pos=end+1;self.limit=saved_limit;self.lines()
    def skip_top(self):
        start=self.pos;t=self.t
        if self.ts[start+1].value=='=':self.record_unknown_write(start)
        if t.kind=='name' and t.value in ('if','do','function'):
            end=self.matching_end(start)
            # Nested native/BJ overrides remain opaque, never treated as builtins.
            for i in range(start,end):
                if self.ts[i].value=='function' and self.ts[i].kind=='name' and self.ts[i+1].kind=='name':
                    name=self.ts[i+1].value
                    if name not in self.functions:self.opaque_function(name,i,end,'嵌套或条件定义')
            self.pos=end+1
        else:
            depth=0
            while self.pos<self.limit:
                token=self.t
                if token.kind=='newline' and not depth:break
                if token.kind=='name' and token.value=='function':
                    self.pos=self.matching_end(self.pos)+1;continue
                if token.kind=='symbol' and token.value in ('(','{','['):depth+=1
                elif token.kind=='symbol' and token.value in (')','}',']'):depth-=1
                if depth<0:self.error('Lua 顶层结构未配对')
                self.pos+=1
        for i in range(start,min(len(self.ts)-3,max(start,self.pos-1))):
            if self.ts[i].kind=='name' and self.ts[i+1].value=='=':self.record_unknown_write(i)
            if self.ts[i].kind=='name' and self.ts[i].value=='function' and self.ts[i+1].kind=='name':
                name=self.ts[i+1].value;self.opaque.add(name)
                self.functions[name]=JassFunction(name,(),'lua-unknown',(),self.ts[i].line,self.ts[min(self.pos,self.limit)].line)
        self.issues.append(f'Lua 未展开顶层语句（行 {t.line}）');self.lines()
    def parse(self):
        self.lines()
        while self.pos<self.limit:
            self.check()
            if self.key=='function' and self.t.kind=='name':self.function()
            elif self.t.kind=='name' and self.ts[self.pos+1].value=='=':
                start=self.pos
                try:
                    s=self.statement();left,right=s.exprs
                    if left.kind!='variable':raise LuaParseError('顶层复杂赋值')
                    self.globals.append(Stmt('global',s.line,(right,),name=left.value,type_name='lua',array=right.kind=='table'))
                except LuaParseError:
                    self.pos=start;self.skip_top()
            else:self.skip_top()
            if len(self.functions)>MAX_FUNCTIONS:raise LuaParseError('Lua 函数数量超过上限')
        return self.finish()
    def finish(self):
        # Return-type proof and callbacks are syntax only. Unknown/opaque
        # functions cannot be inlined as boolean predicates.
        def walk(body):
            for s in body:
                yield s;yield from walk(s.body);yield from walk(s.otherwise)
        calls=set();writes={g.name for g in self.globals}|self.opaque_writes
        for fn in self.functions.values():
            locals_={n for _,n in fn.params}|{s.name for s in walk(fn.body) if s.kind=='local'}
            for s in walk(fn.body):
                if s.kind=='set' and s.exprs[0].kind=='variable' and s.exprs[0].value not in locals_:writes.add(s.exprs[0].value)
                pending=list(s.exprs)
                while pending:
                    e=pending.pop();pending.extend(e.args)
                    if e.kind=='call':calls.add(e.value)
        for name in writes&calls:
            self.opaque.add(name);self.functions[name]=JassFunction(name,(),'lua-unknown',(),1,1)
            self.issues.append('Lua 函数名存在赋值，不能按内置函数处理：'+name)
        known=set(self.functions)-self.opaque
        boolean=set()
        bool_native={'IsUnitDeadBJ','IsUnitAliveBJ','IsUnitEnemy','IsUnitAlly','IsQuestCompleted','IsQuestFailed','IsQuestItemCompleted','IsQuestDiscovered','IsTriggerEnabled','IsUnitType','IsUnitInGroup'}-set(self.functions)
        def is_bool(e):return e.kind=='bool' or e.kind=='binary' and e.value in ('==','!=','<','>','<=','>=') or e.kind=='unary' and e.value=='not' or e.kind=='call' and e.value in boolean|bool_native
        def returns(body):
            if not body:return False
            s=body[-1]
            return s.kind=='return' and bool(s.exprs) and is_bool(s.exprs[0]) or s.kind=='if' and returns(s.body) and returns(s.otherwise)
        for _ in range(32):
            added=set()
            for name in known-boolean:
                fn=self.functions[name];values=[s for s in walk(fn.body) if s.kind=='return']
                if values and returns(fn.body) and all(s.exprs and is_bool(s.exprs[0]) for s in values):added.add(name)
            if not added:break
            boolean.update(added)
        def expr(e,locals_=frozenset()):
            args=tuple(expr(a,locals_) for a in e.args);e=replace(e,args=args)
            if e.kind=='call':
                callbacks={'Condition':(0,), 'Filter':(0,), 'TriggerAddAction':(1,), 'TimerStart':(3,), 'ForGroup':(1,), 'ForForce':(1,)}
                if e.value not in self.functions and e.value in callbacks:
                    converted=list(args)
                    for i in callbacks[e.value]:
                        if i<len(args) and args[i].kind=='variable' and args[i].value in known and args[i].value not in locals_:
                            converted[i]=replace(args[i],kind='function_ref')
                    e=replace(e,args=tuple(converted))
                if e.value=='FourCC' and e.value not in self.functions and len(args)==1 and args[0].kind=='string' and len(args[0].value.encode('utf8'))==4:
                    e=replace(e,kind='rawcode',value=args[0].value,args=())
            if e.kind=='binary' and e.value in ('==','!='):
                a,b=e.args
                if (a.kind=='bool' and not is_bool(b)) or (b.kind=='bool' and not is_bool(a)):
                    # JASS boolean simplification would be wrong for Lua's 0/"".
                    e=replace(e,value='lua_equal' if e.value=='==' else 'lua_not_equal')
            return e
        def body(stmts,locals_):
            rows=[]
            for s in stmts:
                # Lua and/or return operands. The JASS boolean dataflow cannot
                # safely infer handles assigned by that value-selection idiom.
                if s.kind in ('local','set'):
                    pending=[s.exprs[-1]] if s.exprs else []
                    while pending:
                        e=pending.pop();pending.extend(e.args)
                        if e.kind=='binary' and e.value in ('and','or'):raise LuaParseError('Lua and/or 值选择赋值暂不展开')
                rows.append(replace(s,exprs=tuple(expr(e,locals_) for e in s.exprs),body=body(s.body,locals_),otherwise=body(s.otherwise,locals_)))
            return tuple(rows)
        for name,fn in tuple(self.functions.items()):
            locals_={n for _,n in fn.params}|{s.name for s in walk(fn.body) if s.kind=='local'}
            try:self.functions[name]=replace(fn,return_type='boolean' if name in boolean else fn.return_type,body=body(fn.body,locals_))
            except LuaParseError as exc:
                self.opaque.add(name);self.functions[name]=replace(fn,return_type='lua-unknown',body=())
                self.opaque_writes.update(s.exprs[0].value for s in walk(fn.body) if s.kind=='set' and s.exprs[0].kind=='variable')
                self.opaque_text_writes.update(s.exprs[0].value for s in walk(fn.body) if s.kind=='set' and s.exprs[0].kind=='variable' and not (s.exprs[1].kind=='null' or s.exprs[1].kind=='string' and not s.exprs[1].value))
                self.issues.append(f'Lua 未展开函数 {name}（行 {fn.line}）：{exc}')
        constructors={'Rect':'rect','CreateRegion':'region','Location':'location','GetRectCenter':'location',
            'CreateCameraSetup':'camerasetup','CreateUnit':'unit','CreateUnitAtLoc':'unit','CreateUnitAtLocSaveLast':'unit',
            'BlzCreateUnitWithSkin':'unit','CreateItem':'item','CreateItemLoc':'item','CreateDestructable':'destructable',
            'CreateDestructableZ':'destructable','CreateDeadDestructable':'destructable','CreateTrigger':'trigger',
            'CreateQuest':'quest','GetLastCreatedQuestBJ':'quest','GetLastCreatedQuestItemBJ':'questitem','QuestCreateItem':'questitem'}
        kinds={};aliases={}
        for fn in self.functions.values():
            locals_={n for _,n in fn.params}|{s.name for s in walk(fn.body) if s.kind=='local'}
            for s in walk(fn.body):
                if s.kind!='set' or s.exprs[0].kind!='variable' or s.exprs[0].value in locals_:continue
                lhs,rhs=s.exprs
                if rhs.kind=='call' and rhs.value not in self.functions and rhs.value in constructors:kinds.setdefault(lhs.value,set()).add(constructors[rhs.value])
                elif rhs.kind=='variable':aliases.setdefault(lhs.value,set()).add(rhs.value)
        for _ in range(16):
            changed=False
            for name,targets in aliases.items():
                values=set().union(*(kinds.get(t,set()) for t in targets))
                if not values<=kinds.get(name,set()):kinds.setdefault(name,set()).update(values);changed=True
            if not changed:break
        globals_=tuple(replace(g,type_name=next(iter(kinds[g.name]))) if len(kinds.get(g.name,()))==1 else g for g in self.globals)
        return LuaProgram(MappingProxyType(self.functions),globals_,MappingProxyType({}),(),self.text,tuple(dict.fromkeys(self.issues)),frozenset(self.opaque),frozenset(self.opaque_text_writes))


def parse_lua(text,cancelled=lambda:False):return Parser(text,cancelled).parse()


class LuaStaticText:
    """Resolve only unique script text candidates, never current variable values."""
    def __init__(self,program,strings):
        self.program=program;self.strings=strings;self.values={};self.conditional=set();self.cache={};self.base_candidates=set()
        from war3_quest_analysis import expression
        self.expression=expression
        def add(name,e):
            if e.kind!='null' and not (e.kind=='string' and not e.value):self.values.setdefault(name,[]).append(e)
        for g in program.globals:
            if g.exprs:add(g.name,g.exprs[0])
        for fn in program.functions.values():
            pending={};locals_={n for _,n in fn.params}
            def sub(e,name,old):
                if e.kind=='variable' and e.value==name:return old
                return replace(e,args=tuple(sub(a,name,old) for a in e.args))
            def scan(body,conditional=False):
                for s in body:
                    if s.kind=='local':locals_.add(s.name)
                    if s.kind=='set':
                        lhs,rhs=s.exprs;name=expression(lhs)
                        if lhs.kind=='variable' and lhs.value in locals_:continue
                        if conditional:self.conditional.add(name)
                        else:
                            if name in pending:rhs=sub(rhs,name,pending[name])
                            pending[name]=rhs
                    scan(s.body,conditional or s.kind in ('if','loop'));scan(s.otherwise,True)
            scan(fn.body)
            for name,e in pending.items():add(name,e)
    def resolve(self,e,seen=frozenset()):
        if len(seen)>48:return None
        if e.kind=='string':
            m=re.fullmatch(r'TRIGSTR_(\d+)',e.value,re.I)
            return self.strings.get(int(m[1])) if m else e.value
        if e.kind=='call' and e.value=='StringIdentity' and len(e.args)==1:
            if e.value not in self.program.functions:return self.resolve(e.args[0],seen)
            arg=e.args[0]
            if arg.kind=='string' and re.fullmatch(r'TRIGSTR_\d+',arg.value,re.I):
                # The source WTS entry is observable even if a map overrides
                # the wrapper. It is labelled as a base-text candidate, never
                # represented as the wrapper's proven or current return value.
                value=self.resolve(arg,seen)
                if value is not None:self.base_candidates.add(arg.value)
                return value
            return None
        if e.kind=='binary' and e.value=='..':
            a,b=(self.resolve(x,seen) for x in e.args)
            return a+b if a is not None and b is not None and len(a)+len(b)<=1024*1024 else None
        if e.kind not in ('variable','index'):return None
        name=self.expression(e)
        if name in seen or name in self.conditional or name in self.program.opaque_writes:return None
        if name in self.cache:return self.cache[name]
        values=[self.resolve(v,seen|{name}) for v in self.values.get(name,())]
        usable=set(values)
        result=next(iter(usable)) if len(usable)==1 and None not in usable else None
        self.cache[name]=result;return result
