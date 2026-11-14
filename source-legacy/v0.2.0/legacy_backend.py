"""Exact-build Legacy backend. No old Reforged address/ABI is imported.

The x86 host schedules requests on the selected game's own message thread.
All setters are explicit actions; connecting and snapshot() are read-only.
"""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import mmap
import os
import queue
import secrets
import subprocess
import sys
import threading
import time

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
TARGET=r'E:\Games\Warcraft III (Legacy)\Warcraft III.exe'
MAGIC=0x4c313239
class PlayerRow(C.Structure):
    _fields_=[('slot',C.c_uint32),('handle',C.c_uint32),('state',C.c_uint32),('gold',C.c_int32),('lumber',C.c_int32),('food_used',C.c_int32),('food_cap',C.c_int32)]
class UnitRow(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('handle','type','owner','hero')]+[(n,C.c_int32) for n in ('level','strength','agility','intelligence')]+[(n,C.c_float) for n in ('hp','max_hp','mp','max_mp')]
class AbilityRow(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('rawcode','level','flags')]
class ItemRow(C.Structure):
    _fields_=[('handle',C.c_uint32),('type',C.c_uint32),('charges',C.c_int32),('life',C.c_float),('invulnerable',C.c_uint32),('pawnable',C.c_uint32)]
class UnitSpec(C.Structure):
    _fields_=[('base',UnitRow)]+[(n,C.c_float) for n in ('x','y','facing')]+[(n,C.c_uint32) for n in ('xp','points','paused','xp_paused','ability_count','item_nodes')]+[('abilities',AbilityRow*128),('items',ItemRow*6)]
class Packet(C.Structure):
    _pack_=4
    _fields_=[(n,C.c_uint32) for n in ('magic','version','bytes','pid','nonce','seq','ack','status','error','action','target','kind')]+[(n,C.c_int32) for n in ('a','b','c','delta')]+[(n,C.c_uint32) for n in ('expected_world','expected_player','expected_count')]+[(n,C.c_uint32*64) for n in ('expected_units','expected_types','expected_owners')]+[(n,C.c_uint32) for n in ('world','module_base','local_player','player_count','unit_count','applied','stage')]+[('players',PlayerRow*28),('units',UnitRow*64),('detail',UnitSpec),('created_count',C.c_uint32),('created',C.c_uint32*200),('warnings',C.c_uint32)]

K=C.WinDLL('kernel32',use_last_error=True);U=C.WinDLL('user32',use_last_error=True);PS=C.WinDLL('psapi',use_last_error=True)
K.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];K.OpenProcess.restype=W.HANDLE
K.CloseHandle.argtypes=[W.HANDLE];K.CloseHandle.restype=W.BOOL
K.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)];K.QueryFullProcessImageNameW.restype=W.BOOL
K.GetProcessTimes.argtypes=[W.HANDLE,C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME)];K.GetProcessTimes.restype=W.BOOL
PS.EnumProcesses.argtypes=[C.c_void_p,W.DWORD,C.POINTER(W.DWORD)];PS.EnumProcesses.restype=W.BOOL
U.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)];U.GetWindowThreadProcessId.restype=W.DWORD
U.IsWindowVisible.argtypes=[W.HWND];U.IsWindowVisible.restype=W.BOOL
U.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)];U.GetClientRect.restype=W.BOOL
U.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];U.PostMessageW.restype=W.BOOL
U.RegisterWindowMessageW.argtypes=[W.LPCWSTR];U.RegisterWindowMessageW.restype=W.UINT
ENUM=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
U.EnumWindows.argtypes=[ENUM,W.LPARAM];U.EnumWindows.restype=W.BOOL

def process_identity(pid):
    h=K.OpenProcess(0x1000,False,pid)
    if not h:raise RuntimeError('无法读取游戏进程；请以与游戏相同的权限运行修改器。')
    try:
        text=C.create_unicode_buffer(32768);size=W.DWORD(len(text))
        if not K.QueryFullProcessImageNameW(h,0,text,C.byref(size)):raise C.WinError(C.get_last_error())
        created,exited,kernel,user=(W.FILETIME() for _ in range(4))
        if not K.GetProcessTimes(h,C.byref(created),C.byref(exited),C.byref(kernel),C.byref(user)):raise C.WinError(C.get_last_error())
        return os.path.normcase(os.path.abspath(text.value)),(created.dwHighDateTime<<32)|created.dwLowDateTime
    finally:K.CloseHandle(h)

def find_target(path):
    values=(W.DWORD*8192)();size=W.DWORD();wanted=os.path.normcase(os.path.abspath(path));matches=[]
    if not PS.EnumProcesses(values,C.sizeof(values),C.byref(size)):raise C.WinError(C.get_last_error())
    for pid in values[:size.value//4]:
        if not pid:continue
        try:
            identity=process_identity(pid)
            if identity[0]==wanted:matches.append((pid,identity))
        except (OSError,RuntimeError):continue
    if len(matches)!=1:raise RuntimeError('请先从指定 Legacy 目录启动游戏并进入地图；同一路径只能运行一个游戏进程。')
    pid,identity=matches[0];windows=[]
    @ENUM
    def visitor(hwnd,unused):
        owner=W.DWORD();U.GetWindowThreadProcessId(hwnd,C.byref(owner))
        if owner.value==pid and U.IsWindowVisible(hwnd):
            rect=W.RECT()
            if U.GetClientRect(hwnd,C.byref(rect)):windows.append(((rect.right-rect.left)*(rect.bottom-rect.top),int(hwnd)))
        return True
    U.EnumWindows(visitor,0)
    if not windows:raise RuntimeError('没有找到 Legacy 游戏窗口。')
    return pid,max(windows)[1],identity

ERRORS={103:'当前游戏接口与已核对的1.29.2版本不同。',104:'地图或脚本环境尚未就绪，请进入地图并选中单位后重新读取。',105:'地图、目标玩家或选中单位已经变化，请重新读取后再操作。',106:'参数超出允许范围。',108:'此前调用发生异常，本次连接已停用，请断开后核对游戏状态。',109:'游戏接口读回值未完全符合设置值，请先读取核对。',110:'该普通玩家槽位未在当前地图启用。',111:'选择单位超过64个，无法核对完整列表。'}

ERRORS.update({120:'单位、技能或物品快照超出本版支持范围。',121:'未能创建目标单位，请核对单位ID是否存在。',122:'创建或替换期间单位身份发生变化，已停止。',123:'部分技能未能复制到目标单位。',124:'背包或物品读回不符，已停止；请核对原单位与新单位。',125:'英雄或生命魔法状态未能完整复制。',126:'本版不复制或替换已死亡单位。'})

class LegacyTrainer:
    def __init__(self,target_path=TARGET):
        self.target_path=str(target_path);self.pid=0;self.hwnd=0;self.identity=None
        self.host=None;self.mapping=None;self.last=None;self.sequence=0;self.poisoned=False;self.needs_read=False;self.lock=threading.RLock()
        self.profile=json.loads((ROOT/'profile.json').read_text('utf8'));self.native_dir=ROOT/'legacy32'
        if C.sizeof(Packet)!=7300:raise RuntimeError('修改器协议结构大小不符。')
    def connect(self):
        with self.lock:
            self.close()
            if hashlib.sha256(Path(self.target_path).read_bytes()).hexdigest()!=self.profile['sha256']:raise RuntimeError('游戏EXE不是已适配的1.29.2.9231；拒绝使用旧地址。')
            self.pid,self.hwnd,self.identity=find_target(self.target_path)
            self.nonce=secrets.randbits(32) or 1
            self.mapping=mmap.mmap(-1,C.sizeof(Packet),tagname=f'Local\\War3Legacy129-V2-{self.pid}-{self.nonce:08x}')
            self.message=U.RegisterWindowMessageW('War3Legacy129.BasicTrainer.v2')
            # Keep x86 files in their own directory. A frozen x64 Python UCRT
            # beside a 32-bit EXE would otherwise be picked up by its loader.
            self.host=subprocess.Popen([str(self.native_dir/'legacy_host32_v2.exe'),str(self.pid),str(self.hwnd)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
            startup=queue.Queue();stream=self.host.stdout
            threading.Thread(target=lambda:startup.put(stream.readline()),daemon=True).start()
            try:line=startup.get(timeout=5).decode('ascii','replace').strip()
            except queue.Empty:self.close();raise RuntimeError('32位连接助手启动超时；本次没有发送游戏操作。')
            if not line.startswith('READY '):
                code=self.host.poll();self.close();raise RuntimeError(f'32位连接助手未启动（返回 {code}），请确认没有另一份Legacy修改器占用连接。')
            try:return self.snapshot()
            except Exception:self.close();raise
    def _request(self,action=0,**args):
        with self.lock:
            if not self.mapping or not self.host or self.host.poll() is not None:raise RuntimeError('尚未连接Legacy游戏。')
            if self.poisoned:raise RuntimeError('上次请求状态不确定，请先断开并核对游戏；本次不会重放操作。')
            if action and self.needs_read:raise RuntimeError('上次操作可能部分生效，请先按F5或点击读取核对，暂不继续修改。')
            if process_identity(self.pid)!=self.identity:raise RuntimeError('游戏进程已更换，请重新连接。')
            p=Packet();p.magic=MAGIC;p.version=2;p.bytes=C.sizeof(p);p.pid=self.pid;p.nonce=self.nonce
            self.sequence=(self.sequence+1)&0x7fffffff or 1;p.seq=self.sequence;p.status=1;p.action=action
            for key,value in args.items():setattr(p,key,value)
            if action:
                if self.last is None:raise RuntimeError('请先读取当前地图。')
                p.expected_world=self.last.world
                if p.target<self.last.player_count:p.expected_player=self.last.players[p.target].handle
                p.expected_count=self.last.unit_count
                for i in range(p.expected_count):
                    unit=self.last.units[i];p.expected_units[i]=unit.handle;p.expected_types[i]=unit.type;p.expected_owners[i]=unit.owner
            self.mapping.seek(0);self.mapping.write(bytes(p))
            if not U.PostMessageW(self.hwnd,self.message,self.nonce,0):raise C.WinError(C.get_last_error())
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                result=Packet.from_buffer_copy(self.mapping[:])
                if result.ack==p.seq:
                    if result.magic!=MAGIC or result.nonce!=self.nonce or result.pid!=self.pid or result.bytes!=C.sizeof(p):self.poisoned=True;raise RuntimeError('连接响应身份不符。')
                    if result.status!=3 or result.error:
                        if result.error>=0x80000000:self.poisoned=True
                        message=ERRORS.get(result.error,f'32位接口异常 0x{result.error:08X}。')
                        if action and result.applied:
                            self.needs_read=True
                            message+=f' 已尝试操作 {result.applied} 个目标，部分修改可能已生效。不要重复执行，请先按F5读取核对。'
                        exc=RuntimeError(message)
                        exc.stage=result.stage;exc.world=result.world;exc.local_player=result.local_player;exc.player_count=result.player_count
                        self._log_error(result)
                        raise exc
                    if not 0<result.player_count<=28 or result.unit_count>64 or result.created_count>200 or result.detail.ability_count>128:self.poisoned=True;raise RuntimeError('游戏列表数量无效。')
                    self.last=result
                    if not action:self.needs_read=False
                    return self._data(result)
                if self.host.poll() is not None:raise RuntimeError('32位连接助手已退出。')
                time.sleep(.01)
            self.poisoned=True;raise RuntimeError('游戏未在5秒内确认请求；不自动重试，请先核对游戏状态后重新连接。')
    def _log_error(self,result):
        try:
            folder=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'War3LegacyTrainer'
            folder.mkdir(parents=True,exist_ok=True)
            report={k:int(getattr(result,k)) for k in ('pid','seq','action','error','stage','applied','world','player_count','unit_count')}
            report.update(profile=self.profile['version'],time=time.strftime('%Y-%m-%d %H:%M:%S'))
            (folder/'last-error.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        except OSError:pass
    def _data(self,p):
        rows=[]
        for r in p.units[:p.unit_count]:
            rows.append(dict(handle=r.handle,type_id=r.type.to_bytes(4,'big').decode('ascii','replace'),owner=r.owner,hero=bool(r.hero),hp=round(r.hp,2),max_hp=round(r.max_hp,2),mp=round(r.mp,2),max_mp=round(r.max_mp,2),level=r.level,str=r.strength,agi=r.agility,int=r.intelligence))
        result=dict(pid=self.pid,profile='Legacy '+self.profile['version'],local_player=p.local_player,world=p.world,applied=p.applied,
            players=[dict(slot=r.slot,state=r.state,gold=r.gold,lumber=r.lumber,food_used=r.food_used,food_cap=r.food_cap) for r in p.players[:p.player_count]],units=rows,
            old_map_neutral_aliases=p.player_count==24)
        result['created']=list(p.created[:p.created_count]);result['warnings']=p.warnings
        if p.detail.base.handle:
            s=p.detail
            result['detail']=dict(handle=s.base.handle,type_id=s.base.type.to_bytes(4,'big').decode('ascii','replace'),x=s.x,y=s.y,facing=s.facing,xp=s.xp,points=s.points,paused=bool(s.paused),xp_paused=bool(s.xp_paused),item_nodes=s.item_nodes,
                abilities=[dict(id=a.rawcode.to_bytes(4,'big').decode('ascii','replace'),level=a.level,flags=a.flags) for a in s.abilities[:s.ability_count]],
                items=[dict(slot=i,handle=a.handle,id=a.type.to_bytes(4,'big').decode('ascii','replace'),charges=a.charges,life=a.life,invulnerable=bool(a.invulnerable),pawnable=bool(a.pawnable)) for i,a in enumerate(s.items) if a.handle])
        if p.action in (6,7):
            result['message']=f'已复制 {p.applied} 个单位。' if p.action==6 else f'已替换 {p.applied} 个单位。'
            if p.warnings&1:result['message']+=' 最大生命/魔法按本版整数接口取整。'
            if p.warnings&2:result['message']+=' 目标不是英雄，英雄等级/经验/三围/技能点不适用。'
        return result
    @staticmethod
    def _integer(value,low,high):
        if type(value) is not int or not low<=value<=high:raise ValueError(f'请输入 {low}～{high} 之间的整数。')
        return value
    def snapshot(self):return self._request()
    def set_resource(self,player,kind,value):
        kinds=dict(gold=1,lumber=2,food_used=5,food_cap=4)
        if kind not in kinds:raise ValueError('资源类型无效。')
        return self._request(1,target=self._integer(player,0,27),kind=kinds[kind],a=self._integer(value,0,100000000))
    def add_resources(self,player,amount):return self._request(2,target=self._integer(player,0,27),a=self._integer(amount,0,100000000))
    def _selected_action(self,action,**args):
        # Hotkeys mean the current selection, not the previous UI snapshot.
        # Acquire a fresh read, then require that exact selection at execution.
        with self.lock:
            if self.needs_read:raise RuntimeError('上次操作可能部分生效，请先按F5或点击读取核对，暂不继续修改。')
            self._request()
            return self._request(action,**args)
    def fill_selected(self):return self._selected_action(3)
    def set_hero_level(self,value,delta=False):
        if type(delta) is not bool:raise ValueError('等级模式无效。')
        return self._selected_action(4,a=self._integer(value,1,1000),delta=int(delta))
    def set_hero_attributes(self,strength,agility,intelligence,delta=False):
        if type(delta) is not bool:raise ValueError('属性模式无效。')
        return self._selected_action(5,a=self._integer(strength,0,100000),b=self._integer(agility,0,100000),c=self._integer(intelligence,0,100000),delta=int(delta))
    def clone_selected(self,count=1,owner_mode='self',player=0):
        modes=dict(self=0,selected=1,player=2)
        if owner_mode not in modes:raise ValueError('复制归属无效。')
        return self._selected_action(6,a=self._integer(count,1,200),kind=modes[owner_mode],target=self._integer(player,0,27))
    def replace_selected(self,rawcode='zhyd'):
        if type(rawcode) is not str or len(rawcode)!=4 or not rawcode.isascii() or not rawcode.isalnum():raise ValueError('请输入4位ASCII字母或数字单位ID。')
        return self._selected_action(7,b=int.from_bytes(rawcode.encode('ascii'),'big'))
    def clone_preview(self):return self._selected_action(8)
    def close(self):
        with self.lock:
            if self.host:
                try:
                    if self.host.poll() is None:
                        self.host.stdin.write(b'Q');self.host.stdin.flush();self.host.wait(timeout=3)
                except (OSError,subprocess.TimeoutExpired):
                    if self.host.poll() is None:self.host.terminate();self.host.wait(timeout=3)
                finally:
                    for stream in (self.host.stdin,self.host.stdout,self.host.stderr):
                        if stream:stream.close()
                self.host=None
            if self.mapping:self.mapping.close();self.mapping=None
            self.last=None;self.pid=0;self.hwnd=0;self.identity=None;self.poisoned=False;self.needs_read=False
