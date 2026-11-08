import { useEffect, useRef, useState } from 'react'
import { Button, Checkbox, Select, TextField } from '../../../ds'
import { PLAYER_COLORS } from '../../../ds/tokens'
import { fullclone } from '../../../lib/api'
import { useSystem } from '../../state/system'
import s from './PlayerDirectoryPage.module.css'

type Group = { key: string; name: string; members: number[] }
type Config = { name: string; race_label: string; controller_label: string; skin_label: string; fixed_start: boolean; x: number; y: number }
type Player = { id: number; slot: number; name: string; name_source: string; color: number | null; race_label: string; controller_label: string; state_label: string; slot_state?: number; start_index?: number; special?: string; team?: number | null; groups: string[]; config?: Config }
type Directory = { rows: Player[]; initial_groups: Group[]; current_groups: Group[]; source: string; issues: string[]; map_name: string; context: string; profile: string; read_at: string }

// Display swatches only; these do not set player colours or infer slot identity.
const COLORS = [...PLAYER_COLORS, '#9B0000', '#0000C3', '#00EAFF', '#BE00FE', '#EBCD87', '#F8A48B', '#BFFF80', '#DCB9EB', '#282828', '#EBF0FF', '#00781E', '#A46F33']
const COLOR_NAMES = ['红', '蓝', '青', '紫', '黄', '橙', '绿', '粉', '灰', '浅蓝', '深绿', '棕', '栗红', '深蓝', '蓝绿', '紫罗兰', '小麦', '桃色', '薄荷', '淡紫', '煤黑', '雪白', '祖母绿', '花生棕']
const teamText = (p: Player) => p.special ? `${p.special}（原始队伍值 ${p.team ?? '未确认'}）` : p.team == null ? '未确认' : p.team === -1 ? '未分配普通队伍（-1）' : `队伍 ${p.team + 1}`
const colorText = (value: number | null) => value == null ? '未确认' : COLOR_NAMES[value] ? `${value + 1} · ${COLOR_NAMES[value]}` : `原始值 ${value}`
function Color({ value }: { value: number | null }) {
  return <span className={s.color}><i aria-hidden="true" style={{ background: value == null ? 'transparent' : COLORS[value] || 'transparent' }} />{colorText(value)}</span>
}

export default function PlayerDirectoryPage() {
  const connected = useSystem(st => st.status.connected)
  const pid = useSystem(st => st.status.pid)
  const [data, setData] = useState<Directory | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [monitor, setMonitor] = useState(false)
  const [mode, setMode] = useState('initial')
  const [group, setGroup] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [activeOnly, setActiveOnly] = useState(false)
  const reading = useRef(false), generation = useRef(0), context = useRef('')
  useEffect(() => {
    generation.current++; setData(null); setError(''); setBusy(false); setMonitor(false); setGroup(''); setSelected(null)
    return () => { generation.current++ }
  }, [connected, pid])
  const read = async (refresh = false) => {
    if (!connected || reading.current) return
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
    if (!monitor || !connected) return
    // A slow map read never queues a second scan behind it.
    const timer = setInterval(() => void read(), 5000)
    return () => clearInterval(timer)
  }, [monitor, connected, pid]) // eslint-disable-line react-hooks/exhaustive-deps
  const groups = data ? mode === 'initial' ? data.initial_groups : data.current_groups : []
  const chosenGroup = groups.find(g => g.key === group)
  const query = search.trim().toLocaleLowerCase()
  const rows = (data?.rows || []).filter(p => (!chosenGroup || chosenGroup.members.includes(p.id)) && (!activeOnly || p.slot_state === 1 || p.special) && (!query || [p.slot, p.name, p.special, p.race_label, p.controller_label, ...p.groups].join(' ').toLocaleLowerCase().includes(query)))
  const player = data?.rows.find(p => p.id === selected)
  return <div className={s.page} data-testid="player-directory">
    <div className={s.toolbar}>
      <Button disabled={!connected || busy} onClick={() => void read()}>读取／刷新玩家信息</Button>
      <Button disabled={!connected || busy} onClick={() => void read(true)}>重新读取地图配置</Button>
      <Checkbox label="每5秒监视" checked={monitor} disabled={!connected} onChange={() => { setMonitor(!monitor); if (!monitor) void read() }} />
      <span role="status">{busy ? '正在只读核对玩家与地图配置…' : error || (data ? `${data.rows.length} 个槽位 · 读取于 ${data.read_at}` : connected ? '点击读取后显示当前地图玩家' : '请先连接游戏')}</span>
    </div>
    <p className={s.note}>只读查看。地图初始势力是编辑器分组；原生队伍是游戏读取值。大象“加入队伍”使用外交关系模板，不会改写这两个分组。</p>
    {data && <>
      <p className={s.source}>{data.map_name && `地图：${data.map_name}　`}配置来源：{data.source || '未确认'}<br />每个名字注明读取来源；颜色、种族、控制者等来自游戏进程。下方出生点和界面皮肤来自地图初始配置。</p>
      {data.issues.length > 0 && <details className={s.note}><summary>读取说明（{data.issues.length}）</summary><ul>{data.issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul></details>}
      <div className={s.body}>
        <nav className={s.groups} aria-label="队伍成员">
          <Select label="分组方式" aria-label="分组方式" value={mode} options={[{ value: 'initial', label: '地图初始势力' }, { value: 'current', label: '原生队伍（读取时）' }]} onChange={e => { setMode(e.target.value); setGroup('') }} />
          <Button size="sm" onClick={() => setGroup('')}>查看全部玩家</Button>
          {groups.map(g => <details key={g.key} open>
            <summary><button type="button" aria-pressed={g.key === group} onClick={e => { e.preventDefault(); setGroup(g.key) }}>{g.name}（{g.members.length}）</button></summary>
            <ul>{g.members.map(id => { const p = data.rows.find(r => r.id === id); return p && <li key={id}><button type="button" aria-current={p.id === selected ? 'true' : undefined} onClick={() => { setSelected(p.id); setGroup(g.key) }}><i className={s.chip} aria-hidden="true" style={{ background: p.color == null ? 'transparent' : COLORS[p.color] || 'transparent' }} />玩家 {p.slot} · {p.name}</button></li> })}</ul>
          </details>)}
        </nav>
        <article className={s.content}>
          <div className={s.toolbar}><TextField aria-label="搜索玩家信息" placeholder="搜索名字、槽位、种族或势力" value={search} onChange={e => setSearch(e.target.value)} />
            <Checkbox label="隐藏空槽和已离开玩家" checked={activeOnly} onChange={() => setActiveOnly(!activeOnly)} />
            <span>{chosenGroup?.name || '全部玩家'} · {rows.length} 项</span></div>
          <div className={s.table} tabIndex={0} aria-label="玩家信息表">
            <table><thead><tr><th>玩家</th><th>玩家名字</th><th>颜色</th><th>种族</th><th>控制者</th><th>槽位状态</th><th>原生队伍</th><th>地图初始势力</th></tr></thead>
              <tbody>{rows.map(p => <tr key={p.id} aria-selected={p.id === selected} onClick={() => setSelected(p.id)}>
                <td>{p.slot}</td><td><button type="button" title={p.name_source} onClick={() => setSelected(p.id)}>{p.name}</button><small>{p.special || p.name_source}</small></td>
                <td><Color value={p.color} /></td><td>{p.race_label}</td><td>{p.controller_label}</td><td>{p.state_label}</td><td>{teamText(p)}</td><td>{p.groups.join('、') || '未列入／未确认'}</td>
              </tr>)}</tbody></table>
            {!rows.length && <p>没有符合筛选条件的玩家。</p>}
          </div>
          {player ? <section className={s.detail} aria-label="玩家详情">
            <h2>玩家 {player.slot} · {player.name}</h2>
            <p>名字来源：{player.name_source}；{teamText(player)}；出生点索引：{player.start_index == null ? '未确认' : `${player.start_index}（游戏原始值）`}。</p>
            <h3>地图初始配置（非实时）</h3>
            {player.config ? <dl><dt>配置名字</dt><dd>{player.config.name || '未命名'}</dd><dt>控制者／种族</dt><dd>{player.config.controller_label}／{player.config.race_label}</dd><dt>固定开始点</dt><dd>{player.config.fixed_start ? '是' : '否'}</dd><dt>开始点坐标</dt><dd>X={Math.round(player.config.x)}，Y={Math.round(player.config.y)}（地图初始位置）</dd><dt>界面皮肤</dt><dd>{player.config.skin_label}</dd></dl> : <p>该槽位没有已确认的地图初始配置。</p>}
          </section> : <p className={s.note}>点击左侧玩家或表中名字，查看固定开始点、界面皮肤等详情。</p>}
        </article>
      </div>
    </>}
  </div>
}
