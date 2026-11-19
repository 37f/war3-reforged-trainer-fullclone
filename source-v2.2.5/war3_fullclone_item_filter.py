"""Filter already captured item identities, without reading more game fields."""
import re


def parse_filter(mode,text):
    if mode not in ('all','include','exclude'):raise ValueError('物品聚集筛选方式无效')
    if mode=='all':return frozenset()
    if not isinstance(text,str) or len(text)>128:raise ValueError('物品ID列表最多128个字符')
    parts=[p for p in re.split(r'[\s,，;；]+',text.strip()) if p]
    if not parts:raise ValueError('请填写至少一个四字符物品ID')
    if any(not re.fullmatch(r'[!-~]{4}',p) for p in parts):raise ValueError('物品ID必须是区分大小写的四个ASCII字符，多个ID用空格、逗号或分号分隔')
    return frozenset(int.from_bytes(p.encode('ascii'),'big') for p in parts)


def filter_items(items,mode,codes):
    if mode=='all':return list(items)
    return [row for row in items if (row['rawcode'] in codes)==(mode=='include')]
