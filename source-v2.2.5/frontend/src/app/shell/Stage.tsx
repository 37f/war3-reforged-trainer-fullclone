import { Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { useSystem } from '../state/system'
import { usePageMemory } from '../state/pageMemory'
import { PAGES, isReady } from '../pages/registry'
import { chapterOf, pageMeta, type PageId } from '../routes'
import { usePageScrollMemory } from '../state/viewMemory'
import { useNav } from '../state/nav'
import { useT } from '../i18n'
import { Chat } from './Chat'
import s from './Stage.module.css'
import { FrontendReady } from '../startup'
import { useInterface } from '../state/interface'

export function Stage() {
  const t = useT()
  const page = useNav(st => st.page)
  const remember = usePageMemory(st => st.remember)
  const connection = useSystem(st => `${st.status.connected}:${st.status.pid}:${st.status.connectionId ?? ''}`)
  const [retained, setRetained] = useState<{ connection: string; pages: PageId[] }>({ connection, pages: [] })
  const cacheable = (id: PageId) => id === 'quests' && remember.quests || id === 'players' && remember.players
  const visited = retained.connection === connection ? retained.pages : []
  const pages = [...new Set([...visited.filter(cacheable), page])]
  useEffect(() => {
    setRetained(st => ({ connection, pages: [...new Set([...(st.connection === connection ? st.pages.filter(cacheable) : []), ...cacheable(page) ? [page] : []])] }))
  }, [page, connection, remember.quests, remember.players]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { usePageMemory.getState().resetMonitors() }, [connection])
  return (
    <main className={`ds-stage ${s.stage}`} data-testid="stage" data-page={page} data-ready={isReady(page)}>
      <PageHeader page={page} />
      {/* Page availability must not depend on an exit animation/rAF completing. */}
      {pages.map(id => {
        const Page = PAGES[id]
        return <RememberedPage key={(id === 'players' || id === 'quests') ? `${connection}:${id}` : id}
          id={id} active={id === page}>
          <Suspense fallback={<div role="status">{t('正在加载页面…')}</div>}><Page /><FrontendReady /></Suspense>
        </RememberedPage>
      })}
      <Chat />
    </main>
  )
}

function RememberedPage({ id, active, children }: { id: PageId; active: boolean; children: ReactNode }) {
  const content = useRef<HTMLDivElement>(null)
  usePageScrollMemory(content, id)
  return <div ref={content} data-page-view={id} hidden={!active} className={s.content}>{children}</div>
}

function PageHeader({ page }: { page: PageId }) {
  const t = useT()
  const setPage = useNav(st => st.setPage)
  const chapter = chapterOf(page)
  const mode = useInterface(st => st.mode)
  const classic = mode !== 'modern'
  if (mode === 'legacy19') return page === 'elephant' || page === 'hotkeys' ? (
    <nav className={s.legacySubtabs} aria-label={t('大象功能')} data-testid="legacy19-subtabs">
      {(['elephant', 'hotkeys'] as const).map(id => <button type="button" key={id} aria-current={id === page ? 'page' : undefined}
        onClick={() => setPage(id)}>{t(id === 'elephant' ? '功能面板' : '快捷键功能')}</button>)}
    </nav>
  ) : null
  return (
    <div className={s.header}>
      <h1 className={s.title}>{t(pageMeta(page).label)}</h1>
      {!classic && chapter.pages.length > 1 && (
        <nav className={s.tabs} aria-label={`${t(chapter.label)}${t('的页面')}`}>
          {chapter.pages.map(p => (
            <button
              key={p.id}
              type="button"
              className={s.tab}
              data-active={p.id === page || undefined}
              aria-current={p.id === page ? 'page' : undefined}
              data-testid={`page-${p.id}`}
              onClick={() => setPage(p.id)}
            >
              {t(p.label)}
            </button>
          ))}
        </nav>
      )}
    </div>
  )
}
