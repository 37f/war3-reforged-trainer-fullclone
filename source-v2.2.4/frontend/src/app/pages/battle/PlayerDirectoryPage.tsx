import { useEffect, useRef, useState } from 'react'
import { Button, Checkbox, Select, TextField } from '../../../ds'
import { PLAYER_COLORS } from '../../../ds/tokens'
import { fullclone } from '../../../lib/api'
import { useSystem } from '../../state/system'
import { useNav } from '../../state/nav'
import { usePageMemory } from '../../state/pageMemory'
import s from './PlayerDirectoryPage.module.css'

type Group = { key: string; name: string; members: number[]; template?: number }
type Config = { name: string; race_label: string; controller_label: string; skin_label: string; fixed_start: boolean; x: number; y: number }
type Player = { id: number; slot: number; name: string; name_source: string; color: number | null; race_label: string; controller_label: string; state_label: string; slot_state?: number; is_local?: boolean; start_index?: number; special?: string; team?: number | null; diplomacy?: number | null; diplomacy_label?: string; groups: string[]; config?: Config }
type Directory = { rows: Player[]; initial_groups: Group[]; current_groups: Group[]; diplomacy_groups?: Group[]; source: string; issues: string[]; map_name: string; context: string; profile: string; read_at: string }

// Display swatches only; these do not set player colours or infer slot identity.
const COLORS = [...PLAYER_COLORS, '#9B0000', '#0000C3', '#00EAFF', '#BE00FE', '#EBCD87', '#F8A48B', '#BFFF80', '#DCB9EB', '#282828', '#EBF0FF', '#00781E', '#A46F33']
const COLOR_NAMES = ['红', '蓝', '青', '紫', '黄', '橙', '绿', '粉', '灰', '浅蓝', '深绿', '棕', '栗红', '深蓝', '蓝绿', '紫罗兰', '小麦', '桃色', '薄荷', '淡紫', '煤黑', '雪白', '祖母绿', '花生棕']
const teamText = (p: Player) => p.special ? `${p.special}（原始队伍值 ${p.team ?? '未确认'}）` : p.team == null ? '未确认' : p.team === -1 ? '未分配普通队伍（-1）' : `队伍 ${p.team + 1}`
const diplomacyText = (p: Player) => p.diplomacy_label || (p.diplomacy == null ? '未套用外交模板' : p.diplomacy < 12 ? `队伍 ${p.diplomacy + 1}` : p.diplomacy === 12 ? '中立敌对' : p.diplomacy === 13 ? '中立被动' : '未确认')
const colorText = (value: number | null) => value == null ? '未确认' : COLOR_NAMES[value] ? `${value + 1} · ${COLOR_NAMES[value]}` : `原始值 ${value}`
function Color({ value }: { value: number | null }) {
  return <span className={s.color}><i aria-hidden="true" style={{ background: value == null ? 'transparent' : COLORS[value] || 'transparent' }} />{colorText(value)}</span>
}

export default function PlayerDirectoryPage() {
  const connected = useSystem(st => st.status.connected)
  const pid = useSystem(st => st.status.pid)
  const active = useNav(st => st.page === 'players')
  const remember = usePageMemory(st => st.remember.players)
  const [checking, setChecking] = useState(false)
  const checkingRef = useRef(false)
  const needsCheck = useRef(false)
  const [data, setData] = useState<Directory | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [monitor, setMonitor] = useState(false)
  const [mode, setMode] = useState('initial')
  const [group, setGroup] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [activeOnly, setActiveOnly] = useState(false)
  const [notice, setNotice] = useState('')
  const [dragged, setDragged] = useState<number | null>(null)
  const [dropGroup, setDropGroup] = useState('')
  const drag = useRef<{ player: number; context: string } | null>(null), moving = useRef(false)
  const reading = useRef(false), generation = useRef(0), context = useRef('')
  useEffect(() => {
    generation.current++; setData(null); setError(''); setBusy(false); setMonitor(false); setGroup(''); setSelected(null); setNotice(''); setDragged(null); setDropGroup(''); drag.current = null
    return () => { generation.current++ }
  }, [connected, pid])
  const read = async (refresh = false) => {
    if (!connected || reading.current || moving.current || checkingRef.current) return
    const version = generation.current
    reading.current = true; setBusy(true)
    try {
      const result: Directory = await fullclone.players(refresh)
      if (generation.current !== version) return
      if (context.current !== result.context) { setGroup(''); setSelected(null); context.current = result.context }
      setData(result); setError('')
    } catch (e) {
      if (generation.current === version) { setData(null); setMonitor(false); setError(e instanceof Error ? e.message : String(e)) }
    } finally { reading.current = false; if (generation.current === version) setBusy(false) }
  }
  useEffect(() => {
    if (!monitor || !connected || !active || checking) return
    // A slow map read never queues a second scan behind it.
    const timer = setInterval(() => void read(), 5000)
    return () => clearInterval(timer)
  }, [monitor, connected, pid, active, checking]) // eslint-disable-line react-hooks/exhaustive-deps
  // Remembered rows cannot enable a drag/write until this map is revalidated.
  useEffect(() => {
    if (!active) { needsCheck.current = true; return }
    if (!needsCheck.current || !context.current || !connected) return
    needsCheck.current = false; checkingRef.current = true; setChecking(true)
    const version = generation.current
    let live = true
    void fullclone.pageContext().then(r => {
      if (live && generation.current === version && r.context !== context.current) throw new Error('地图已变化，请重新读取玩家信息')
    }).catch(e => {
      if (live && generation.current === version) { setData(null); context.current = ''; setMonitor(false); setSelected(null); setGroup(''); setError(String(e)) }
    }).finally(() => { if (live) { checkingRef.current = false; setChecking(false) } })
    return () => { live = false; checkingRef.current = false }
  }, [active, connected])
  const restoreAll = async () => {
    if (!connected || busy || checkingRef.current || reading.current || moving.current) return
    const version = generation.current
    moving.current = true; setBusy(true); setError('')
    try {
      const r = await fullclone.action('restore_all_teams')
      if (generation.current !== version) return
      moving.current = false; await read(); setNotice(r.message)
    } catch (e) {
      if (generation.current === version) { setData(null); setMonitor(false); setError(String(e)); setNotice('') }
    } finally { moving.current = false; if (generation.current === version) setBusy(false) }
  }
  const groups = data ? mode === 'initial' ? data.initial_groups : mode === 'diplomacy' ? (data.diplomacy_groups || []) : data.current_groups : []
  const chosenGroup = groups.find(g => g.key === group)
  const query = search.trim().toLocaleLowerCase()
  const rows = (data?.rows || []).filter(p => (!chosenGroup || chosenGroup.members.includes(p.id)) && (!activeOnly || p.slot_state === 1 || p.special || p.is_local) && (!query || [p.slot, p.name, p.special, p.race_label, p.controller_label, ...p.groups].join(' ').toLocaleLowerCase().includes(query)))
  const player = data?.rows.find(p => p.id === selected)
  const draggable = (p: Player) => mode === 'diplomacy' && connected && !busy && !checking && (p.id === 24 || p.id === 27 || p.id < 24 && (p.slot_state === 1 || p.is_local))
  const move = async (destination: Group, payload: { player: number; context: string }) => {
    if (!data || !connected || busy || checkingRef.current || reading.current || moving.current || destination.template == null || payload.context !== data.context || destination.members.includes(payload.player)) return
    const version = generation.current
    moving.current = true; setBusy(true); setError(''); setNotice('正在修改外交模板…')
    try {
      const result = await fullclone.movePlayer(payload.player, destination.template, payload.context)
      if (version !== generation.current) return
      moving.current = false
      await read()
      setNotice(result.message || '外交模板已修改')
    } catch (e) {
      if (version === generation.current) { setData(null); setMonitor(false); setError(e instanceof Error ? e.message : String(e)); setNotice('') }
    } finally { moving.current = false; if (version === generation.current) setBusy(false) }
  }
  return <div className={s.page} data-testid="player-directory">
    <div className={s.toolbar}>
      <Checkbox label="记忆模式" checked={remember} onChange={() => usePageMemory.getState().setRemember('players', !remember)} />
      {mode === 'diplomacy' && <Button disabled={!connected || busy || checking} onClick={() => void restoreAll()}>恢复所有玩家真正原队伍</Button>}
      <Button disabled={!connected || busy || checking} onClick={() => void read()}>读取／刷新玩家信息</Button>
      <Button disabled={!connected || busy || checking} onClick={() => void read(true)}>重新读取地图配置</Button>
      <Checkbox label="每5秒监视" checked={monitor} disabled={!connected} onChange={() => { setMonitor(!monitor); if (!monitor) void read() }} />
      <span role="status">{checking ? '正在核对记忆中的地图…' : busy ? moving.current ? '正在修改外交模板…' : '正在只读核对玩家与地图配置…' : error || notice || (data ? `${data.rows.length} 个槽位 · 读取于 ${data.read_at}` : connected ? '点击读取后显示当前地图玩家' : '请先连接游戏')}</span>
    </div>
    <p className={s.note}>玩家信息按读取结果显示。选择“查看或修改外交模板”后，可把左侧玩家框拖入目标队伍，松开后套用外交模板，控制权限保持不变。尚未修改或已恢复的玩家按原队伍显示；原生队伍和地图初始势力分别保留。</p>
    {data && <>
      <p className={s.source}>{data.map_name && `地图：${data.map_name}　`}配置来源：{data.source || '未确认'}<br />每个名字注明读取来源；颜色、种族、控制者等来自游戏进程。下方出生点和界面皮肤来自地图初始配置。</p>
      {data.issues.length > 0 && <details className={s.note}><summary>读取说明（{data.issues.length}）</summary><ul>{data.issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul></details>}
      <div className={s.body}>
        <nav className={s.groups} aria-label="队伍成员">
          <Select label="分组方式" aria-label="分组方式" value={mode} options={[{ value: 'initial', label: '地图初始势力' }, { value: 'current', label: '原生队伍（读取时）' }, { value: 'diplomacy', label: '查看或修改外交模板' }]} onChange={e => { setMode(e.target.value); setGroup('') }} />
          <Button size="sm" onClick={() => setGroup('')}>查看全部玩家</Button>
          {groups.map(g => <details key={g.key} open data-team={g.template} className={dropGroup === g.key ? s.dropTarget : undefined}
            onDragOver={e => { if (mode === 'diplomacy' && g.template != null && drag.current && !busy) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDropGroup(g.key) } }}
            onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropGroup('') }}
            onDrop={e => {
              e.preventDefault(); e.stopPropagation(); setDropGroup('')
              if (mode !== 'diplomacy' || !drag.current) return
              try {
                const payload = JSON.parse(e.dataTransfer.getData('application/x-war3-player'))
                if (payload.player === drag.current.player && payload.context === drag.current.context) void move(g, payload)
              } catch { /* External or invalid drag data never becomes a game operation. */ }
            }}>
            <summary><button type="button" aria-pressed={g.key === group} onClick={e => { e.preventDefault(); setGroup(g.key) }}>{g.name}（{g.members.length} 个玩家）</button></summary>
            <ul>{g.members.map(id => { const p = data.rows.find(r => r.id === id); return p && <li key={id}><button type="button" data-player={p.id} draggable={!!draggable(p)} className={dragged === p.id ? s.dragging : undefined}
              title={draggable(p) ? '拖入另一队伍以修改外交模板' : undefined}
              onDragStart={e => {
                if (!draggable(p)) { e.preventDefault(); return }
                drag.current = { player: p.id, context: data.context }; setDragged(p.id); e.dataTransfer.effectAllowed = 'move'
                e.dataTransfer.setData('application/x-war3-player', JSON.stringify(drag.current))
              }} onDragEnd={() => { drag.current = null; setDragged(null); setDropGroup('') }}
              aria-current={p.id === selected ? 'true' : undefined} onClick={() => { setSelected(p.id); setGroup(g.key) }}><i className={s.chip} aria-hidden="true" style={{ background: p.color == null ? 'transparent' : COLORS[p.color] || 'transparent' }} />玩家 {p.slot} · {p.name}{p.is_local && '（自己）'}</button></li> })}</ul>
          </details>)}
        </nav>
        <article className={s.content}>
          <div className={s.toolbar}><TextField aria-label="搜索玩家信息" placeholder="搜索名字、槽位、种族或势力" value={search} onChange={e => setSearch(e.target.value)} />
            <Checkbox label="隐藏空槽和已离开玩家" checked={activeOnly} onChange={() => setActiveOnly(!activeOnly)} />
            <span>{chosenGroup?.name || '全部玩家'} · {rows.length} 项</span></div>
          <div className={s.table} tabIndex={0} aria-label="玩家信息表">
            <table><thead><tr><th>玩家</th><th>玩家名字</th><th>颜色</th><th>种族</th><th>控制者</th><th>槽位状态</th><th>原生队伍</th><th>当前外交模板</th><th>地图初始势力</th></tr></thead>
              <tbody>{rows.map(p => <tr key={p.id} aria-selected={p.id === selected} onClick={() => setSelected(p.id)}>
                <td>{p.slot}</td><td><button type="button" title={p.name_source} onClick={() => setSelected(p.id)}>{p.name}</button>{p.is_local && '（自己）'}<small>{p.special || p.name_source}</small></td>
                <td><Color value={p.color} /></td><td>{p.race_label}</td><td>{p.controller_label}</td><td>{p.state_label}</td><td>{teamText(p)}</td><td>{diplomacyText(p)}</td><td>{p.groups.join('、') || '未列入／未确认'}</td>
              </tr>)}</tbody></table>
            {!rows.length && <p>没有符合筛选条件的玩家。</p>}
          </div>
          {player ? <section className={s.detail} aria-label="玩家详情">
            <h2>玩家 {player.slot} · {player.name}</h2>
            <p>名字来源：{player.name_source}；{teamText(player)}；当前外交模板：{diplomacyText(player)}；出生点索引：{player.start_index == null ? '未确认' : `${player.start_index}（游戏原始值）`}。</p>
            <h3>地图初始配置（非实时）</h3>
            {player.config ? <dl><dt>配置名字</dt><dd>{player.config.name || '未命名'}</dd><dt>控制者／种族</dt><dd>{player.config.controller_label}／{player.config.race_label}</dd><dt>固定开始点</dt><dd>{player.config.fixed_start ? '是' : '否'}</dd><dt>开始点坐标</dt><dd>X={Math.round(player.config.x)}，Y={Math.round(player.config.y)}（地图初始位置）</dd><dt>界面皮肤</dt><dd>{player.config.skin_label}</dd></dl> : <p>该槽位没有已确认的地图初始配置。</p>}
          </section> : <p className={s.note}>点击左侧玩家或表中名字，查看固定开始点、界面皮肤等详情。</p>}
        </article>
      </div>
    </>}
  </div>
}
