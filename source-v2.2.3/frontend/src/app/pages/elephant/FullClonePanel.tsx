import { useEffect, useState, type ReactNode } from 'react'
import { Button, Checkbox, Select, TextField, announce } from '../../../ds'
import { fullclone } from '../../../lib/api'
import { useSystem } from '../../state/system'
import { useNav } from '../../state/nav'
import s from './FullClonePanel.module.css'

export function useFullCloneOptions() {
  const [options, setOptions] = useState<Record<string, any>>({})
  useEffect(() => {
    let live = true
    const load = () => { void fullclone.settings().then(r => { if (live) setOptions(r.options) }).catch(() => {}) }
    load(); window.addEventListener('fullclone-options', load)
    return () => { live = false; window.removeEventListener('fullclone-options', load) }
  }, [])
  const set = async (key: string, value: unknown) => {
    const r = await fullclone.set(key, value)
    setOptions(r.options); window.dispatchEvent(new Event('fullclone-options'))
  }
  return { options, set }
}

const PLAYERS = [...Array.from({ length: 24 }, (_, i) => ({ value: String(i), label: `玩家 ${i + 1}` })),
  { value: '24', label: '中立敌对（玩家25）' }, { value: '27', label: '中立被动（玩家28）' }]
const TEAMS = [...Array.from({ length: 12 }, (_, i) => ({ value: String(i), label: `队伍 ${i + 1}` })),
  { value: '12', label: '中立敌对模板' }, { value: '13', label: '中立被动模板' }]

export type FullCloneControls = { ownership: ReactNode; targets: ReactNode; unit: ReactNode; items: ReactNode }

// Presentation slots let the old layout reuse exactly the same controls, options
// and monitor state. Action dispatch and the game connection are shared.
export default function FullClonePanel({ layout }: { layout?: (controls: FullCloneControls) => ReactNode }) {
  const { options: o, set } = useFullCloneOptions()
  const connected = useSystem(st => st.status.connected)
  const [busy, setBusy] = useState(false)
  const [monitor, setMonitor] = useState(false)
  const [owner, setOwner] = useState('尚未读取选中玩家')
  const readOwner = async () => { try { setOwner((await fullclone.owner()).message) } catch (e) { setOwner(String(e)) } }
  useEffect(() => {
    if (!connected || !monitor) return
    let live = true, reading = false
    const poll = async () => {
      if (reading) return; reading = true
      try { const r = await fullclone.owner(); if (live) setOwner(r.message) } catch { if (live) setOwner('当前选中玩家无法读取') }
      finally { reading = false }
    }
    void poll(); const timer = setInterval(() => void poll(), 1000)
    return () => { live = false; clearInterval(timer) }
  }, [connected, monitor])
  const act = async (action: string) => {
    if (busy) return; setBusy(true)
    try { const r = await fullclone.action(action); announce(r.message); if (monitor) await readOwner() } catch { /* shared API reports */ }
    finally { setBusy(false) }
  }
  const playerSelect = (key: string) => <Select aria-label="目标玩家" value={String(o[key] ?? 0)} options={PLAYERS} onChange={e => void set(key, Number(e.target.value))} />
  const button = (action: string, label: string) => <Button size="sm" disabled={!connected || busy} onClick={() => void act(action)}>{label}</Button>
  const controls: FullCloneControls = {
    ownership: <>
      <Checkbox label="启用面板复制归属（关闭＝作者逻辑）" checked={!!o.owner_enabled} onChange={() => void set('owner_enabled', !o.owner_enabled)} />
      <div className={s.row}>
        {([['self', '给自己'], ['selected', '给选中单位所属玩家'], ['player', '给指定玩家']] as const).map(([v, label]) =>
          <label key={v}><input type="radio" name="fc-owner" checked={o.owner_mode === v} onChange={() => void set('owner_mode', v)} /> {label}</label>)}
        {playerSelect('owner_player')}
      </div>
      <p>开关控制复制单位、大量复制和呼叫增援。Ctrl+A 始终给自己；关闭时 Ctrl+B 与大量复制保留源归属。</p>
      <div className={s.row}>{button('clone', '复制选中单位（Ctrl+B）')}{button('mass_clone', '大量复制（Ctrl+N）')}</div>
    </>,
    targets: <>
      <div className={s.row}>{button('give_owner', '把单位给指定玩家（Ctrl+I+U）')}{playerSelect('target_player')}</div>
      <div className={s.row}>{button('toggle_owner_control', '控制/恢复选中玩家（Ctrl+I+O，不改变阵营）')}</div>
      <div className={s.row}>{button('join_team', '把选中玩家加入队伍（Ctrl+F1）')}
        <Select aria-label="队伍" value={String(o.team ?? 0)} options={TEAMS} onChange={e => void set('team', Number(e.target.value))} />
        {button('restore_team', '恢复真正原队伍')}
      </div>
      <p>队伍功能套用外交关系模板；恢复使用当前地图首次切换前记录的双向关系。原生队伍编号单独显示。</p>
      <div className={s.row}><Button size="sm" disabled={!connected} onClick={() => void readOwner()}>读取选中玩家与队伍</Button>
        <Checkbox label="每秒监视玩家名字和队伍" checked={monitor} onChange={() => setMonitor(!monitor)} /></div>
      <p role="status">{owner}</p>
      <Button size="sm" onClick={() => useNav.getState().setPage('players')}>查看队伍与全部玩家</Button>
    </>,
    unit: <>
      <div className={s.row}>{button('replace_unit', '替换单位（Ctrl+U+8）')}<TextField aria-label="替换单位ID" maxLength={4} value={String(o.replace_id ?? 'zhyd')} onChange={e => void set('replace_id', e.target.value)} /></div>
      <div className={s.row}>{button('fill_life_mana', '单位生命魔法全满（Ctrl+空格）')}{button('revive_owner_heroes', '复活选中玩家阵亡英雄（Ctrl+F+H）')}</div>
      <div className={s.row}><Select aria-label="颜色" value={String(o.color ?? 0)} options={PLAYERS.slice(0, 24).map((p, i) => ({ value: p.value, label: `颜色 ${i + 1}` }))} onChange={e => void set('color', Number(e.target.value))} />{button('unit_color', '设置单位颜色')}{button('player_color', '设置玩家颜色')}</div>
      <Checkbox label="Ctrl+Q 使用自定义等级（不勾选：每次升1级）" checked={!!o.hero_custom} onChange={() => void set('hero_custom', !o.hero_custom)} />
      <Checkbox label="Alt+Q 使用自定义属性（不勾选：永久三围各加2）" checked={!!o.attributes_custom} onChange={() => void set('attributes_custom', !o.attributes_custom)} />
    </>,
    items: <>
      <div className={s.row}>{button('gold_mine', '设置金矿黄金（Alt+空格）')}<TextField aria-label="金矿黄金" value={String(o.mine_amount ?? '100000')} onChange={e => void set('mine_amount', e.target.value)} /></div>
      <div className={s.row}>{button('infernal', '释放地狱火 AUin（Ctrl+F2）')}{button('gather_ground_items', '聚集全图地面物品（Alt+F2）')}</div>
      <p>鼠标放在游戏地面后按快捷键。地狱火固定归自己；物品移动原实例，背包、商店库存及隐藏物品除外。</p>
    </>,
  }
  if (layout) return layout(controls)
  return <section className={s.panel} aria-label="FullClone 扩展">
    <h2>FullClone 扩展</h2>
    <fieldset><legend>复制与创建归属</legend>{controls.ownership}</fieldset>
    <fieldset><legend>目标玩家</legend>{controls.targets}</fieldset>
    <fieldset><legend>单位与英雄</legend>{controls.unit}</fieldset>
    <fieldset><legend>金矿、地狱火与地面物品</legend>{controls.items}</fieldset>
  </section>
}
