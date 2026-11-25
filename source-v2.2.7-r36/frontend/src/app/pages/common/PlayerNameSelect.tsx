import { Select } from '../../../ds'
import { useT } from '../../i18n'
import { usePageMemory } from '../../state/pageMemory'

export function PlayerNameSelect() {
  const t = useT()
  const mode = usePageMemory(st => st.playerNameMode)
  const setMode = usePageMemory(st => st.setPlayerNameMode)
  return <Select label={t('玩家名显示')} aria-label={t('玩家名显示')} value={mode}
    options={[{ value: 'game', label: t('游戏中名字（含玩家昵称）') }, { value: 'map', label: t('地图配置名') }]}
    onChange={e => setMode(e.target.value === 'map' ? 'map' : 'game')} />
}
