import { useInterface } from '../state/interface'
import { useT } from '../i18n'
import s from './ClassicHeader.module.css'

export function InterfaceSwitch() {
  const t = useT()
  const { mode, toggle, choose } = useInterface()
  return <>
  <button type="button" className={s.switch} data-testid="interface-switch" onClick={toggle}>
    {mode === 'modern' ? t('回到旧版界面') : t('返回新版界面')}
  </button>
  <button type="button" className={s.switch} data-testid="interface-legacy19" onClick={() => choose(mode === 'legacy19' ? 'classic' : 'legacy19')}>
    {mode === 'legacy19' ? t('白色标签页界面') : t('1.0.19 旧版 UI')}
  </button>
  </>
}
