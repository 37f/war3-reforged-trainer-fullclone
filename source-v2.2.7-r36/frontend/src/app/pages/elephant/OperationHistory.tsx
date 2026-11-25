import { useEffect, useRef, useState } from 'react'
import { Button, announce } from '../../../ds'
import { fullclone, type OperationHistoryEntry } from '../../../lib/api'
import { fill, useT } from '../../i18n'
import { useSystem } from '../../state/system'
import s from './FullClonePanel.module.css'

const STATUS: Record<string, string> = {
  pending: '可撤销',
  undone: '已撤销',
  newer: '此目标有更新的记录，请先撤销更新的操作',
  superseded: '已有恢复或未确认的修改，此项已失效',
  unit_changed: '单位已失效或身份无法核对',
  owner_changed: '单位归属已变化',
  player_unavailable: '玩家槽位无法核对',
  relations_changed: '当前外交关系已变化',
  unconfirmed: '结果未确认，请核对游戏',
}

export default function OperationHistory({ active, connected, disabled, onUndo }: {
  active: boolean; connected: boolean; disabled: boolean; onUndo: () => void
}) {
  const t = useT()
  const pid = useSystem(st => st.status.pid)
  const locale = useSystem(st => st.status.language)
  const [open, setOpen] = useState(false)
  const [available, setAvailable] = useState<boolean | null>(null)
  const [entries, setEntries] = useState<OperationHistoryEntry[]>([])
  const [undoing, setUndoing] = useState(false)
  const updating = useRef(false), generation = useRef(0)

  useEffect(() => {
    const version = ++generation.current
    setEntries([]); setAvailable(null)
    if (!active || !open || !connected) return
    let reading = false
    const refresh = async () => {
      if (reading || updating.current) return
      reading = true
      try {
        const result = await fullclone.history()
        if (generation.current === version && !updating.current) {
          setEntries(result.entries); setAvailable(result.available)
        }
      } catch {
        if (generation.current === version && !updating.current) { setEntries([]); setAvailable(false) }
      } finally { reading = false }
    }
    void refresh()
    const timer = setInterval(() => void refresh(), 2500)
    return () => { ++generation.current; clearInterval(timer) }
  }, [active, connected, open, pid])

  const undo = async (id: string) => {
    if (updating.current || disabled || !connected || !active) return
    updating.current = true; setUndoing(true)
    const version = generation.current
    try {
      const result = await fullclone.undo(id)
      if (result.team) window.dispatchEvent(new CustomEvent('fullclone-team-undone', { detail: result.team }))
      if (generation.current !== version) return
      setEntries(result.entries)
      if (result.undone) onUndo()
      announce(result.undone ? fill(t('已撤销 {n} 项，请查看逐项结果'), { n: result.undone }) : t('当前没有可撤销的目标'))
    } catch { /* the shared backend reports errors */ }
    finally { updating.current = false; setUndoing(false) }
  }

  const player = (slot: number) => t(slot === 24 ? '中立敌对（玩家25）' : slot === 27 ? '中立被动（玩家28）' : `玩家 ${slot + 1}`)
  const template = (id?: number | null) => t(id == null ? '未套用外交模板' : id === 12 ? '中立敌对模板' : id === 13 ? '中立被动模板' : `队伍 ${id + 1}`)
  const date = (value: number) => new Date(value).toLocaleTimeString(locale === 'en' ? 'en-US' : 'zh-CN')
  return <details onToggle={event => { if (event.target === event.currentTarget) setOpen(event.currentTarget.open) }}>
    <summary>{t('操作历史')}</summary>
    <p>{t('显示当前地图最近 30 次单位转交和外交模板操作。展开条目查看每个目标。')}</p>
    {!connected || available === false ? <p>{t('进入地图后可读取操作历史。')}</p>
      : available === null ? <p>{t('正在读取操作历史…')}</p>
      : !entries.length ? <p>{t('当前地图还没有操作记录。')}</p> : <ol className={s.history}>
        {entries.map(entry => {
          const eligible = entry.targets.some(target => target.status === 'pending')
          return <li key={entry.id}>
            <div className={s.row}>
              <span>{date(entry.time)} · {entry.kind === 'owner' ? t('转交单位') : t('套用外交模板')}</span>
              <Button size="sm" disabled={disabled || undoing || !eligible} onClick={() => void undo(entry.id)}>{t('撤销这次操作')}</Button>
            </div>
            <details>
              <summary>{fill(t('查看 {n} 个目标'), { n: entry.targets.length })}</summary>
              <ul>{entry.targets.map((target, index) => <li key={index}>
                {target.player != null ? `${player(target.player)} · ${template(target.source)} → ${template(target.destination)}`
                  : `${target.unit || t('单位')}${target.source != null && target.destination != null ? ` · ${player(target.source)} → ${player(target.destination)}` : ''}`}
                {' · '}{t(STATUS[target.status] || '未确认')}
              </li>)}</ul>
            </details>
          </li>
        })}
      </ol>}
  </details>
}
