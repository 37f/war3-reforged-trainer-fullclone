"""R22 bounded JASS syntax/evidence. Parses data; never executes map code."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import re
import time
from types import MappingProxyType
from typing import Mapping

MAX_BYTES=32*1024*1024
MAX_TOKENS=500000
MAX_NODES=500000
MAX_NESTING=128
MAX_FUNCTIONS=50000
MAX_SECONDS=30


class JassParseError(ValueError):
    def __init__(self,message,line=1,column=1):
        self.line,self.column=line,column
        super().__init__(f'{message}（行 {line}，列 {column}）')


@dataclass(frozen=True)
class Expr:
    kind:str
    value:object
    args:tuple[Expr,...]=()
    line:int=1
    column:int=1


@dataclass(frozen=True)
class Stmt:
    kind:str
    line:int
    exprs:tuple[Expr,...]=()
    body:tuple[Stmt,...]=()
    otherwise:tuple[Stmt,...]=()
    name:str=''
    type_name:str=''
    array:bool=False
    constant:bool=False


@dataclass(frozen=True)
class JassFunction:
    name:str
    params:tuple[tuple[str,str],...]
    return_type:str
    body:tuple[Stmt,...]
    line:int
    end_line:int
    constant:bool=False


@dataclass(frozen=True)
class JassProgram:
    functions:Mapping[str,JassFunction]
    globals:tuple[Stmt,...]
    natives:Mapping[str,JassFunction]
    types:tuple[tuple[str,str],...]
    text:str


@dataclass(frozen=True)
class _Token:
    kind:str
    value:str
    line:int
    column:int


class _Budget:
    def __init__(self,cancelled):
        self.cancelled=cancelled;self.deadline=time.monotonic()+MAX_SECONDS
        self.nodes=0;self.depth=0;self.check()

    def check(self,line=1,column=1):
        if self.cancelled():raise JassParseError('脚本解析已取消',line,column)
        if time.monotonic()>self.deadline:raise JassParseError('脚本解析超过时间上限',line,column)

    def node(self,line):
        self.nodes+=1
        if self.nodes>MAX_NODES:raise JassParseError('脚本节点超过数量上限',line)
        if self.nodes%256==0:self.check(line)

    @contextmanager
    def nested(self,line):
        self.depth+=1
        try:
            if self.depth>MAX_NESTING:raise JassParseError('脚本嵌套超过深度上限',line)
            yield
        finally:self.depth-=1


_NAME=re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
_NUMBER=re.compile(r'(?:\$[0-9a-fA-F]+|0[xX][0-9a-fA-F]+|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)')
_ESCAPES={'n':'\n','r':'\r','t':'\t','"':'"',"'":"'",'\\':'\\'}


def _tokens(text,budget):
    if len(text.encode('utf8'))>MAX_BYTES:raise JassParseError('脚本超过字节上限')
    out=[];i=0;line=1;column=1
    def push(kind,value,ln,col):
        out.append(_Token(kind,value,ln,col))
        if len(out)>MAX_TOKENS:raise JassParseError('脚本词法数量超过上限',ln,col)
        if len(out)%256==0:budget.check(ln,col)
    while i<len(text):
        ch=text[i]
        if i%4096==0:budget.check(line,column)
        if ch in ' \t\v\f' or (ch=='\ufeff' and i==0):i+=1;column+=1;continue
        if ch in '\r\n':
            push('newline','\n',line,column)
            i+=2 if ch=='\r' and text[i:i+2]=='\r\n' else 1
            line+=1;column=1;continue
        if text.startswith('//',i):
            end=i+2
            while end<len(text) and text[end] not in '\r\n':
                if end%4096==0:budget.check(line,column+end-i)
                end+=1
            column+=end-i;i=end;continue
        if ch in ('"',"'"):
            quote=ch;start_line,start_column=line,column;value=[];i+=1;column+=1
            while i<len(text) and text[i]!=quote:
                if i%4096==0:budget.check(line,column)
                if text[i] in '\r\n':raise JassParseError('字符串中有未转义换行',line,column)
                if text[i]=='\\':
                    i+=1;column+=1
                    if i>=len(text) or text[i] not in _ESCAPES:raise JassParseError('不支持或截断的字符串转义',line,column)
                    value.append(_ESCAPES[text[i]])
                else:value.append(text[i])
                i+=1;column+=1
            if i>=len(text):raise JassParseError('字符串或对象 ID 未闭合',start_line,start_column)
            i+=1;column+=1;value=''.join(value)
            if quote=="'" and len(value.encode('utf8'))!=4:raise JassParseError('对象 ID 必须是四字节',start_line,start_column)
            push('string' if quote=='"' else 'rawcode',value,start_line,start_column);continue
        match=_NUMBER.match(text,i) or _NAME.match(text,i)
        if match:
            value=match[0];push('number' if _NUMBER.fullmatch(value) else 'name',value,line,column)
            i+=len(value);column+=len(value);continue
        operator=text[i:i+2] if text[i:i+2] in ('==','!=','<=','>=') else ch
        if operator not in ('==','!=','<=','>=','+','-','*','/','%','<','>','=','(',')','[',']',','):
            raise JassParseError(f'不支持的脚本字符 {ch!r}',line,column)
        push('symbol',operator,line,column);i+=len(operator);column+=len(operator)
    push('eof','',line,column)
    return tuple(out)


class _Parser:
    precedence={'or':1,'and':2,'==':3,'!=':3,'<':3,'>':3,'<=':3,'>=':3,'+':4,'-':4,'*':5,'/':5,'%':5}

    def __init__(self,text,cancelled):
        self.budget=_Budget(cancelled);self.tokens=_tokens(text,self.budget);self.pos=0;self.text=text

    @property
    def token(self):return self.tokens[self.pos]

    def error(self,message):raise JassParseError(message,self.token.line,self.token.column)

    def take(self,value=None):
        token=self.token
        if value is not None and (token.value!=value or token.kind not in ('name','symbol')):
            self.error(f'期望 {value!r}，实际为 {token.value!r}')
        if token.kind!='eof':self.pos+=1
        if self.pos%256==0:self.budget.check(token.line,token.column)
        return token

    def name(self):
        if self.token.kind!='name':self.error('期望标识符')
        return self.take().value

    def skip_lines(self):
        while self.token.kind=='newline':self.take()

    def end_line(self):
        if self.token.kind=='eof':return
        if self.token.kind!='newline':self.error('语句结束前存在多余内容')
        self.skip_lines()

    def expr(self,minimum=0):
        token=self.token
        with self.budget.nested(token.line):
            self.take()
            if token.kind in ('string','rawcode','number'):left=self.expression(token.kind,token.value,(),token)
            elif token.value in ('not','-','+'):
                left=self.expression('unary',token.value,(self.expr(6),),token)
            elif token.value=='(':
                left=self.expr();self.take(')')
            elif token.value=='function':left=self.expression('function_ref',self.name(),(),token)
            elif token.value in ('true','false'):left=self.expression('bool',token.value=='true',(),token)
            elif token.value=='null':left=self.expression('null',None,(),token)
            elif token.kind=='name':left=self.expression('variable',token.value,(),token)
            else:raise JassParseError('期望表达式',token.line,token.column)
            while True:
                if self.token.kind=='symbol' and self.token.value=='(':
                    if left.kind!='variable':self.error('不支持间接函数调用语法')
                    self.take();args=[]
                    if self.token.value!=')':
                        args.append(self.expr())
                        while self.token.value==',':self.take();args.append(self.expr())
                    self.take(')');left=self.expression('call',left.value,tuple(args),token);continue
                if self.token.kind=='symbol' and self.token.value=='[':
                    self.take();index=self.expr();self.take(']');left=self.expression('index','',(left,index),token);continue
                operator=self.token;level=self.precedence.get(operator.value,-1) if operator.kind in ('name','symbol') else -1
                if level<minimum:break
                self.take();right=self.expr(level+1);left=self.expression('binary',operator.value,(left,right),operator)
            return left

    def expression(self,kind,value,args,token):
        self.budget.node(token.line);return Expr(kind,value,args,token.line,token.column)

    def declaration(self,kind,constant=False):
        token=self.token;typ=self.name();array=False
        if self.token.value=='array':self.take();array=True
        name=self.name();exprs=()
        if self.token.value=='=':self.take();exprs=(self.expr(),)
        self.end_line();self.budget.node(token.line)
        return Stmt(kind,token.line,exprs,name=name,type_name=typ,array=array,constant=constant)

    def block(self,endings):
        result=[];self.skip_lines()
        while not (self.token.kind=='name' and self.token.value in endings):
            if self.token.kind=='eof':self.error('函数或控制块未闭合')
            result.append(self.statement())
        return tuple(result)

    def conditional(self):
        with self.budget.nested(self.token.line):
            return self._conditional()

    def _conditional(self):
        token=self.take();condition=self.expr();self.take('then');self.end_line()
        body=self.block({'elseif','else','endif'});other=()
        if self.token.value=='elseif':other=(self.conditional(),)
        else:
            if self.token.value=='else':self.take();self.end_line();other=self.block({'endif'})
            self.take('endif');self.end_line()
        return Stmt('if',token.line,(condition,),body,other)

    def statement(self):
        token=self.token
        if token.kind!='name':self.error('期望语句关键字')
        with self.budget.nested(token.line):
            self.budget.node(token.line)
            if token.value=='if':return self.conditional()
            self.take()
            if token.value=='loop':
                self.end_line();body=self.block({'endloop'});self.take('endloop');self.end_line()
                return Stmt('loop',token.line,body=body)
            if token.value=='local':return self.declaration('local')
            if token.value=='debug':return Stmt('debug',token.line,body=(self.statement(),))
            if token.value=='call':
                value=self.expr()
                if value.kind!='call':self.error('call 后必须为函数调用')
                result=Stmt('call',token.line,(value,))
            elif token.value=='set':
                left=self.expr()
                if left.kind not in ('variable','index'):self.error('赋值目标不是变量或数组')
                self.take('=');result=Stmt('set',token.line,(left,self.expr()))
            elif token.value in ('return','exitwhen'):
                values=() if self.token.kind in ('newline','eof') else (self.expr(),)
                if token.value=='exitwhen' and not values:self.error('exitwhen 缺少条件')
                result=Stmt(token.value,token.line,values)
            else:raise JassParseError(f'不支持的语句 {token.value!r}',token.line,token.column)
            self.end_line();return result

    def function(self,native=False,constant=False):
        start=self.take('native' if native else 'function');name=self.name();self.take('takes');params=[]
        if self.token.value=='nothing':self.take()
        else:
            params.append((self.name(),self.name()))
            while self.token.value==',':self.take();params.append((self.name(),self.name()))
        self.take('returns');returns=self.name();self.end_line()
        if native:return JassFunction(name,tuple(params),returns,(),start.line,start.line,constant)
        body=self.block({'endfunction'});end=self.take('endfunction');self.end_line()
        return JassFunction(name,tuple(params),returns,body,start.line,end.line,constant)

    def parse(self):
        functions={};natives={};globals_=[];types=[];self.skip_lines()
        while self.token.kind!='eof':
            constant=False
            if self.token.value=='constant':self.take();constant=True
            if self.token.value in ('function','native'):
                native=self.token.value=='native';function=self.function(native,constant)
                if function.name in functions or function.name in natives:self.error('重复函数定义 '+function.name)
                (natives if native else functions)[function.name]=function
                if len(functions)+len(natives)>MAX_FUNCTIONS:self.error('函数数量超过上限')
            elif self.token.value=='globals' and not constant:
                self.take();self.end_line()
                while self.token.value!='endglobals':
                    if self.token.kind=='eof':self.error('globals 未闭合')
                    is_constant=False
                    if self.token.value=='constant':self.take();is_constant=True
                    globals_.append(self.declaration('global',is_constant))
                self.take('endglobals');self.end_line()
            elif self.token.value=='type' and not constant:
                self.take();name=self.name();self.take('extends');types.append((name,self.name()));self.end_line()
            else:self.error('不支持的脚本顶层声明')
        self.budget.check(self.token.line,self.token.column)
        return JassProgram(MappingProxyType(functions),tuple(globals_),MappingProxyType(natives),tuple(types),self.text)


def parse_jass(text:str,cancelled=lambda:False)->JassProgram:
    """Return immutable syntax, or a source-positioned explicit failure."""
    if not isinstance(text,str):raise TypeError('脚本文本必须是 str')
    return _Parser(text,cancelled).parse()
