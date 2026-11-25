import { useEffect, useState } from 'react'
import { Button, Checkbox, Select, TextField, announce } from '../../../ds'
import { fullclone } from '../../../lib/api'
import { useSystem } from '../../state/system'
import { useNav } from '../../state/nav'
import { usePageMemory } from '../../state/pageMemory'
import { fill, useT } from '../../i18n'
import s from './QuestPage.module.css'

type Place = { index: number; label: string; labelEn?: string; enabled: boolean }
type Rule = { text: string; textEn?: string; label?: string; labelEn?: string; positions: Place[] }
type Quest = { key: string; title: string; kind: string; text: string; textEn?: string; description: string; entries: Place[]; conditions: Rule[]; state: string; stateReason: string }

export default function QuestPage() {
  const t = useT()
  const english = useSystem(st => st.status.language === 'en')
  const localText = (value?: string, translated?: string) => english && translated ? translated : t(value || '')
  const connected = useSystem(st => st.status.connected)
  const active = useNav(st => st.page === 'quests')
  const remember = usePageMemory(st => st.remember.quests)
  const [checking, setChecking] = useState(true)
  const [data, setData] = useState<any>({ status: 'idle', started: false, rows: [], chapters: [] })
  const [selected, setSelected] = useState('')
  const [locations, setLocations] = useState(false)
  const [path, setPath] = useState('')
  const [chapter, setChapter] = useState('')
  const [starting, setStarting] = useState(false)
  // Opening the page only reads an existing result; analysis starts on a click.
  useEffect(() => {
    if (!active) return
    setChecking(true)
    let live = true, reading = false
    const poll = async () => {
      if (reading) return; reading = true
      try { const r = await fullclone.quests(); if (live) setData(r) }
      catch { if (live) setData({ status: 'stale', started: true, rows: [], chapters: [], error: '无法核对当前地图，请重新检测' }) }
      finally { reading = false; if (live) setChecking(false) }
    }
    void poll(); const timer = setInterval(() => void poll(), 1000)
    return () => { live = false; clearInterval(timer) }
  }, [active])
  const busy = starting || ['reading', 'analyzing'].includes(data.status)
  const start = async (file = '') => {
    setStarting(true)
    try { await fullclone.scan(file, chapter); setData(await fullclone.quests()) } catch { /* API reports */ }
    finally { setStarting(false) }
  }
  const quests: Quest[] = data.rows || []
  const q = quests.find(r => r.key === selected) || quests[0]
  const jump = async (p: Place) => {
    if (!p.enabled || !connected || checking || !active || !data.canLocate) return
    try { const r = await fullclone.camera(p.index); announce(t(r.message)) } catch { /* API reports */ }
  }
  const selectQuest = (r: Quest) => {
    setSelected(r.key)
    if (!locations) return
    const candidates = ['未触发', '状态未确认'].includes(r.state)
      ? r.entries
      : r.conditions.flatMap(c => c.positions)
    const points = candidates.filter(p => p.enabled)
    if (points.length === 1) void jump(points[0])
  }
  const places = (list: Place[]) => <div className={s.places}>
    {list.length ? list.map(p => <Button key={p.index} size="sm" disabled={!p.enabled || !connected || checking || !data.canLocate} onClick={() => void jump(p)}>{localText(p.label, p.labelEn)}</Button>) : <span className={s.muted}>{t('无位置')}</span>}
  </div>
  return <div className={s.page} data-testid="quest-page">
    <div className={s.toolbar}>
      <Button disabled={!connected || busy} onClick={() => void start()}>{t(data.started ? '重新检测' : '开始检测')}</Button>
      <Checkbox label={t('记忆模式')} checked={remember} onChange={() => usePageMemory.getState().setRemember('quests', !remember)} />
      <Checkbox label={t('触发位置')} checked={locations} onChange={() => setLocations(!locations)} />
      <span role="status">{data.status === 'ready' && !busy ? fill(t('已检索 {n} 个任务'), { n: quests.length }) : t(busy ? '正在读取并分析地图脚本…' : data.status === 'idle' ? '点击开始检测后读取当前地图' : data.error || '请选择战役章节')}</span>
    </div>
    <details><summary>{t('只读分析指定文件（无法自动定位时使用）')}</summary>
      <div className={s.toolbar}><TextField aria-label={t('战役或地图路径')} placeholder={t('.w3n / .w3x / .w3m 完整路径')} value={path} onChange={e => setPath(e.target.value)} />
        <Button disabled={!path.trim() || busy} onClick={() => void start(path)}>{t('读取文件')}</Button></div>
      {data.chapters?.length > 0 && <Select aria-label={t('章节')} value={chapter} options={[{ value: '', label: t('请选择章节') }, ...data.chapters.map((p: string) => ({ value: p, label: p }))]} onChange={e => setChapter(e.target.value)} />}
      <p>{t('文件读取不执行地图脚本；未确认与当前地图一致时不开放视角跳转或运行状态匹配。')}</p>
    </details>
    {data.source && <p className={s.source}>{t('来源：')}{data.source}</p>}
    {data.notice && <p className={s.source} role="note">{t(data.notice)}</p>}
    <div className={s.body}>
      <nav aria-label={t('主线与支线任务')}><ul>{quests.map(r => <li key={r.key}>
        <button type="button" aria-current={q?.key === r.key ? 'true' : undefined} onClick={() => selectQuest(r)}>
          <span>{t(r.kind)} · {r.title || t('未命名任务')}</span><small title={t(r.stateReason)}>{t(r.state)}</small>
        </button></li>)}</ul></nav>
      <article>{q ? <>
        <h2>{q.title || t('未命名任务')}</h2><p title={t(q.stateReason)}>{t(q.kind)} · {t(q.state)}</p>
        {q.state === '状态未确认' && q.stateReason && <p className={s.source}>{t(q.stateReason)}</p>}
        <pre>{localText(q.text, q.textEn)}</pre>
        {locations && <section><h3>{t('触发前位置')}</h3>{places(q.entries)}
          {q.conditions.map((r, i) => <section key={i}><h3>{localText(r.label, r.labelEn)}</h3><pre>{localText(r.text, r.textEn)}</pre>{places(r.positions)}</section>)}
        </section>}
      </> : <p>{t('尚无任务检测结果。未解析的内容会明确提示，不推测任务已完成。')}</p>}
        {data.outcomes?.length > 0 && <details><summary>{t('整关胜利与失败条件')}</summary>{data.outcomes.map((r: Rule, i: number) => <section key={i}><pre>{localText(r.text, r.textEn)}</pre>{locations && places(r.positions)}</section>)}</details>}
        {data.issues?.length > 0 && <details><summary>{t('未完全解析的内容')}</summary><pre>{(data.issues as string[]).map(t).join('\n')}</pre></details>}
      </article>
    </div>
  </div>
}
