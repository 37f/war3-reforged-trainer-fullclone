import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { createPortal } from 'react-dom'
import { Button, Checkbox, Select, TextField } from '../../../ds'
import { PLAYER_COLORS } from '../../../ds/tokens'
import { fullclone } from '../../../lib/api'
import { useSystem } from '../../state/system'
import { useNav } from '../../state/nav'
import { usePageMemory } from '../../state/pageMemory'
import { fill, useT } from '../../i18n'
import s from './PlayerDirectoryPage.module.css'

type DragPreview = { player: number; x: number; y: number; label: string; color: string }
type PlayerDrag = DragPreview & { pointerId: number; context: string; startX: number; startY: number; moved: boolean }
type Group = { key: string; name: string; members: number[]; template?: number }
type Config = { name: string; race_label: string; controller_label: string; skin_label: string; fixed_start: boolean; x: number; y: number }
type Player = { id: number; slot: number; name: string; name_source: string; color: number | null; race_label: string; controller_label: string; state_label: string; slot_state?: number; is_local?: boolean; start_index?: number; special?: string; team?: number | null; diplomacy?: number | null; diplomacy_available?: boolean; diplomacy_label?: string; groups: string[]; config?: Config }
type Directory = { rows: Player[]; initial_groups: Group[]; current_groups: Group[]; diplomacy_groups?: Group[]; source: string; issues: string[]; map_name: string; context: string; profile: string; read_at: string }

// Display swatches only; these do not set player colours or infer slot identity.
const COLORS = [...PLAYER_COLORS, '#9B0000', '#0000C3', '#00EAFF', '#BE00FE', '#EBCD87', '#F8A48B', '#BFFF80', '#DCB9EB', '#282828', '#EBF0FF', '#00781E', '#A46F33']
const COLOR_NAMES = ['红', '蓝', '青', '紫', '黄', '橙', '绿', '粉', '灰', '浅蓝', '深绿', '棕', '栗红', '深蓝', '蓝绿', '紫罗兰', '小麦', '桃色', '薄荷', '淡紫', '煤黑', '雪白', '祖母绿', '花生棕']
const teamText = (p: Player) => p.special ? `${p.special}（原始队伍值 ${p.team ?? '未确认'}）` : p.team == null ? '未确认' : p.team === -1 ? '未分配普通队伍（-1）' : `队伍 ${p.team + 1}`
const diplomacyText = (p: Player) => p.diplomacy_label || (p.diplomacy == null ? '未套用外交模板' : p.diplomacy < 12 ? `队伍 ${p.diplomacy + 1}` : p.diplomacy === 12 ? '中立敌对' : p.diplomacy === 13 ? '中立被动' : '未确认')
const colorText = (value: number | null) => value == null ? '未确认' : COLOR_NAMES[value] ? `${value + 1} · ${COLOR_NAMES[value]}` : `原始值 ${value}`
function Color({ value }: { value: number | null }) {
  const t = useT()
  return <span className={s.color}><i aria-hidden="true" style={{ background: value == null ? 'transparent' : COLORS[value] || 'transparent' }} />{t(colorText(value))}</span>
}

function applyTeamMove(data: Directory, player: number, destination: Group): Directory {
  const groups = (data.diplomacy_groups || []).map(g => {
    if (g.key === destination.key) return { ...g, members: [...g.members, player].sort((a, b) => a - b) }
    if (g.members.includes(player)) return { ...g, members: g.members.filter(id => id !== player) }
    return g
  }).filter(g => g.members.length || (g.template != null &&
    (g.template >= 12 || data.current_groups.some(native => native.key === `team:${g.template}`))))
  return {
    ...data,
    rows: data.rows.map(row => row.id === player
      ? { ...row, diplomacy: destination.template, diplomacy_label: destination.name }
      : row),
    diplomacy_groups: groups,
  }
}

function applyTeamRestore(data: Directory, restored: number[]): Directory {
  const ids = new Set(restored)
  const groups = (data.diplomacy_groups || []).map(g => ({ ...g, members: g.members.filter(id => !ids.has(id)) }))
  const rows = data.rows.map(row => {
    if (!ids.has(row.id)) return row
    const native = data.current_groups.find(g => g.members.includes(row.id))
    const origin = data.initial_groups.find(g => g.members.includes(row.id))
    const target = row.id === 24 ? 12 : row.id === 27 ? 13 : row.team
    const key = native?.key === 'inactive' ? 'inactive'
      : target != null && target >= 0 && target < 14 && (row.special || target < 12) ? 'diplomacy:'+target
      : origin ? 'diplomacy-origin:'+origin.key : 'diplomacy-unknown'
    let group = groups.find(g => g.key === key)
    if (!group) {
      group = { key, name: origin ? origin.name+'（队伍未确认）' : '队伍未确认', members: [] }
      groups.push(group)
    }
    group.members.push(row.id)
    group.members.sort((a, b) => a - b)
    return { ...row, diplomacy: null, diplomacy_label: group.name }
  })
  return { ...data, rows, diplomacy_groups: groups.filter(g => g.template != null || g.members.length) }
}

export default function PlayerDirectoryPage() {
  const connected = useSystem(st => st.status.connected)
  const pid = useSystem(st => st.status.pid)
  const t = useT()
  const active = useNav(st => st.page === 'players')
  const remember = usePageMemory(st => st.remember.players)
  const [checking, setChecking] = useState(false)
  const needsCheck = useRef(false)
  const [data, setData] = useState<Directory | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [monitor, setMonitor] = useState(false)
  const [mode, setMode] = useState('initial')
  const [nameMode, setNameMode] = useState('game')
  const [group, setGroup] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [activeOnly, setActiveOnly] = useState(false)
  const [notice, setNotice] = useState('')
  const [preview, setPreview] = useState<DragPreview | null>(null)
  const [dropGroup, setDropGroup] = useState('')
  const drag = useRef<PlayerDrag | null>(null), moving = useRef(false)
  const page = useRef<HTMLDivElement>(null), teamList = useRef<HTMLElement>(null)
  const suppressClick = useRef(false)
  const dragging = preview !== null
  const reading = useRef(false), generation = useRef(0), context = useRef('')
  const clearDrag = () => { drag.current = null; setPreview(null); setDropGroup('') }
  useEffect(() => {
    generation.current++; setData(null); setError(''); setBusy(false); setMonitor(false); setGroup(''); setSelected(null); setNotice(''); clearDrag()
    return () => { generation.current++ }
  }, [connected, pid])
  useEffect(() => {
    if (!dragging) return
    // Pointer capture keeps the card held while Chromium delivers wheel input.
    const scrollPage = (event: WheelEvent) => {
      const container = page.current
      if (!container || !drag.current?.moved || event.ctrlKey || !event.deltaY) return
      event.preventDefault()
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? container.clientHeight : 1
      container.scrollTop += event.deltaY * unit
    }
    window.addEventListener('wheel', scrollPage, { capture: true, passive: false })
    return () => window.removeEventListener('wheel', scrollPage, true)
  }, [dragging])

  const read = async (refresh = false) => {
    if (!connected || !active || checking || reading.current || moving.current || drag.current) return
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
  useEffect(() => {
    if (!active) { needsCheck.current = true; clearDrag(); return }
    if (!needsCheck.current || !context.current || !connected) { setChecking(false); return }
    setChecking(true)
    const version = generation.current
    let live = true
    void fullclone.pageContext().then(result => {
      if (live && generation.current === version && result.context !== context.current) {
        throw new Error('地图已变化，请重新读取玩家信息')
      }
    }).catch(e => {
      if (!live || generation.current !== version) return
      context.current = ''; setData(null); setMonitor(false); setSelected(null); setGroup('')
      setNotice(''); setError(e instanceof Error ? e.message : String(e))
    }).finally(() => {
      if (live && generation.current === version) { needsCheck.current = false; setChecking(false) }
    })
    return () => { live = false }
  }, [active, connected, pid])
  const restoreAll = async () => {
    if (!connected || busy || checking || reading.current || moving.current) return
    const version = generation.current
    moving.current = true; setBusy(true); setError('')
    try {
      const r = await fullclone.action('restore_all_teams')
      if (generation.current !== version) return
      const restored: number[] = r.restored || []
      setData(previous => previous && restored.length ? applyTeamRestore(previous, restored) : previous)
      setGroup('')
      setNotice(r.message)
    } catch (e) {
      if (generation.current === version) { setData(null); setMonitor(false); setError(e instanceof Error ? e.message : String(e)); setNotice('') }
    } finally { moving.current = false; if (generation.current === version) setBusy(false) }
  }
  const groups = data ? mode === 'initial' ? data.initial_groups : mode === 'diplomacy' ? (data.diplomacy_groups || []) : data.current_groups : []
  const chosenGroup = groups.find(g => g.key === group)
  const groupLabel = (g: Group) => g.key.startsWith('force:') ? g.name : t(g.name)
  const query = search.trim().toLocaleLowerCase()
  const rows = (data?.rows || []).filter(p => (!chosenGroup || chosenGroup.members.includes(p.id)) && (!activeOnly || p.slot_state === 1 || p.special || p.is_local) && (!query || [p.slot, p.name, p.config?.name, p.special, p.race_label, p.controller_label, ...p.groups].join(' ').toLocaleLowerCase().includes(query)))
  const player = data?.rows.find(p => p.id === selected)
  const mapPlayerName = (p: Player) => {
    const name = p.config?.name?.trim()
    return name && !/^(?:TRIGSTR|STR)_\d+(?:（文字表缺失）)?$/i.test(name) ? name : ''
  }
  const displayName = (p: Player) => nameMode === 'map'
    ? mapPlayerName(p) || '—'
    : (p.name_source === '中立槽位标识' || p.name_source === '槽位编号' ? t(p.name) : p.name)
  const nameSource = (p: Player) => nameMode === 'map'
    ? t(mapPlayerName(p) ? '地图配置名（非实时）' : '地图未设置名称')
    : t(p.name_source)

  const draggable = (p: Player) => mode === 'diplomacy' && connected && !busy && !checking &&
    (p.id < 24 || p.id === 24 || p.id === 27)
  const move = async (destination: Group, payload: { player: number; context: string }) => {
    if (!data || !connected || busy || checking || reading.current || moving.current || destination.template == null || payload.context !== data.context || destination.members.includes(payload.player)) return
    const version = generation.current
    moving.current = true; setBusy(true); setError(''); setNotice('正在修改外交模板…')
    try {
      const result = await fullclone.movePlayer(payload.player, destination.template, payload.context)
      if (version !== generation.current) return
      if (result.player !== payload.player || result.target !== destination.template || result.context !== payload.context) {
        throw new Error('外交模板回执与本次拖放不一致，请重新读取')
      }
      if (result.applied === false) { setNotice(result.message); return }
      setData(previous => previous?.context === result.context ? applyTeamMove(previous, result.player, destination) : previous)
      setSelected(result.player)
      setGroup(previous => previous ? destination.key : previous)
      setNotice(result.message || '外交模板已修改')
    } catch (e) {
      if (version === generation.current) { setData(null); setMonitor(false); setError(e instanceof Error ? e.message : String(e)); setNotice('') }
    } finally { moving.current = false; if (version === generation.current) setBusy(false) }
  }
  const targetAt = (x: number, y: number) => {
    const element = document.elementFromPoint(x, y)?.closest<HTMLElement>('details[data-team]')
    if (element && teamList.current?.contains(element)) return groups.find(g => g.template === Number(element.dataset.team))
  }
  const highlightDrop = () => {
    const current = drag.current
    if (current?.moved) {
      const target = targetAt(current.x, current.y)
      setDropGroup(target && !target.members.includes(current.player) ? target.key : '')
    }
  }
  const dragCard = (event: PointerEvent<HTMLButtonElement>) => {
    const current = drag.current
    if (!current || current.pointerId !== event.pointerId) return
    if (!current.moved && Math.hypot(event.clientX - current.startX, event.clientY - current.startY) < 5) return
    current.moved = true
    suppressClick.current = true
    current.x = event.clientX
    current.y = event.clientY
    setPreview({ ...current })
    highlightDrop()
  }
  const dropCard = (event: PointerEvent<HTMLButtonElement>) => {
    const current = drag.current
    if (!current || current.pointerId !== event.pointerId) return
    const target = current.moved ? targetAt(event.clientX, event.clientY) : undefined
    clearDrag()
    if (target) void move(target, current)
  }
  const cancelCard = (event: PointerEvent<HTMLButtonElement>) => {
    if (drag.current?.pointerId === event.pointerId) clearDrag()
  }
  return <div ref={page} className={s.page} data-testid="player-directory" onScroll={highlightDrop}>
    {preview && createPortal(
      <span className={s.dragPreview} data-testid="player-drag-preview" aria-hidden="true" style={{ left: preview.x + 10, top: preview.y + 10 }}>
        <i className={s.chip} style={{ background: preview.color }} />{preview.label}
      </span>,
      document.body,
    )}
    <div className={s.toolbar}>
      <Checkbox label={t('记忆模式')} checked={remember} onChange={() => usePageMemory.getState().setRemember('players', !remember)} />
      <Select label={t('玩家名显示')} aria-label={t('玩家名显示')} value={nameMode}
        options={[{ value: 'game', label: t('游戏中名字（含玩家昵称）') }, { value: 'map', label: t('地图配置名') }]}
        onChange={e => setNameMode(e.target.value)} />
      {mode === 'diplomacy' && <Button disabled={!connected || busy || checking} onClick={() => void restoreAll()}>{t('恢复所有玩家真正原队伍')}</Button>}
      <Button disabled={!connected || busy || checking} onClick={() => void read()}>{t('读取／刷新玩家信息')}</Button>
      <Button disabled={!connected || busy || checking} onClick={() => void read(true)}>{t('重新读取地图配置')}</Button>
      <Checkbox label={t('每5秒监视')} checked={monitor} disabled={!connected} onChange={() => { setMonitor(!monitor); if (!monitor) void read() }} />
      <span role="status">{checking ? t('正在核对记忆中的地图…') : busy ? t(moving.current ? '正在修改外交模板…' : '正在只读核对玩家与地图配置…') : error || notice ? t(error || notice) : data ? fill(t('{n} 个槽位 · 读取于 {time}'), { n: data.rows.length, time: data.read_at }) : t(connected ? '点击读取后显示当前地图玩家' : '请先连接游戏')}</span>
    </div>
    <p className={s.note}>{t('玩家信息按读取结果显示。选择“查看或修改外交模板”后，可把左侧玩家框拖入目标队伍，松开后套用外交模板，控制权限保持不变。尚未修改或已恢复的玩家按原队伍显示；原生队伍和地图初始势力分别保留。')}</p>
    {data && <>
      <p className={s.source}>{data.map_name && fill(t('地图：{name}'), { name: data.map_name }) + ' · '}{t('配置来源：')}{data.source || t('未确认')}<br />{t('每个名字注明读取来源；颜色、种族、控制者等来自游戏进程。下方出生点和界面皮肤来自地图初始配置。')}</p>
      {data.issues.length > 0 && <details className={s.note}><summary>{fill(t('读取说明（{n}）'), { n: data.issues.length })}</summary><ul>{data.issues.map((issue, i) => <li key={i}>{t(issue)}</li>)}</ul></details>}
      <div className={s.body}>
        <nav ref={teamList} className={s.groups} aria-label={t('队伍成员')}>
          <Select label={t('分组方式')} aria-label={t('分组方式')} value={mode} options={[{ value: 'initial', label: t('地图初始势力') }, { value: 'current', label: t('原生队伍（读取时）') }, { value: 'diplomacy', label: t('查看或修改外交模板') }]} onChange={e => { setMode(e.target.value); setGroup('') }} />
          <Button size="sm" onClick={() => setGroup('')}>{t('查看全部玩家')}</Button>
          {groups.map(g => <details key={g.key} open data-team={g.template} className={dropGroup === g.key ? s.dropTarget : undefined}>
            <summary><button type="button" aria-pressed={g.key === group} onClick={e => { e.preventDefault(); setGroup(g.key) }}>{fill(t('{name}（{n} 个玩家）'), { name: groupLabel(g), n: g.members.length })}</button></summary>
            <ul>{g.members.map(id => {
              const p = data.rows.find(r => r.id === id)
              if (!p) return null
              const movable = draggable(p)
              const label = fill(t('玩家 {n}'), { n: p.slot }) + ' · ' + displayName(p) + (p.is_local ? t('（自己）') : '')
              const color = p.color == null ? 'transparent' : COLORS[p.color] || 'transparent'
              return <li key={id}><button type="button" data-player={p.id} data-draggable={movable || undefined}
                className={preview?.player === p.id ? s.dragging : undefined}
                title={movable ? t(p.diplomacy_available === false ? '当前地图未确认此玩家槽位' : '拖入另一队伍以修改外交模板') : undefined}
                onPointerDown={event => {
                  suppressClick.current = false
                  if (!movable || event.pointerType !== 'mouse' || event.button !== 0 || !event.isPrimary) return
                  event.currentTarget.setPointerCapture(event.pointerId)
                  drag.current = { player: p.id, context: data.context, pointerId: event.pointerId,
                    startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, label, color, moved: false }
                }}
                onPointerMove={dragCard} onPointerUp={dropCard} onPointerCancel={cancelCard} onLostPointerCapture={cancelCard}
                onKeyDown={event => {
                  if (event.key !== 'Escape' || !drag.current) return
                  const id = drag.current.pointerId
                  clearDrag()
                  if (event.currentTarget.hasPointerCapture(id)) event.currentTarget.releasePointerCapture(id)
                }}
                aria-current={p.id === selected ? 'true' : undefined} onClick={event => {
                  if (event.detail && suppressClick.current) { suppressClick.current = false; return }
                  setSelected(p.id); setGroup(g.key)
                }}><i className={s.chip} aria-hidden="true" style={{ background: color }} />{label}</button></li>
            })}</ul>
          </details>)}
        </nav>
        <article className={s.content}>
          <div className={s.toolbar}><TextField aria-label={t('搜索玩家信息')} placeholder={t('搜索名字、槽位、种族或势力')} value={search} onChange={e => setSearch(e.target.value)} />
            <Checkbox label={t('隐藏空槽和已离开玩家')} checked={activeOnly} onChange={() => setActiveOnly(!activeOnly)} />
            <span>{fill(t('{name} · {n} 项'), { name: chosenGroup ? groupLabel(chosenGroup) : t('全部玩家'), n: rows.length })}</span></div>
          <div className={s.table} tabIndex={0} aria-label={t('玩家信息表')}>
            <table><thead><tr><th>{t('玩家')}</th><th>{t('玩家名字')}</th><th>{t('颜色')}</th><th>{t('种族')}</th><th>{t('控制者')}</th><th>{t('槽位状态')}</th><th>{t('原生队伍')}</th><th>{t('当前外交模板')}</th><th>{t('地图初始势力')}</th></tr></thead>
              <tbody>{rows.map(p => <tr key={p.id} aria-selected={p.id === selected} onClick={() => setSelected(p.id)}>
                <td>{p.slot}</td><td><button type="button" title={nameSource(p)} onClick={() => setSelected(p.id)}>{displayName(p)}</button>{p.is_local && t('（自己）')}<small>{nameSource(p)}</small></td>
                <td><Color value={p.color} /></td><td>{t(p.race_label)}</td><td>{t(p.controller_label)}</td><td>{t(p.state_label)}</td><td>{t(teamText(p))}</td><td>{t(diplomacyText(p))}</td><td>{p.groups.join('、') || t('未列入／未确认')}</td>
              </tr>)}</tbody></table>
            {!rows.length && <p>{t('没有符合筛选条件的玩家。')}</p>}
          </div>
          {player ? <section className={s.detail} aria-label={t('玩家详情')}>
            <h2>{fill(t('玩家 {n}'), { n: player.slot })} · {displayName(player)}</h2>
            <p>{fill(t('名字来源：{source}；{team}；当前外交模板：{template}；出生点索引：{start}。'), {
              source: nameSource(player), team: t(teamText(player)), template: t(diplomacyText(player)),
              start: player.start_index == null ? t('未确认') : fill(t('{n}（游戏原始值）'), { n: player.start_index }),
            })}</p>
            <h3>{t('地图初始配置（非实时）')}</h3>
            {player.config ? <dl><dt>{t('配置名字')}</dt><dd>{mapPlayerName(player) || t('未命名')}</dd><dt>{t('控制者／种族')}</dt><dd>{t(player.config.controller_label)} / {t(player.config.race_label)}</dd><dt>{t('固定开始点')}</dt><dd>{t(player.config.fixed_start ? '是' : '否')}</dd><dt>{t('开始点坐标')}</dt><dd>X={Math.round(player.config.x)}，Y={Math.round(player.config.y)} {t('（地图初始位置）')}</dd><dt>{t('界面皮肤')}</dt><dd>{t(player.config.skin_label)}</dd></dl> : <p>{t('该槽位没有已确认的地图初始配置。')}</p>}
          </section> : <p className={s.note}>{t('点击左侧玩家或表中名字，查看固定开始点、界面皮肤等详情。')}</p>}
        </article>
      </div>
    </>}
  </div>
}
