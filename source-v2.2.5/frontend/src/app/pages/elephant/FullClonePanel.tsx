import { useEffect, useState, type ReactNode } from 'react'
import { Button, Checkbox, Select, TextArea, TextField, announce } from '../../../ds'
import { fullclone } from '../../../lib/api'
import { useSystem } from '../../state/system'
import { useNav } from '../../state/nav'
import { usePageMemory } from '../../state/pageMemory'
import { fill, useT } from '../../i18n'
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
  const t = useT()
  const { options: o, set } = useFullCloneOptions()
  const connected = useSystem(st => st.status.connected)
  const [busy, setBusy] = useState(false)
  const active = useNav(st => st.page) === 'elephant'
  const [pending, setPending] = useState<{ action: string; seconds: number } | null>(null)
  const monitor = usePageMemory(st => st.ownerMonitor)
  const setMonitor = usePageMemory(st => st.setOwnerMonitor)
  const [owner, setOwner] = useState('尚未读取选中玩家')
  const readOwner = async () => { try { setOwner((await fullclone.owner()).message) } catch (e) { setOwner(e instanceof Error ? e.message : String(e)) } }
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
    try { const r = action === 'supply_save' ? await fullclone.saveSupplies() : await fullclone.action(action); announce(t(r.message)); if (monitor && action !== 'supply_save') await readOwner() } catch { /* shared API reports */ }
    finally { setBusy(false) }
  }
  // Keep mouse placement separate from execution. Leaving the page, changing
  // settings or disconnecting cancels an unsubmitted operation.
  useEffect(() => { setPending(null) }, [active, connected, o])
  useEffect(() => {
    if (!pending || !active || !connected) return
    const timer = setTimeout(() => {
      if (pending.seconds > 1) setPending({ ...pending, seconds: pending.seconds - 1 })
      else { setPending(null); void act(pending.action) }
    }, 1000)
    return () => clearTimeout(timer)
  }, [pending, active, connected])
  const place = (action: string) => { if (!busy && !pending) setPending({ action, seconds: 3 }) }
  const playerSelect = (key: string) => <Select aria-label={t('目标玩家')} value={String(o[key] ?? 0)} options={PLAYERS.map(p => ({ ...p, label: t(p.label) }))} onChange={e => void set(key, Number(e.target.value))} />
  const button = (action: string, label: string) => <Button size="sm" disabled={!connected || busy || !!pending} onClick={() => void act(action)}>{label}</Button>
  const controls: FullCloneControls = {
    ownership: <>
      <Checkbox label={t('启用面板复制归属（关闭＝作者逻辑）')} checked={!!o.owner_enabled} onChange={() => void set('owner_enabled', !o.owner_enabled)} />
      <div className={s.row}>
        {([['self', '给自己'], ['selected', '给选中单位所属玩家'], ['player', '给指定玩家']] as const).map(([v, label]) =>
          <label key={v}><input type="radio" name="fc-owner" checked={o.owner_mode === v} onChange={() => void set('owner_mode', v)} /> {t(label)}</label>)}
        {playerSelect('owner_player')}
      </div>
      <p>{t('开关控制复制单位、大量复制和呼叫增援。Ctrl+A 始终给自己；关闭时 Ctrl+B 与大量复制保留源归属。')}</p>
      <div className={s.row}>{button('clone', t('复制选中单位（Ctrl+B）'))}{button('mass_clone', t('大量复制（Ctrl+N）'))}</div>
      <div className={s.row}><Select aria-label={t('大量复制阵型')} value={String(o.formation ?? 'original')} options={[
        { value: 'original', label: t('原排列') }, { value: 'square', label: t('方阵') }, { value: 'ring', label: t('圆环') },
        { value: 'line', label: t('直线') }, { value: 'scatter', label: t('分散') },
      ]} onChange={e => void set('formation', e.target.value)} />
      <TextField aria-label={t('复制阵型间距')} value={String(o.formation_gap ?? '128')} disabled={(o.formation ?? 'original') === 'original'} onChange={e => void set('formation_gap', e.target.value)} /></div>
      <p>{t('阵型以鼠标为中心，间距32至2048，服从原归属开关。新阵型先支持单选源单位，多选请使用原排列；游戏避障可能微调实际落点。')}</p>
    </>,
    targets: <>
      <div className={s.row}>{button('give_owner', t('把单位给指定玩家（Ctrl+I+U）'))}{playerSelect('target_player')}</div>
      <div className={s.row}>{button('toggle_owner_control', t('控制/恢复选中玩家（Ctrl+I+O，不改变阵营）'))}</div>
      <div className={s.row}>{button('join_team', t('把选中玩家加入队伍（Ctrl+F1）'))}
        <Select aria-label={t('队伍')} value={String(o.team ?? 0)} options={TEAMS.map(team => ({ ...team, label: t(team.label) }))} onChange={e => void set('team', Number(e.target.value))} />
        {button('restore_team', t('恢复真正原队伍'))}
        {button('restore_all_teams', t('恢复所有玩家真正原队伍'))}
      </div>
      <p>{t('队伍功能套用外交关系模板；恢复使用当前地图首次切换前记录的双向关系。原生队伍编号单独显示。')}</p>
      <div className={s.row}><Button size="sm" disabled={!connected} onClick={() => void readOwner()}>{t('读取选中玩家与队伍')}</Button>
        <Checkbox label={t('每秒监视玩家名字和队伍')} checked={monitor} onChange={() => setMonitor(!monitor)} /></div>
      <p role="status">{t(owner)}</p>
      <Button size="sm" onClick={() => useNav.getState().setPage('players')}>{t('查看队伍与全部玩家')}</Button>
    </>,
    unit: <>
      <div className={s.row}>{button('replace_unit', t('替换单位（Ctrl+U+8）'))}<TextField aria-label={t('替换单位ID')} maxLength={4} value={String(o.replace_id ?? 'zhyd')} onChange={e => void set('replace_id', e.target.value)} /></div>
      <div className={s.row}>{button('fill_life_mana', t('单位生命魔法全满'))}{button('revive_owner_heroes', t('复活选中玩家阵亡英雄（Ctrl+F+H）'))}</div>
      <div className={s.row}>{button('fill_owner_life_mana', t('选中玩家全军生命魔法全满（Ctrl+空格）'))}
        <Select aria-label={t('全军补满范围')} value={String(o.army_scope ?? 'all')} options={[
          { value: 'all', label: t('全部单位（含建筑）') }, { value: 'heroes', label: t('仅英雄') },
          { value: 'nonheroes', label: t('仅非英雄（含建筑）') },
        ]} onChange={e => void set('army_scope', e.target.value)} />
      </div>
      <p>{t('全军补满以当前选中单位的所属玩家为准，处理存活且未被地图隐藏的单位；不复活、不修改生命魔法上限。')}</p>
      <fieldset><legend>{t('冻结与恢复部队')}</legend>
        <div className={s.row}>{button('freeze_owner', t('冻结／恢复选中玩家部队'))}
          <Select aria-label={t('冻结部队范围')} value={String(o.freeze_scope ?? 'all')} options={[
            { value: 'all', label: t('全部部队') }, { value: 'heroes', label: t('仅英雄') }, { value: 'nonheroes', label: t('仅非英雄') },
          ]} onChange={e => void set('freeze_scope', e.target.value)} />
        </div>
        <Checkbox label={t('冻结包含建筑')} checked={!!o.freeze_buildings} onChange={() => void set('freeze_buildings', !o.freeze_buildings)} />
        <div className={s.row}>{button('restore_all_frozen', t('恢复本次冻结的所有部队'))}</div>
        <p>{t('再次执行按首次记录恢复，保留地图原本的暂停状态；跳过死亡、易主或身份变化的单位。每玩家最多4096个目标。关闭修改器或重开游戏前请先恢复。')}</p>
      </fieldset>
      <div className={s.row}><Select aria-label={t('颜色')} value={String(o.color ?? 0)} options={PLAYERS.slice(0, 24).map((p, i) => ({ value: p.value, label: fill(t('颜色 {n}'), { n: i + 1 }) }))} onChange={e => void set('color', Number(e.target.value))} />{button('unit_color', t('设置单位颜色'))}{button('player_color', t('设置玩家颜色'))}</div>
      <Checkbox label={t('Ctrl+Q 使用自定义等级（不勾选：每次升1级）')} checked={!!o.hero_custom} onChange={() => void set('hero_custom', !o.hero_custom)} />
      <Checkbox label={t('Alt+Q 使用自定义属性（不勾选：永久三围各加2）')} checked={!!o.attributes_custom} onChange={() => void set('attributes_custom', !o.attributes_custom)} />
    </>,
    items: <>
      <div className={s.row}>{button('gold_mine', t('设置金矿黄金（Alt+空格）'))}<TextField aria-label={t('金矿黄金')} value={String(o.mine_amount ?? '100000')} onChange={e => void set('mine_amount', e.target.value)} /></div>
      <div className={s.row}>{button('gather_ground_items', t('聚集全图地面物品（Alt+F2）'))}</div>
      <div className={s.row}><Select aria-label={t('物品聚集筛选')} value={String(o.item_filter_mode ?? 'all')} options={[
          { value: 'all', label: t('全部物品') }, { value: 'include', label: t('只聚集指定ID') }, { value: 'exclude', label: t('排除指定ID') },
        ]} onChange={e => void set('item_filter_mode', e.target.value)} />
        <TextField aria-label={t('物品ID列表')} maxLength={128} placeholder="ratf I000" disabled={(o.item_filter_mode ?? 'all') === 'all'}
          value={String(o.item_filter_ids ?? '')} onChange={e => void set('item_filter_ids', e.target.value)} />
      </div>
      <p>{t('物品ID区分大小写，用空格、逗号或分号分隔。Alt+F2使用此筛选；未匹配到物品时不移动，不会退回聚集全部。')}</p>
      <p>{t('鼠标放在游戏地面后按快捷键。地狱火固定归自己；物品移动原实例，背包、商店库存及隐藏物品除外。')}</p>
      <fieldset><legend>{t('自定义补给包')}</legend>
        <div className={s.row}><Select aria-label={t('补给包方案')} value={String(o.supply_slot ?? '1')} options={['1','2','3'].map(i => ({ value: i, label: `${i} · ${t(o[`supply_name_${i}`] ?? fill(t('补给包{n}'), { n: i }))}` }))} onChange={e => void set('supply_slot', e.target.value)} />
          <TextField aria-label={t('补给包名称')} maxLength={24} value={String(o[`supply_name_${o.supply_slot ?? '1'}`] ?? '')} onChange={e => void set(`supply_name_${o.supply_slot ?? '1'}`, e.target.value)} />
        </div>
        <TextArea aria-label={t('补给包物品清单')} rows={4} maxLength={2048} placeholder={'phea 2 1\npman 2 1'} value={String(o[`supply_text_${o.supply_slot ?? '1'}`] ?? '')} onChange={e => void set(`supply_text_${o.supply_slot ?? '1'}`, e.target.value)} />
        <p>{t('每行：物品ID 数量 [使用次数]。省略次数保留物品默认值，最多32个物品；给英雄时只操作单选存活英雄的经典背包，必须有足够空位。')}</p>
        <div className={s.row}><Button size="sm" disabled={busy || !!pending} onClick={() => void act('supply_save')}>{t('保存三组补给包')}</Button>
          <Select aria-label={t('补给投放方式')} value={String(o.supply_target ?? 'hero')} options={[{ value: 'hero', label: t('给选中英雄') }, { value: 'ground', label: t('投放到鼠标地面') }]} onChange={e => void set('supply_target', e.target.value)} />
          <Button size="sm" disabled={!connected || busy || !!pending} onClick={() => (o.supply_target ?? 'hero') === 'ground' ? place('supply_deliver') : void act('supply_deliver')}>{t('投放补给包')}</Button>
        </div>
      </fieldset>
      <fieldset><legend>{t('鼠标位置技能')}</legend>
        <div className={s.row}><Select aria-label={t('鼠标位置技能')} value={String(o.point_spell ?? 'AUin')} options={[
          { value: 'AUin', label: t('地狱火 AUin') }, { value: 'AHbz', label: t('暴风雪 AHbz') },
          { value: 'AHfs', label: t('烈焰风暴 AHfs') }, { value: 'ANrf', label: t('火焰雨 ANrf') },
        ]} onChange={e => void set('point_spell', e.target.value)} />
          <Button size="sm" disabled={!connected || busy || !!pending} onClick={() => place('point_spell')}>{t('释放到鼠标位置（Ctrl+F2）')}</Button>
        </div>
        <p>{t('固定归自己，使用透明载体和真实技能命令。地狱火沿用原入口；新增三个技能仍需在具体地图核对实际效果，地图可能覆盖技能定义。')}</p>
      </fieldset>
      {pending && <div role="status" className={s.row}>{fill(t('请将鼠标放到游戏地面，{n}秒后执行。'), { n: pending.seconds })}<Button size="sm" onClick={() => setPending(null)}>{t('取消本次放置')}</Button></div>}
    </>,
  }
  if (layout) return layout(controls)
  return <section className={s.panel} aria-label={t('FullClone 扩展')}>
    <h2>{t('FullClone 扩展')}</h2>
    <fieldset><legend>{t('复制与创建归属')}</legend>{controls.ownership}</fieldset>
    <fieldset><legend>{t('目标玩家')}</legend>{controls.targets}</fieldset>
    <fieldset><legend>{t('单位与英雄')}</legend>{controls.unit}</fieldset>
    <fieldset><legend>{t('金矿、地狱火与地面物品')}</legend>{controls.items}</fieldset>
  </section>
}
