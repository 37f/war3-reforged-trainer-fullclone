"""Independent white-tab UI for the narrowly scoped Legacy 1.29.2 trainer.

All backend calls run on one worker. Tk widgets and hotkey edges stay on the UI
thread; offline checks never import the backend or attach to a process.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk


TARGET = r'E:\Games\Warcraft III (Legacy)\Warcraft III.exe'
RESOURCE_LABELS = [('gold', '金币'), ('lumber', '木材'), ('food_used', '已用人口'), ('food_cap', '人口上限')]


class TrainerWindow:
    def __init__(self, root, *, offline=False, target_path=TARGET):
        self.root, self.offline, self.target_path = root, offline, target_path
        self.backend = None
        self.jobs, self.results = queue.Queue(), queue.Queue()
        self.data, self.pid, self.busy, self.closing = {}, 0, False, False
        self.selected_slot, self.held = None, set()
        self.buttons, self.connected_buttons = [], []
        self.status = tk.StringVar(value='离线界面检查，不连接游戏' if offline else '请先进入 Legacy 地图，再连接游戏。')
        self.identity = tk.StringVar(value='未连接 · 仅适配 Legacy 1.29.2')
        self.hotkeys = tk.BooleanVar(value=False)
        self.custom_level, self.custom_stats = tk.BooleanVar(), tk.BooleanVar()
        self.level = tk.StringVar(value='1')
        self.stats = [tk.StringVar(value='20') for _ in range(3)]
        self.resource_values = {key: tk.StringVar(value='0') for key, _ in RESOURCE_LABELS}
        self.add_amount = tk.StringVar(value='10000')
        self.owner_mode = tk.StringVar(value='self')
        self.owner_player = tk.StringVar()
        self.owner_choices = {}
        self.clone_count = tk.StringVar(value='10')
        self.replace_id = tk.StringVar(value='zhyd')
        self._make_window()
        self._make_hotkey_api()
        if not offline:
            threading.Thread(target=self._worker, name='Legacy trainer worker', daemon=True).start()
        root.after(60, self._drain_results)
        root.after(60, self._poll_hotkeys)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def _make_window(self):
        root = self.root
        root.title('魔兽争霸 III Legacy 1.29.2 修改器 v0.2.0-Test')
        root.geometry('980x740'); root.minsize(800, 620)
        style = ttk.Style(root)
        if 'vista' in style.theme_names(): style.theme_use('vista')
        root.columnconfigure(0, weight=1); root.rowconfigure(1, weight=1)
        top = ttk.Frame(root, padding=10); top.grid(row=0, column=0, sticky='ew')
        self.connect_button = self._button(top, '连接 Legacy 1.29.2', lambda: self._enqueue('connect', (), '连接'), connected=False)
        self.connect_button.pack(side='left')
        self._button(top, '读取／刷新（F5）', lambda: self._enqueue('snapshot', (), '读取')).pack(side='left', padx=8)
        ttk.Checkbutton(top, text='启用游戏内快捷键', variable=self.hotkeys).pack(side='left', padx=8)
        ttk.Label(top, textvariable=self.identity).pack(side='right')
        self.tabs = ttk.Notebook(root); self.tabs.grid(row=1, column=0, sticky='nsew', padx=10)
        resource_tab, unit_tab, clone_tab = (ttk.Frame(self.tabs, padding=12) for _ in range(3))
        self.tabs.add(resource_tab, text='玩家资源'); self.tabs.add(unit_tab, text='选中单位与英雄')
        self.tabs.add(clone_tab, text='复制与替换')
        self._make_resources(resource_tab); self._make_units(unit_tab); self._make_clone(clone_tab)
        bottom = ttk.Frame(root, padding=10); bottom.grid(row=2, column=0, sticky='ew')
        ttk.Label(bottom, text='快捷键仅在已连接的 Legacy 游戏位于前台时生效；默认关闭。').pack(anchor='w')
        ttk.Label(bottom, text='F5 读取　Ctrl+空格 生命魔法全满　Ctrl+Q 英雄等级　Alt+Q 永久三围　Ctrl+L 增加金币木材').pack(anchor='w', pady=(3, 6))
        ttk.Label(bottom, text='Ctrl+B 复制　Ctrl+A 复制给自己　Ctrl+N 大量复制　Ctrl+U+8 替换单位').pack(anchor='w', pady=(0, 6))
        ttk.Label(bottom, textvariable=self.status, wraplength=930, foreground='#174875').pack(anchor='w')
        self._set_busy(False)

    def _button(self, parent, text, command, *, connected=True):
        button = ttk.Button(parent, text=text, command=command)
        self.buttons.append(button)
        if connected: self.connected_buttons.append(button)
        return button

    def _table(self, parent, columns, widths, height):
        frame = ttk.Frame(parent); frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=[key for key, _ in columns], show='headings', height=height, selectmode='browse')
        for (key, label), width in zip(columns, widths):
            tree.heading(key, text=label); tree.column(key, width=width, minwidth=45, anchor='center')
        vertical = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew'); vertical.grid(row=0, column=1, sticky='ns'); horizontal.grid(row=1, column=0, sticky='ew')
        return frame, tree

    def _make_resources(self, tab):
        tab.columnconfigure(0, weight=1); tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text='选中下表玩家，再设置其资源；“本地玩家”仅标识游戏当前玩家。').grid(row=0, column=0, sticky='w', pady=(0, 8))
        frame, self.players = self._table(tab, [('slot', '玩家'), ('local', '本地玩家')] + RESOURCE_LABELS, [180, 100, 135, 135, 135, 135], 12)
        frame.grid(row=1, column=0, sticky='nsew')
        self.players.bind('<<TreeviewSelect>>', self._select_player)
        fields = ttk.LabelFrame(tab, text='设置选中玩家的资源', padding=10); fields.grid(row=2, column=0, sticky='ew', pady=10)
        for row, (key, label) in enumerate(RESOURCE_LABELS):
            ttk.Label(fields, text=label).grid(row=row, column=0, sticky='w', padx=5, pady=4)
            ttk.Entry(fields, textvariable=self.resource_values[key], width=20).grid(row=row, column=1, sticky='w', padx=5)
            self._button(fields, '设置'+label, lambda key=key: self._set_resource(key)).grid(row=row, column=2, padx=5)
        ttk.Label(fields, text='增加金币与木材').grid(row=0, column=3, sticky='w', padx=(35, 5))
        ttk.Entry(fields, textvariable=self.add_amount, width=16).grid(row=0, column=4, padx=5)
        self._button(fields, '增加（Ctrl+L）', self._add_resources).grid(row=1, column=3, columnspan=2, padx=(35, 5), sticky='w')

    def _make_units(self, tab):
        tab.columnconfigure(0, weight=1); tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text='显示游戏当前选中单位；补满和英雄操作针对当前选择，非英雄会跳过。').grid(row=0, column=0, sticky='w', pady=(0, 8))
        columns = [('type_id', '单位ID'), ('owner', '所属玩家'), ('hp', '生命／上限'), ('mp', '魔法／上限'), ('level', '英雄等级'), ('str', '永久力量'), ('agi', '永久敏捷'), ('int', '永久智力')]
        frame, self.units = self._table(tab, columns, [90, 80, 145, 145, 90, 85, 85, 85], 9)
        frame.grid(row=1, column=0, sticky='nsew')
        self._button(tab, '单位生命魔法全满（Ctrl+空格）', lambda: self._enqueue('fill_selected', (), '补满生命魔法')).grid(row=2, column=0, sticky='w', pady=10)
        hero = ttk.LabelFrame(tab, text='英雄等级与永久三围', padding=12); hero.grid(row=3, column=0, sticky='ew')
        ttk.Checkbutton(hero, text='使用自定义等级', variable=self.custom_level, command=self._update_custom).grid(row=0, column=0, sticky='w', pady=5)
        self.level_entry = ttk.Entry(hero, textvariable=self.level, width=12); self.level_entry.grid(row=0, column=1, padx=8)
        self._button(hero, '应用英雄等级（Ctrl+Q）', self._hero_level).grid(row=0, column=2, sticky='w', padx=8)
        ttk.Label(hero, text='未勾选：每次增加1级').grid(row=1, column=0, columnspan=3, sticky='w', pady=(0, 8))
        ttk.Checkbutton(hero, text='使用自定义永久三围', variable=self.custom_stats, command=self._update_custom).grid(row=2, column=0, sticky='w')
        self.stat_entries = []
        for row, (label, variable) in enumerate(zip(('力量', '敏捷', '智力'), self.stats), 3):
            ttk.Label(hero, text=label).grid(row=row, column=0, sticky='e', pady=4)
            entry = ttk.Entry(hero, textvariable=variable, width=12); entry.grid(row=row, column=1, padx=8)
            self.stat_entries.append(entry)
        self._button(hero, '应用永久三围（Alt+Q）', self._hero_stats).grid(row=3, column=2, sticky='w', padx=8)
        ttk.Label(hero, text='未勾选：力量、敏捷、智力各增加2点').grid(row=4, column=2, rowspan=2, sticky='w', padx=8)
        self._update_custom()

    def _update_custom(self):
        self.level_entry.configure(state='normal' if self.custom_level.get() else 'disabled')
        for entry in self.stat_entries: entry.configure(state='normal' if self.custom_stats.get() else 'disabled')

    def _make_clone(self, tab):
        tab.columnconfigure(0, weight=1)
        ttk.Label(tab, text='复制与替换会创建游戏对象，建议先保存；替换会移除旧单位，地图脚本对旧单位的引用无法通用迁移。',
            wraplength=880).grid(row=0, column=0, sticky='w', pady=(0, 16))
        ownership = ttk.LabelFrame(tab, text='复制归属', padding=12)
        ownership.grid(row=1, column=0, sticky='ew')
        for row, (value, label) in enumerate((('self', '给自己（默认）'), ('selected', '给选中单位所属玩家'), ('player', '给指定玩家'))):
            ttk.Radiobutton(ownership, text=label, value=value, variable=self.owner_mode,
                command=self._update_owner_mode).grid(row=row, column=0, sticky='w', pady=6)
        self.owner_combo = ttk.Combobox(ownership, textvariable=self.owner_player, values=(), width=34, state='disabled')
        self.owner_combo.grid(row=2, column=1, sticky='w', padx=12)
        ttk.Label(ownership, text='指定玩家列表会随读取结果更新，包括当前地图的特殊中立槽位。', wraplength=800).grid(
            row=3, column=0, columnspan=2, sticky='w', pady=(8, 0))
        clone = ttk.LabelFrame(tab, text='复制当前选中单位', padding=12)
        clone.grid(row=2, column=0, sticky='ew', pady=14)
        self._button(clone, '复制单位（Ctrl+B）', lambda: self._clone(False)).grid(row=0, column=0, sticky='w')
        self._button(clone, '复制给自己（Ctrl+A）', self._clone_self).grid(row=0, column=1, padx=12, sticky='w')
        ttk.Label(clone, text='每个选中单位的复制数量').grid(row=1, column=0, sticky='w', pady=(16, 4))
        ttk.Spinbox(clone, from_=1, to=200, textvariable=self.clone_count, width=10).grid(row=1, column=1, padx=12, sticky='w', pady=(16, 4))
        self._button(clone, '大量复制（Ctrl+N）', lambda: self._clone(True)).grid(row=1, column=2, sticky='w', pady=(16, 4))
        ttk.Label(clone, text='复制数量1～200；一次创建总数不得超过200，具体状态由后端校验并返回结果。', wraplength=800).grid(
            row=2, column=0, columnspan=3, sticky='w', pady=(8, 0))
        replace = ttk.LabelFrame(tab, text='替换当前选中单位', padding=12)
        replace.grid(row=3, column=0, sticky='ew')
        ttk.Label(replace, text='新单位ID').grid(row=0, column=0, sticky='w')
        ttk.Entry(replace, textvariable=self.replace_id, width=14).grid(row=0, column=1, padx=12, sticky='w')
        self._button(replace, '替换单位（Ctrl+U+8）', self._replace).grid(row=0, column=2, sticky='w')
        ttk.Label(replace, text='填写4位ASCII字母或数字，区分大小写；默认zhyd。替换保持源单位所属玩家，不使用上面的复制归属选择。',
            wraplength=800).grid(row=1, column=0, columnspan=3, sticky='w', pady=(10, 0))

    def _update_owner_mode(self):
        enabled = self.owner_mode.get() == 'player' and bool(self.owner_choices)
        self.owner_combo.configure(state='readonly' if enabled else 'disabled')

    def _clone_owner(self):
        mode = self.owner_mode.get()
        if mode not in ('self', 'selected', 'player'): raise ValueError('请选择有效的复制归属方式')
        if mode != 'player': return mode, 0
        if self.owner_player.get() not in self.owner_choices: raise ValueError('请先读取玩家列表，再选择指定玩家')
        return mode, self.owner_choices[self.owner_player.get()]

    def _clone(self, mass):
        def submit():
            count = self._integer(self.clone_count, '复制数量', 1, 200) if mass else 1
            mode, player = self._clone_owner()
            self._enqueue('clone_selected', (count, mode, player), '大量复制' if mass else '复制单位')
        self._with_input(submit)

    def _clone_self(self):
        # Ctrl+A always ignores the panel owner setting.
        self._enqueue('clone_selected', (1, 'self', 0), '复制给自己')

    def _replace(self):
        def submit():
            rawcode = self.replace_id.get().strip()
            if len(rawcode) != 4 or not rawcode.isascii() or not rawcode.isalnum():
                raise ValueError('单位ID必须是4位ASCII字母或数字，区分大小写')
            self._enqueue('replace_selected', (rawcode,), '替换单位')
        self._with_input(submit)

    def _integer(self, variable, label, minimum=0, maximum=100_000_000):
        try: value = int(variable.get().strip())
        except ValueError: raise ValueError(label+'必须填写整数') from None
        if not minimum <= value <= maximum: raise ValueError(f'{label}范围为 {minimum}～{maximum}')
        return value

    def _with_input(self, callback):
        try: callback()
        except ValueError as exc: messagebox.showerror('输入无效', str(exc), parent=self.root)

    def _player(self):
        if self.selected_slot is None: raise ValueError('请先读取并在玩家列表中选择一个玩家')
        return self.selected_slot

    def _set_resource(self, key):
        self._with_input(lambda: self._enqueue('set_resource', (self._player(), key, self._integer(self.resource_values[key], dict(RESOURCE_LABELS)[key])), '设置'+dict(RESOURCE_LABELS)[key]))

    def _add_resources(self):
        self._with_input(lambda: self._enqueue('add_resources', (self._player(), self._integer(self.add_amount, '增加数量', 1)), '增加金币木材'))

    def _hero_level(self):
        self._with_input(lambda: self._enqueue('set_hero_level', (self._integer(self.level, '英雄等级', 1, 1000) if self.custom_level.get() else 1, not self.custom_level.get()), '设置英雄等级' if self.custom_level.get() else '英雄等级增加1'))

    def _hero_stats(self):
        def submit():
            values = tuple(self._integer(v, name, 0, 100_000) for v, name in zip(self.stats, ('力量', '敏捷', '智力'))) if self.custom_stats.get() else (2, 2, 2)
            self._enqueue('set_hero_attributes', (*values, not self.custom_stats.get()), '设置永久三围' if self.custom_stats.get() else '永久三围各增加2')
        self._with_input(submit)

    def _set_busy(self, busy):
        self.busy = busy
        for button in self.buttons:
            disabled = self.closing or busy or (button in self.connected_buttons and not self.pid) or self.offline
            button.configure(state='disabled' if disabled else 'normal')

    def _enqueue(self, method, args, title):
        # Do not replay a hotkey or queue an old selection behind a slow action.
        if self.offline or self.closing or self.busy: return
        if method != 'connect' and not self.pid:
            self.status.set('请先连接 Legacy 游戏。'); return
        self._set_busy(True); self.status.set(title+'，请稍候…')
        self.jobs.put((method, args, title))

    def _worker(self):
        while True:
            method, args, title = self.jobs.get()
            try:
                if method == 'close':
                    try:
                        if self.backend is not None: self.backend.close()
                    except Exception:
                        pass  # A dead process must not keep the trainer window open.
                    self.results.put(('closed', None, title)); return
                if self.backend is None:
                    from legacy_backend import LegacyTrainer
                    self.backend = LegacyTrainer(target_path=self.target_path)
                data = getattr(self.backend, method)(*args)
                self.results.put(('ok', data, title))
            except Exception as exc:
                self.results.put(('error', str(exc), title))

    @staticmethod
    def _number(value):
        try: return f'{float(value):g}'
        except (ValueError, TypeError): return '未确认'

    def _apply_snapshot(self, data):
        if not isinstance(data, dict): raise ValueError('后端没有返回有效的读取结果')
        new_pid = int(data.get('pid') or 0)
        if new_pid != self.pid: self.selected_slot = None
        self.data, self.pid = data, new_pid
        self.identity.set(f'PID {self.pid} · {data.get("profile", "Legacy 1.29.2")}')
        self.players.delete(*self.players.get_children())
        # Use the backend's verified map mode; slot numbers alone cannot tell
        # whether an old script's Player(12..15) aliases the neutral players.
        neutral_start = 12 if data.get('old_map_neutral_aliases', False) else 24
        neutrals = ('中立敌对', '中立受害者', '中立额外', '中立被动')
        previous_target = self.owner_choices.get(self.owner_player.get())
        self.owner_choices = {}
        for p in data.get('players', []):
            slot = int(p['slot'])
            label = f'{neutrals[slot-neutral_start]}（玩家{slot+1}）' if neutral_start <= slot < neutral_start+4 else f'玩家 {slot+1}'
            self.owner_choices[label] = slot
            self.players.insert('', 'end', iid=str(slot), values=(label, '是' if slot == data.get('local_player') else '', *(p.get(key, '未确认') for key, _ in RESOURCE_LABELS)))
        self.owner_combo.configure(values=list(self.owner_choices))
        target = previous_target if previous_target in self.owner_choices.values() else data.get('local_player')
        self.owner_player.set(next((label for label, slot in self.owner_choices.items() if slot == target), next(iter(self.owner_choices), '')))
        self._update_owner_mode()
        available = self.players.get_children()
        if str(self.selected_slot) not in available:
            local = str(data.get('local_player', ''))
            self.selected_slot = int(local if local in available else available[0]) if available else None
        if self.selected_slot is not None:
            self.players.selection_set(str(self.selected_slot)); self._select_player()
        self.units.delete(*self.units.get_children())
        for index, unit in enumerate(data.get('units', [])):
            hero = unit.get('hero', False)
            life = self._number(unit.get('hp'))+' / '+self._number(unit.get('max_hp'))
            mana = self._number(unit.get('mp'))+' / '+self._number(unit.get('max_mp'))
            owner = unit.get('owner')
            self.units.insert('', 'end', iid=str(index), values=(unit.get('type_id', '未确认'), owner+1 if isinstance(owner, int) else '未确认', life, mana, *(unit.get(key, '未确认') if hero else '—' for key in ('level', 'str', 'agi', 'int'))))

    def _select_player(self, _event=None):
        chosen = self.players.selection()
        if not chosen: return
        self.selected_slot = int(chosen[0])
        player = next((p for p in self.data.get('players', []) if p['slot'] == self.selected_slot), None)
        if player:
            for key, _ in RESOURCE_LABELS: self.resource_values[key].set(str(player.get(key, '')))

    def _drain_results(self):
        try:
            while True:
                kind, value, title = self.results.get_nowait()
                if kind == 'closed': self.root.destroy(); return
                if self.closing: continue
                if kind == 'ok':
                    try:
                        self._apply_snapshot(value)
                        if value.get('message'):
                            self.status.set(str(value['message']))
                        elif value.get('applied') == 0 and title not in ('连接', '读取'):
                            self.status.set('未发现符合条件的选中目标，未作修改')
                        else:
                            self.status.set(f'{title}完成；读取到 {len(value.get("players", []))} 个玩家槽位、{len(value.get("units", []))} 个选中单位。')
                    except Exception as exc: kind, value = 'error', str(exc)
                if kind == 'error':
                    if title in ('连接', '读取'):
                        self.pid = 0; self.identity.set('本次读取未确认，请重新连接')
                        self.players.delete(*self.players.get_children()); self.units.delete(*self.units.get_children())
                        self.owner_choices = {}; self.owner_player.set(''); self.owner_combo.configure(values=())
                        self._update_owner_mode()
                    self.status.set(title+'未完成：'+str(value))
                    messagebox.showerror('操作未完成', str(value), parent=self.root)
                self._set_busy(False)
        except queue.Empty: pass
        self.root.after(60, self._drain_results)

    def _make_hotkey_api(self):
        self.user32 = None
        if os.name != 'nt': return
        from ctypes import wintypes as w
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.GetForegroundWindow.restype = w.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = w.DWORD
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short

    def _poll_hotkeys(self):
        if self.closing: return
        pressed = set()
        if self.user32 and self.pid and self.hotkeys.get() and not self.offline:
            from ctypes import wintypes as w
            front_pid = w.DWORD()
            self.user32.GetWindowThreadProcessId(self.user32.GetForegroundWindow(), ctypes.byref(front_pid))
            if front_pid.value == self.pid:
                down = lambda key: bool(self.user32.GetAsyncKeyState(key) & 0x8000)
                ctrl, alt = down(0x11), down(0x12)
                if down(0x74) and not ctrl and not alt: pressed.add('read')
                if ctrl and not alt:
                    if down(0x20): pressed.add('fill')
                    if down(ord('Q')): pressed.add('level')
                    if down(ord('L')): pressed.add('resources')
                    if down(ord('B')): pressed.add('clone')
                    if down(ord('A')): pressed.add('clone_self')
                    if down(ord('N')): pressed.add('mass_clone')
                    if down(ord('U')) and down(ord('8')): pressed.add('replace')
                if alt and not ctrl and down(ord('Q')): pressed.add('stats')
        edges = pressed - self.held; self.held = pressed
        actions = {'read': lambda: self._enqueue('snapshot', (), '读取'), 'fill': lambda: self._enqueue('fill_selected', (), '补满生命魔法'), 'level': self._hero_level, 'stats': self._hero_stats, 'resources': self._add_resources,
            'clone': lambda: self._clone(False), 'clone_self': self._clone_self, 'mass_clone': lambda: self._clone(True), 'replace': self._replace}
        if not self.busy:
            for key in ('replace', 'read', 'fill', 'level', 'stats', 'resources', 'clone_self', 'clone', 'mass_clone'):
                if key in edges: actions[key](); break
        self.root.after(60, self._poll_hotkeys)

    def close(self):
        if self.closing: return
        self.closing = True; self.hotkeys.set(False); self._set_busy(True)
        if self.offline: self.root.destroy(); return
        self.status.set('正在断开 Legacy 连接…'); self.jobs.put(('close', (), '关闭'))

    def ui_check(self, path):
        """Construct and inspect all tabs without importing/starting a backend."""
        self.root.update_idletasks()
        self.tabs.select(1); self.root.update_idletasks()
        default_disabled = self.level_entry.instate(['disabled']) and all(e.instate(['disabled']) for e in self.stat_entries)
        self.custom_level.set(True); self.custom_stats.set(True); self._update_custom()
        custom_enabled = not self.level_entry.instate(['disabled']) and all(not e.instate(['disabled']) for e in self.stat_entries)
        self.custom_level.set(False); self.custom_stats.set(False); self._update_custom()
        self.tabs.select(2); self.root.update_idletasks()
        clone_defaults = self.owner_mode.get() == 'self' and self.clone_count.get() == '10' and self.replace_id.get() == 'zhyd'
        report = dict(ok=self.offline and default_disabled and custom_enabled and clone_defaults and len(self.tabs.tabs()) == 3,
            offline=self.offline, backend_imported=self.backend is not None, tabs=[self.tabs.tab(t, 'text') for t in self.tabs.tabs()],
            buttons=len(self.buttons), hotkeys_default_off=not self.hotkeys.get(), custom_inputs_default_disabled=default_disabled,
            checkbox_enables_custom_inputs=custom_enabled, target_path=self.target_path,
            clone_defaults_valid=clone_defaults, clone_owner_options=['self', 'selected', 'player'], replace_id_default=self.replace_id.get(),
            controls_constructed=True, game_process_attached=False, gameplay_mutations=False,
            width=self.root.winfo_width(), height=self.root.winfo_height())
        target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        self.close()


def main():
    parser = argparse.ArgumentParser(description='Legacy 1.29.2 修改器 v0.2.0-Test')
    parser.add_argument('--offline', action='store_true', help='仅显示界面，不导入后端或连接游戏')
    parser.add_argument('--ui-check', metavar='REPORT_JSON', help='离线检查三页控件并退出')
    parser.add_argument('--read-only-probe', metavar='REPORT_JSON', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.ui_check and not args.offline: parser.error('--ui-check 必须同时使用 --offline')
    if args.read_only_probe:
        if args.offline or args.ui_check: parser.error('只读探测不能与离线检查同时使用')
        from legacy_backend import LegacyTrainer
        backend=LegacyTrainer()
        try:
            backend.connect()
            report=dict(ok=True,gameplay_mutations=False,snapshot=backend.clone_preview())
        except Exception as exc: report=dict(ok=False,gameplay_mutations=False,error=str(exc),details=vars(exc))
        finally: backend.close()
        target=Path(args.read_only_probe);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        return
    root = tk.Tk(); app = TrainerWindow(root, offline=args.offline)
    if args.ui_check: root.after(200, lambda: app.ui_check(args.ui_check))
    root.mainloop()


if __name__ == '__main__': main()
