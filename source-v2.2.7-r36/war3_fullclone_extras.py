"""R35 orchestration; every old clone and infernal transaction stays intact."""
import math,random,threading,time

def formation_points(kind,count,gap,x,y):
    if kind not in ('square','ring','line','scatter') or type(count) is not int or not 1<=count<=100:raise ValueError('阵型或复制数量无效')
    gap=float(gap)
    if not math.isfinite(gap) or not 32<=gap<=2048:raise ValueError('阵型间距必须在32至2048之间')
    if not all(math.isfinite(v) and abs(v)<=1000000 for v in (x,y)):raise ValueError('阵型中心坐标无效')
    if count==1:return [(x,y)]
    if kind=='line':points=[(x+(i-(count-1)/2)*gap,y) for i in range(count)]
    elif kind=='ring':
        r=0 if count==1 else gap/(2*math.sin(math.pi/count))
        points=[(x+r*math.cos(2*math.pi*i/count),y+r*math.sin(2*math.pi*i/count)) for i in range(count)]
    else:
        side=math.ceil(math.sqrt(count));cells=[(x+(i%side-(side-1)/2)*gap,y+(i//side-(math.ceil(count/side)-1)/2)*gap) for i in range(count)]
        if kind=='scatter':
            # Seeded jitter has a bounded minimum separation, unlike retrying
            # random points. It is stable enough to preview and test.
            rng=random.Random(count);points=[(a+rng.uniform(-.15,.15)*gap,b+rng.uniform(-.15,.15)*gap) for a,b in cells]
        else:points=cells
    if any(abs(v)>1000000 for p in points for v in p):raise ValueError('阵型超出允许坐标范围')
    return points

def clone_formation(trainer,count,kind,gap,*,owner_mode='author',player=0):
    if type(count) is not int or not 1<=count<=100 or owner_mode not in ('author','self','selected','player'):raise ValueError('复制数量或归属无效')
    engine=trainer._engine_instance_24268()
    with engine.session.lock:
        sources=trainer._capture_clone_sources_24268()
        if len(sources)!=1:raise ValueError('新阵型请只选择一个源单位；多选单位可使用“原排列”')
        points=formation_points(kind,count,gap,*trainer.query_mouse_world_position())
        owner=trainer.fullclone_owner()
        if not owner:raise ValueError('请先选中单位')
        destination=owner['a'] if owner_mode=='selected' else player
        handles=[];issues=[]
        for x,y in points:
            try:
                args=dict(spawn_x_bits=trainer._float_bits(x),spawn_y_bits=trainer._float_bits(y))
                if owner_mode=='player':r=engine.fullclone_clone_state(sources,destination,**args)
                else:r=trainer.clone_batch_24268(keep=True,preserve_owner=owner_mode in ('author','selected'),copy_abilities=True,copy_items=True,spawn=True,expected_sources=sources,**args)
                handles.extend(row['clone'] for row in r['rows']);issues.extend(r.get('ability_issues',()))
            except Exception as exc:raise RuntimeError(f'阵型复制已确认{len(handles)}个，已停止；当前一次可能部分生效，不自动补足：{exc}') from exc
        return dict(count=len(handles),handles=handles,ability_issues=issues)

def restore_frozen(engine,owner,record):
    if engine.session.epoch!=record['epoch']:raise ValueError('地图已变化，不能恢复旧地图单位')
    changed=skipped=0
    for key,row in list(record['pending'].items()):
        r=engine.fullclone_extra(2,rows=(dict(row,paused=1,desired=row['paused'],status=0),),expected_epoch=record['epoch'])
        if r['rows'][0]['status']==1:changed+=r['changed']
        else:skipped+=1
        record['pending'].pop(key)
    engine.session.cache.get('fullclone_frozen',{}).pop(owner,None)
    return dict(restored=True,changed=changed,skipped=skipped)

def toggle_frozen(trainer,scope='all',buildings=False):
    if scope not in ('all','heroes','nonheroes') or type(buildings) is not bool:raise ValueError('冻结范围无效')
    engine=trainer._engine_instance_24268()
    with engine.session.lock:
        owner=trainer.fullclone_owner()
        if not owner:raise ValueError('请先选择该玩家的一个单位')
        key=owner['owner'];records=engine.session.cache.setdefault('fullclone_frozen',{})
        if key in records:return restore_frozen(engine,key,records[key])
        snapshot=engine.fullclone_extra(1,scope={'all':0,'heroes':1,'nonheroes':2}[scope],flag=int(buildings))
        if snapshot['owner']!=key:raise ValueError('选中玩家已变化，未冻结')
        pending={};record=dict(epoch=engine.session.epoch,pending=pending);records[key]=record
        changed=0
        try:
            for row in snapshot['rows']:
                if row['paused']:continue  # Map-paused units are never thawed by us.
                clean=dict(row,status=0);pending[row['full']]=clean
                r=engine.fullclone_extra(2,rows=(dict(clean,desired=1),),expected_epoch=record['epoch'])
                if r['rows'][0]['status']!=1:pending.pop(row['full'])
                else:changed+=r['changed']
        except Exception as exc:raise RuntimeError(f'已冻结{changed}个单位，已停止；原状态记录保留，再按按钮恢复：{exc}') from exc
        if not pending:records.pop(key,None)
        return dict(restored=False,changed=changed,skipped=0)

def restore_all_frozen(trainer):
    engine=trainer._engine_instance_24268();changed=skipped=0
    with engine.session.lock:
        records=engine.session.cache.get('fullclone_frozen',{})
        for owner,rec in list(records.items()):
            r=restore_frozen(engine,owner,rec);changed+=r['changed'];skipped+=r['skipped']
    return dict(changed=changed,skipped=skipped)

def point_spell(trainer,code):
    from war3_fullclone_extra_protocol import SPELLS
    if code not in SPELLS:raise ValueError('请选择固定技能')
    if code=='AUin':return trainer.fullclone_infernal() # Original verified path.
    engine=trainer._engine_instance_24268();raw=int.from_bytes(code.encode(),'big')
    with engine.session.lock:
        x,y=trainer.query_mouse_world_position();epoch=engine.session.epoch
        state=engine.fullclone_extra(4,rawcode=raw,x=x,y=y,expected_epoch=epoch)
    def release():
        with engine.session.lock:
            if engine.session.closed or engine.session.epoch!=epoch:return
            engine.fullclone_extra(6,rawcode=raw,target=state['target'],expected_full=state['full'],owner=state['owner'],expected_epoch=epoch)
    time.sleep(.15)
    try:
        engine.fullclone_extra(5,rawcode=raw,x=x,y=y,target=state['target'],expected_full=state['full'],owner=state['owner'],expected_epoch=epoch)
    except Exception:
        try:release()
        except Exception as exc:engine.session.cache['fullclone_point_cleanup_error']=str(exc)
        raise
    def cleanup():
        time.sleep(20)
        try:release()
        except Exception as exc:engine.session.cache['fullclone_point_cleanup_error']=str(exc)
    threading.Thread(target=cleanup,daemon=True,name='fullclone-point-cleanup').start()
    return f'已接受鼠标位置{SPELLS[code][0]}（{code}）施法命令，归自己'
