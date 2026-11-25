"""Three local supply presets. Never executes text as script or overwrites items."""
import json,os,re,tempfile
from pathlib import Path

def path():return Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')/'War3Trainer/FullClone/supply-packs.json'

def parse(text):
    if not isinstance(text,str) or len(text)>2048:raise ValueError('补给清单最多2048字符')
    result=[]
    for line in text.splitlines():
        if not line.strip():continue
        p=line.split()
        if len(p) not in (2,3) or not re.fullmatch('[!-~]{4}',p[0]) or any(not re.fullmatch('[0-9]+',v) or len(v)>10 for v in p[1:]):raise ValueError('每行填写：四字符物品ID 数量 [使用次数]；省略次数保留默认')
        n=int(p[1]);charges=int(p[2]) if len(p)==3 else -1
        if not 1<=n<=32 or not -1<=charges<=1000000000 or len(result)+n>32:raise ValueError('每包最多32个物品；数量1至32，使用次数0至10亿')
        result.extend(dict(rawcode=int.from_bytes(p[0].encode('ascii'),'big'),desired=charges+1) for _ in range(n))
    if not result:raise ValueError('补给包不能为空')
    return result

def load():
    try:
        raw=json.loads(path().read_text('utf8'));out={}
        for i in range(1,4):
            name=raw.get(f'supply_name_{i}');text=raw.get(f'supply_text_{i}')
            if isinstance(name,str) and 1<=len(name)<=24 and isinstance(text,str) and len(text)<=2048:
                if text.strip():parse(text)
                out.update({f'supply_name_{i}':name,f'supply_text_{i}':text})
        return out
    except (OSError,ValueError,TypeError,AttributeError):return {}

def save(options):
    data={}
    for i in range(1,4):
        name=options[f'supply_name_{i}'];text=options[f'supply_text_{i}']
        if not isinstance(name,str) or not 1<=len(name.strip())<=24:raise ValueError('补给包名称请输入1至24个字符')
        if text.strip():parse(text)
        data.update({f'supply_name_{i}':name.strip(),f'supply_text_{i}':text})
    p=path();p.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='supplies-',suffix='.tmp',dir=p.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(temp,p)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return '已保存三组补给包，下次打开仍可使用'

def deliver(trainer,text,target):
    rows=parse(text)
    if target not in ('hero','ground'):raise ValueError('补给投放方式无效')
    engine=trainer._engine_instance_24268()
    with engine.session.lock:
        x,y=trainer.query_mouse_world_position() if target=='ground' else (0.,0.)
        return engine.fullclone_extra(3,rows=rows,flag=int(target=='ground'),x=x,y=y,expected_epoch=engine.session.epoch)
