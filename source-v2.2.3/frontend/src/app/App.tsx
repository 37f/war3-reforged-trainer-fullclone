import { useEffect } from 'react'
import { useShellHotkeys } from './hotkeys'
import { startSync } from './state/sync'
import { Console } from './shell/Console'
import { NoticeDialog } from './shell/NoticeDialog'
import { Stage } from './shell/Stage'
import { TopBand } from './shell/TopBand'
import { ClassicHeader, ClassicTabs, Legacy19Tabs } from './shell/ClassicHeader'
import { useInterface } from './state/interface'
import s from './App.module.css'
import './classic.css'

/** Top band, stage, console: the three rows of the redesign (plan, section 4.1). */
export function App() {
  useEffect(() => startSync(), [])
  useEffect(() => useInterface.getState().hydrate(), [])
  useShellHotkeys()
  const mode = useInterface(st => st.mode)
  const classic = mode !== 'modern'
  return (
    <div className={`${s.app} ${classic ? s.classic : ''}`} data-testid="app">
      {classic ? <ClassicHeader /> : <TopBand />}
      {classic && (mode === 'legacy19' ? <Legacy19Tabs /> : <ClassicTabs />)}
      <Stage />
      <Console />
      <NoticeDialog />
    </div>
  )
}
