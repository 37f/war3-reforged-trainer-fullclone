import { useEffect, useState, type KeyboardEvent } from 'react'
import { Button, Checkbox, TextField } from '../../ds'
import { PAGES, type PageId } from '../routes'
import { useNav } from '../state/nav'
import { useSystem } from '../state/system'
import { useUnit } from '../state/unit'
import { useT } from '../i18n'
import { SystemMenu } from './SystemMenu'
import { InterfaceSwitch } from './InterfaceSwitch'
import s from './ClassicHeader.module.css'

export function ClassicHeader() {
  const t = useT()
  const { status, bridgeReady, connecting, connect, setHotkeysEnabled } = useSystem()
  const { reading, readAll } = useUnit()
  const [pid, setPid] = useState('')
  const connectGame = () => void connect(pid.trim() ? Number.parseInt(pid, 10) : null)
  return <header className={s.header} data-testid="classic-header">
    <Button size="sm" disabled={!bridgeReady || connecting} onClick={connectGame} data-testid="connect-refresh">{t('连接/刷新')}</Button>
    <Button size="sm" disabled={!status.connected || reading} onClick={() => void readAll()} data-testid="global-read-units">{t('读取全部单位')} (Ctrl+F11)</Button>
    <Checkbox label={t('启用全局快捷键')} checked={status.hotkeysEnabled} disabled={!bridgeReady} onChange={e => void setHotkeysEnabled(e.target.checked)} />
    <label className={s.pid}>PID <TextField aria-label="PID" value={pid} placeholder={status.pid ? String(status.pid) : t('自动检测')} inputMode="numeric"
      onChange={e => setPid(e.target.value.replace(/\D/g, ''))} onKeyDown={e => { if (e.key === 'Enter') connectGame() }} /></label>
    <span className={s.status} title={status.statusMessage}>{t(status.statusMessage)}</span>
    <InterfaceSwitch />
    <SystemMenu />
  </header>
}

export function ClassicTabs() {
  const t = useT()
  const { page, setPage } = useNav()
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = e.key === 'ArrowRight' ? (index + 1) % PAGES.length : e.key === 'ArrowLeft' ? (index + PAGES.length - 1) % PAGES.length : e.key === 'Home' ? 0 : e.key === 'End' ? PAGES.length - 1 : -1
    if (next < 0) return
    e.preventDefault(); setPage(PAGES[next].id)
    document.querySelector<HTMLButtonElement>(`[data-classic-page="${PAGES[next].id}"]`)?.focus()
  }
  return <nav className={s.tabs} role="tablist" aria-label={t('功能标签页')} data-testid="classic-tabs">
    {PAGES.map((p, i) => <button type="button" role="tab" key={p.id} className={s.tab} data-classic-page={p.id}
      aria-selected={p.id === page} tabIndex={p.id === page ? 0 : -1} onClick={() => setPage(p.id)} onKeyDown={e => onKey(e, i)}>
      {t(p.id === 'elephant' ? '大象功能' : p.id === 'hotkeys' ? '快捷键功能' : p.label)}
    </button>)}
  </nav>
}

// R31.5: match the 1.0.19 tab order, retaining newer pages at the end.
export function Legacy19Tabs() {
  const t = useT()
  const { page, setPage } = useNav()
  const [kind, setKind] = useState(() => localStorage.getItem('war3-catalog-kind') || 'item')
  useEffect(() => {
    const sync = () => setKind(localStorage.getItem('war3-catalog-kind') || 'item')
    window.addEventListener('war3-catalog-kind', sync)
    return () => window.removeEventListener('war3-catalog-kind', sync)
  }, [])
  const first: { id: PageId; label: string; kind?: string }[] = [
    { id: 'resources', label: '玩家资源' }, { id: 'players', label: '队伍与玩家' }, { id: 'unit', label: '选中单位' },
    { id: 'locks', label: '锁定列表' }, { id: 'ability_fields', label: '技能字段' },
    { id: 'item_fields', label: '物品字段' }, { id: 'elephant', label: '大象功能' },
    { id: 'catalogs', label: '物品 ID', kind: 'item' }, { id: 'catalogs', label: '技能 ID', kind: 'ability' },
    { id: 'catalogs', label: '单位 ID', kind: 'unit' },
    { id: 'map_catalog', label: '自定义地图数据' }, { id: 'quests', label: '任务与条件' },
  ]
  const entries: typeof first = [...first, ...PAGES.filter(p => !first.some(f => f.id === p.id) && p.id !== 'hotkeys')]
  const active = (id: PageId, catalog?: string) => id === 'elephant' ? page === 'elephant' || page === 'hotkeys'
    : id === page && (!catalog || kind === catalog || (kind === 'upgrade' && catalog === 'unit'))
  const select = (entry: typeof entries[number]) => {
    if (entry.kind) {
      localStorage.setItem('war3-catalog-kind', entry.kind)
      window.dispatchEvent(new Event('war3-catalog-kind'))
    }
    setPage(entry.id)
  }
  return <nav className={s.tabs} role="tablist" aria-label={t('1.0.19 功能标签页')} data-testid="legacy19-tabs">
    {entries.map((entry, i) => <button type="button" role="tab" key={`${entry.id}-${entry.kind || ''}`} className={s.tab}
      data-legacy19-page={entry.id} data-catalog-kind={entry.kind} aria-selected={active(entry.id, entry.kind)}
      tabIndex={active(entry.id, entry.kind) ? 0 : -1} onClick={() => select(entry)} onKeyDown={e => {
        const next = e.key === 'ArrowRight' ? (i + 1) % entries.length : e.key === 'ArrowLeft' ? (i + entries.length - 1) % entries.length
          : e.key === 'Home' ? 0 : e.key === 'End' ? entries.length - 1 : -1
        if (next < 0) return
        e.preventDefault(); select(entries[next]); e.currentTarget.parentElement?.querySelectorAll('button')[next]?.focus()
      }}>{t(entry.label)}</button>)}
  </nav>
}
