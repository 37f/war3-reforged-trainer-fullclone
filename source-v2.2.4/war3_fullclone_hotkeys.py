"""Additional chords without changing the author's ordinary hotkey manager."""
from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class Chord:
    name:str
    label:str
    modifiers:int
    virtual_key:int
    hold_keys:tuple=()
    poll_on_conflict:bool=True


def specs(base):
    return tuple(base)+(
        Chord('give_owner','Ctrl+I+U  把单位给指定玩家',2,ord('U'),(ord('I'),)),
        Chord('toggle_owner_control','Ctrl+I+O  控制/恢复选中玩家（不改变阵营）',2,ord('O'),(ord('I'),)),
        Chord('join_team','Ctrl+F1  把选中玩家加入队伍',2,0x70),
        Chord('replace_unit','Ctrl+U+8  替换单位',2,ord('8'),(ord('U'),)),
        Chord('revive_owner_heroes','Ctrl+F+H  复活选中玩家的阵亡英雄',2,ord('H'),(ord('F'),)),
        Chord('fill_life_mana','Ctrl+空格  单位生命魔法全满',2,0x20),
        Chord('gold_mine','Alt+空格  设置金矿黄金',1,0x20),
        Chord('infernal','Ctrl+F2  释放地狱火（AUin）',2,0x71),
        Chord('gather_ground_items','Alt+F2  聚集全图地面物品',1,0x71),
    )


def manager_type(base,api,is_down):
    class FullCloneHotkeys(base):
        def start(self,spec_list,on_trigger):
            stop=threading.Event();chords=tuple(s for s in spec_list if getattr(s,'hold_keys',()))
            ordinary=tuple(s for s in spec_list if not getattr(s,'hold_keys',()))
            down=lambda k:bool(int(api.GetAsyncKeyState(k))&0x8000)
            def emit(name):
                # Suppress the old single-key action while a new chord owns it.
                if name=='preset_tech' and down(ord('I')):return
                if name=='ability_level' and down(ord('F')):return
                prefix={'take_control':('I',('U','O')),'item_charges':('F',('H',))}.get(name)
                if prefix:
                    def delayed():
                        key,children=prefix;used=False
                        while down(ord(key)) and not stop.wait(.02):used|=any(down(ord(c)) for c in children)
                        if not used and not stop.is_set():on_trigger(name)
                    threading.Thread(target=delayed,daemon=True).start()
                else:on_trigger(name)
            result=super().start(ordinary,emit)
            self._fc_stop=stop
            def poll():
                pressed={s.name:False for s in chords}
                while not stop.wait(.02):
                    for s in chords:
                        active=is_down(s) and all(down(k) for k in s.hold_keys)
                        if active and not pressed[s.name]:
                            try:on_trigger(s.name)
                            except Exception:pass
                        pressed[s.name]=active
            self._fc_chords=tuple(s.name for s in chords)
            self._fc_thread=threading.Thread(target=poll,daemon=True,name='fullclone-chords');self._fc_thread.start()
            return result

        @property
        def fallback_names(self):
            return super().fallback_names+getattr(self,'_fc_chords',())

        def stop(self):
            self._fc_chords=()
            if hasattr(self,'_fc_stop'):self._fc_stop.set()
            super().stop()
            thread=getattr(self,'_fc_thread',None)
            if thread and thread is not threading.current_thread():thread.join(1)
    return FullCloneHotkeys
