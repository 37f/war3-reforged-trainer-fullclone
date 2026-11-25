import { useEffect, useState, type ReactNode } from 'react'
import { Button, Checkbox, Select, TextArea, TextField, announce } from '../../../ds'
import { fullclone, type SelectedOwnerStatus, type TargetNames } from '../../../lib/api'
import { useSystem } from '../../state/system'
import { useNav } from '../../state/nav'
import { usePageMemory } from '../../state/pageMemory'
import { fill, useT } from '../../i18n'
import s from './FullClonePanel.module.css'
import OperationHistory from './OperationHistory'
import { PlayerNameSelect } from '../common/PlayerNameSelect'

type LocalAIStatus = {
  active: boolean; stopped: boolean; detail?: string; stockOpenings?: number; stockWaves?: number
  progress?: { mined: number; wood: number; built: number; spells: number; researched: number; creeps: number; trained: number; upgraded: number
    harvestNote: string; buildNote: string; researchNote: string; trainNote: string; destructibleNote?: string
    tactics: number; tacticsReady: number; tacticsNote: string
    buildStarted?: number; buildTimeouts?: number; revives?: number } | null
}
type HeroCandidate = { code: string; player: number; nameZh: string; nameEn: string }

export function useFullCloneOptions(watchAI = false) {
  const [options, setOptions] = useState<Record<string, any>>({})
  const [localAI, setLocalAI] = useState<LocalAIStatus>({ active: false, stopped: false })
  const [heroCandidates, setHeroCandidates] = useState<(HeroCandidate | null)[]>([null, null])
  useEffect(() => {
    let live = true
    const load = () => {
      void fullclone.settings().then(r => {
        if (!live) return
        setOptions(r.options)
        if (r.localAI) setLocalAI(r.localAI)
        if (r.heroCandidates) setHeroCandidates(r.heroCandidates)
      }).catch(() => {})
    }
    load(); window.addEventListener('fullclone-options', load)
    return () => { live = false; window.removeEventListener('fullclone-options', load) }
  }, [])
  useEffect(() => {
    if (!watchAI || !localAI.active) return
    let live = true
    const poll = async () => {
      try {
        const r = await fullclone.settings()
        if (live && r.localAI) setLocalAI(r.localAI)
      } catch { /* Retry the status query. The backend owns the game timer. */ }
      if (live) timer = setTimeout(() => void poll(), 1500)
    }
    let timer = setTimeout(() => void poll(), 1500)
    return () => { live = false; clearTimeout(timer) }
  }, [watchAI, localAI.active])
  const set = async (key: string, value: unknown) => {
    const r = await fullclone.set(key, value)
    setOptions(r.options); window.dispatchEvent(new Event('fullclone-options'))
  }
  return { options, set, localAI, setLocalAI, heroCandidates, setHeroCandidates }
}

const PLAYERS = [...Array.from({ length: 24 }, (_, i) => ({ value: String(i), label: `玩家 ${i + 1}` })),
  { value: '24', label: '中立敌对（玩家25）' }, { value: '27', label: '中立被动（玩家28）' }]
const TEAMS = [...Array.from({ length: 12 }, (_, i) => ({ value: String(i), label: `队伍 ${i + 1}` })),
  { value: '12', label: '中立敌对模板' }, { value: '13', label: '中立被动模板' }]
export function useTeamPlayerOptions(active: boolean) {
  const { connected, pid, language, connectionId } = useSystem(st => st.status)
  const connection = connectionId ?? pid
  const nameMode = usePageMemory(st => st.playerNameMode)
  const t = useT()
  const [snapshot, setSnapshot] = useState<{ connection: typeof connection; names: TargetNames } | null>(null)

  useEffect(() => {
    setSnapshot(null)
    if (!active || !connected) return
    let live = true
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const names = await fullclone.targetNames()
        if (live) setSnapshot({ connection, names })
      } catch { if (live) setSnapshot(null) }
      if (live) timer = setTimeout(() => void poll(), 5000)
    }
    void poll()
    return () => { live = false; clearTimeout(timer) }
  }, [active, connected, connection])

  const names = active && connected && snapshot?.connection === connection ? snapshot.names : undefined
  const labelOptions = (options: typeof PLAYERS, customNames?: Record<string, string>) => options.map(option => {
    const base = t(option.label)
    const name = customNames?.[option.value]?.trim()
    const label = name && name.replace(/\s/g, '').toLowerCase() !== base.replace(/\s/g, '').toLowerCase()
      ? base + (language === 'en' ? ' (' + name + ')' : '（' + name + '）')
      : base
    return { ...option, label }
  })
  const playerNames = nameMode === 'map' ? names?.mapPlayers : names?.players
  return {
    playerOptions: labelOptions(PLAYERS, playerNames), teamOptions: labelOptions(TEAMS, names?.teams),
    nameMode, playerNames, mapContext: names?.context,
  }
}

export const POINT_SPELLS = [
  { value: 'AUin', label: '地狱火 AUin' }, { value: 'AHbz', label: '暴风雪 AHbz' },
  { value: 'AHfs', label: '烈焰风暴 AHfs' }, { value: 'ANrf', label: '火焰雨 ANrf' },
]
export const ITEM_FILTERS = [
  { value: 'all', label: '全部物品' }, { value: 'include', label: '只聚集指定ID' },
  { value: 'exclude', label: '排除指定ID' },
]

export type FullCloneControls = { ownership: ReactNode; targets: ReactNode; unit: ReactNode; items: ReactNode }

// Presentation slots let the old layout reuse exactly the same controls, options
// and monitor state. Action dispatch and the game connection are shared.
export default function FullClonePanel({ layout }: { layout?: (controls: FullCloneControls) => ReactNode }) {
  const t = useT()
  const { options: o, set, localAI, setLocalAI, heroCandidates, setHeroCandidates } = useFullCloneOptions(true)
  const connected = useSystem(st => st.status.connected)
  const language = useSystem(st => st.status.language)
  const [busy, setBusy] = useState(false)
  const active = useNav(st => st.page) === 'elephant'
  const { playerOptions, teamOptions, nameMode, playerNames, mapContext } = useTeamPlayerOptions(active)
  const [controlTarget, setControlTarget] = useState({ slot: '', context: '' })
  const controlSlot = mapContext && controlTarget.context === mapContext ? controlTarget.slot : ''
  const [pending, setPending] = useState<{ action: string; seconds: number } | null>(null)
  const monitor = usePageMemory(st => st.ownerMonitor)
  const setMonitor = usePageMemory(st => st.setOwnerMonitor)
  const [owner, setOwner] = useState<SelectedOwnerStatus>({ message: '尚未读取选中玩家', owner: null })
  const readOwner = async () => {
    try { setOwner(await fullclone.owner()) }
    catch (e) { setOwner({ message: e instanceof Error ? e.message : String(e), owner: null }) }
  }
  const ownerName = owner.owner && owner.context === mapContext ? playerNames?.[owner.owner - 1] : undefined
  let ownerMessage = owner.message
  if (owner.owner && owner.owner <= 24 && owner.details && (ownerName || nameMode === 'map')) {
    const name = ownerName || (mapContext && owner.context === mapContext ? '地图未设置名称' : '名称暂无法读取')
    ownerMessage = '玩家 ' + owner.owner + '（' + name + '）：' + owner.details
  }
  useEffect(() => {
    if (!connected || !monitor) return
    let live = true, reading = false
    const poll = async () => {
      if (reading) return; reading = true
      try { const r = await fullclone.owner(); if (live) setOwner(r) }
      catch { if (live) setOwner({ message: '当前选中玩家无法读取', owner: null }) }
      finally { reading = false }
    }
    void poll(); const timer = setInterval(() => void poll(), 1000)
    return () => { live = false; clearInterval(timer) }
  }, [connected, monitor])
  const act = async (action: string) => {
    if (busy) return; setBusy(true)
    try {
      if (action === 'control_player') {
        if (controlSlot && mapContext) {
          const result = await fullclone.controlPlayer(Number(controlSlot), mapContext)
          announce(t(result.message))
        }
        return
      }
      const r = action === 'supply_save' ? await fullclone.saveSupplies() : await fullclone.action(action)
      announce(t(r.message))
      if (r.localAI) setLocalAI(r.localAI)
      else if (r.heroCandidates) setHeroCandidates(r.heroCandidates)
      else if (monitor && action !== 'supply_save') await readOwner()
    } catch {
      if (action.startsWith('swap_') || action.startsWith('hero_candidate'))
        window.dispatchEvent(new Event('fullclone-options'))
    }
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
  const playerSelect = (key: string) => <Select aria-label={t('目标玩家')} value={String(o[key] ?? 0)} options={playerOptions} onChange={e => void set(key, Number(e.target.value))} />
  const button = (action: string, label: string, disabled = false) => <Button size="sm" disabled={!connected || busy || !!pending || disabled} onClick={() => void act(action)}>{label}</Button>
  const candidateCount = connected ? heroCandidates.filter(Boolean).length : 0
  const swapPrefix = candidateCount ? 'swap_candidate_hero_skill_' : 'swap_hero_skill_'
  const aiFeatures = [['ai_combat', '自动接敌'], ['ai_harvest', '自动采集'],
    ['ai_build', '自动建造'], ['ai_spells', '英雄自动施法'],
    ['ai_research', '自动研究科技'], ['ai_creeps', '优先打野怪'], ['ai_train', '自动训练单位'],
    ['ai_team', '集结与回防'], ['ai_pickup', '自动拾取物品'],
    ['ai_destructibles', '攻击可破坏物'], ['ai_neutral_creatures', '攻击中立生物'],
    ['ai_neutral_buildings', '攻击中立建筑']] as const
  const aiEnabled = (key: string) => Boolean(o[key] ?? (key === 'ai_combat'))
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
      <div className={s.row}><PlayerNameSelect /></div>
      <div className={s.row}>{button('give_owner', t('把选中单位给指定玩家（Ctrl+I+U）'))}{playerSelect('target_player')}
        {button('restore_selected_owners', t('把选中单位恢复真正原玩家'))}
        {button('restore_all_owners', t('恢复所有真正原玩家'))}
      </div>
      <p>{t('归属恢复使用当前地图中首次转交前的记录。')}</p>
      <div className={s.row}>{button('toggle_owner_control', t('控制/恢复选中玩家（Ctrl+I+O，不改变阵营）'))}</div>
      <div className={s.row}>{button('control_player', t('控制/恢复玩家'), !controlSlot)}
        <Select aria-label={t('要控制或恢复的玩家')} disabled={!connected || !mapContext || busy} value={controlSlot}
          options={[{ value: '', label: t('选择玩家') }, ...playerOptions]}
          onChange={e => setControlTarget({ slot: e.target.value, context: mapContext || '' })} />
      </div>
      <div className={s.row}>{button('join_team', t('把选中玩家加入队伍（Ctrl+F1）'))}
        <Select aria-label={t('队伍')} value={String(o.team ?? 0)} options={teamOptions} onChange={e => void set('team', Number(e.target.value))} />
        {button('restore_team', t('把选中玩家恢复真正原队伍'))}
        {button('restore_all_teams', t('恢复所有玩家真正原队伍'))}
      </div>
      <p>{t('队伍功能套用外交关系模板；恢复使用当前地图首次切换前记录的双向关系。原生队伍编号单独显示。')}</p>
      <div className={s.row}><Button size="sm" disabled={!connected} onClick={() => void readOwner()}>{t('读取选中玩家与队伍')}</Button>
        <Checkbox label={t('每秒监视玩家名字和队伍')} checked={monitor} onChange={() => setMonitor(!monitor)} /></div>
      <p role="status">{t(ownerMessage)}</p>
      <Button size="sm" onClick={() => useNav.getState().setPage('players')}>{t('查看队伍与全部玩家')}</Button>
      <OperationHistory active={active} connected={connected} disabled={busy || !!pending}
        onUndo={() => { if (monitor) void readOwner() }} />
    </>,
    unit: <>
      <div className={s.row}>{button('replace_unit', t('替换单位（Ctrl+U+8）'))}<TextField aria-label={t('替换单位ID')} maxLength={4} value={String(o.replace_id ?? 'zhyd')} onChange={e => void set('replace_id', e.target.value)} /></div>
      <fieldset>
        <legend>{t('AI 托管（仅自己）· 实验性，谨慎操作')}</legend>
        <p>{t('托管仅指挥自己的单位。建造优先使用空闲工人，缺人时可调度正在采集的工人。')}</p>
        <div className={s.row}>
          {aiFeatures.map(([key, text]) => <Checkbox key={key} label={t(text)} checked={aiEnabled(key)}
            onChange={() => void set(key, !aiEnabled(key))} />)}
        </div>
        {aiEnabled('ai_train') && <>
          <p>{t('优先补工人和战斗单位。与自动建造一起开启时，四个原版种族会尝试补齐前置建筑、升本并扩充兵种。')}</p>
          <p>{t('英雄按本族名单抽选。升本后可训练不同英雄，阵亡英雄优先由祭坛复活。')}</p>
        </>}
        {aiEnabled('ai_team') && <p>{t('基地遇袭时优先回防。英雄和兵力就绪后成队推进，勾选「优先打野怪」时先打附近可见的野怪。')}</p>}
        <div className={s.row}>
          <label>{t('目标搜索范围')} <Select aria-label={t('目标搜索范围')} value={String(o.ai_radius ?? 900)}
            options={[900, 1600, 2400, 3200, 4000, 4800, 6400, 9600, 12800, 19200, 25600]
              .map(radius => ({value: String(radius), label: radius === 900 ? t('900（默认）') : String(radius)}))}
            onChange={e => void set('ai_radius', Number(e.target.value))} /></label>
        </div>
        <div className={s.row}>
          <Button size="sm" disabled={busy || !!pending || (!localAI.active &&
              (!connected || !aiFeatures.some(([key]) => aiEnabled(key))))}
            onClick={() => void act(localAI.active ? 'local_ai_stop' : 'local_ai_start')}>
            {localAI.active ? t('停止本方 AI 托管') : t('开启本方 AI 托管')}
          </Button>
          <span role="status">{localAI.active ? t('已开启本方 AI 托管') : localAI.stopped
            ? t('AI 托管已自动停止，确认当前地图后可重新开启。') : t('AI 托管未开启')}</span>
        </div>
        {localAI.stopped && localAI.detail && <p>{t(localAI.detail)}</p>}
        {localAI.active && localAI.progress && <div>
          <p>{fill(t('已下达指令 · 采金 {mined} · 伐木 {wood} · 建造 {built} · 施法 {spells}'), localAI.progress)}</p>
          {aiEnabled('ai_build') && <p>{fill(t('确认开工 {started} · 开工超时 {timeouts}'), {
            started: localAI.progress.buildStarted ?? 0, timeouts: localAI.progress.buildTimeouts ?? 0,
          })}</p>}
          {(aiEnabled('ai_research') || (aiEnabled('ai_creeps') && !aiEnabled('ai_team'))) &&
            <p>{fill(t('已下达指令 · 科技 {researched} · 打野 {creeps}'), localAI.progress)}</p>}
          {localAI.stockOpenings != null && <p>
            {localAI.stockOpenings > 0
              ? fill(t('已读取本机原版 AI 开局规则（{n}/4 种族）'), { n: localAI.stockOpenings })
              : t('本机原版 AI 开局规则未读出，当前使用内置生产顺序。')}
          </p>}
          {aiEnabled('ai_train') && <>
            <p>{fill(t('已下达训练指令 {trained} 次 · 主基地升级 {upgraded} 次'), localAI.progress)}</p>
            {!!localAI.progress.revives && <p>
              {fill(t('已下达英雄复活指令 {count} 次'), { count: localAI.progress.revives })}
            </p>}
            {localAI.progress.trainNote && <p>{t(localAI.progress.trainNote)}</p>}
          </>}
          {aiEnabled('ai_team') && localAI.stockWaves != null && <>
            <p>{localAI.stockWaves > 0
              ? fill(t('已读取本机原版 AI 出征门槛（{n}/4 种族）'), { n: localAI.stockWaves })
              : t('本机原版 AI 出征门槛未读出，当前使用内置门槛。')}</p>
            <p>{fill(t('编队指令 {tactics} · 就绪兵力 {tacticsReady}'), localAI.progress)}</p>
            <p>{t(localAI.progress.tacticsNote)}</p>
          </>}
          {localAI.progress.harvestNote && <p>{t(localAI.progress.harvestNote)}</p>}
          {localAI.progress.buildNote && <p>{t(localAI.progress.buildNote)}</p>}
          {localAI.progress.researchNote && <p>{t(localAI.progress.researchNote)}</p>}
          {localAI.progress.destructibleNote && <p>{t(localAI.progress.destructibleNote)}</p>}
        </div>}
      </fieldset>
      <fieldset>
        <legend>{t('英雄技能互换')}</legend>
        <p>{t('可逐个加入自己、友军、敌人或中立英雄。两个候选位都空时，也可以同时选中两名英雄交换。')}</p>
        <ol>
          {[1, 2].map(n => {
            const candidate = connected ? heroCandidates[n - 1] : null
            const name = candidate && (language === 'en' ? candidate.nameEn : candidate.nameZh)
            return <li key={n}>
              <div className={s.row}>
                {button(`hero_candidate_${n}`, fill(t('将选中英雄放入候选位 {n}'), { n }))}
                <span>{candidate
                  ? [name, candidate.code, fill(t('玩家 {n}'), { n: candidate.player })].filter(Boolean).join(' · ')
                  : t('空候选位')}</span>
              </div>
            </li>
          })}
        </ol>
        <div className={s.row}>
          {button('hero_candidates_clear', t('清空候选英雄'), candidateCount === 0)}
          {[1, 2, 3, 4].map(n => <span key={n}>{button(swapPrefix + n, fill(t('交换第 {n} 个技能'), { n }), candidateCount === 1)}</span>)}
          {button(swapPrefix + 'all', t('交换全部技能'), candidateCount === 1)}
          {button('restore_hero_skills', t('还原所有英雄技能'))}
        </div>
      </fieldset>
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
      <div className={s.row}><Select aria-label={t('物品聚集筛选')} value={String(o.item_filter_mode ?? 'all')}
        options={ITEM_FILTERS.map(option => ({ ...option, label: t(option.label) }))} onChange={e => void set('item_filter_mode', e.target.value)} />
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
        <div className={s.row}><Select aria-label={t('鼠标位置技能')} value={String(o.point_spell ?? 'AUin')}
          options={POINT_SPELLS.map(option => ({ ...option, label: t(option.label) }))} onChange={e => void set('point_spell', e.target.value)} />
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
