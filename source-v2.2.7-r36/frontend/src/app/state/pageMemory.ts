import { create } from 'zustand'

// UI preferences only, kept for this window. Game identities/snapshots are never
// written to localStorage. Stage remounts remembered pages on reconnection.
type RememberedPage = 'quests' | 'players'
export const usePageMemory = create<{
  remember: Record<RememberedPage, boolean>
  setRemember(page: RememberedPage, enabled: boolean): void
  unitMonitor: boolean
  ownerMonitor: boolean
  playerNameMode: 'game' | 'map'
  setPlayerNameMode(mode: 'game' | 'map'): void
  setUnitMonitor(enabled: boolean): void
  setOwnerMonitor(enabled: boolean): void
  resetMonitors(): void
}>(set => ({
  remember: { quests: true, players: false },
  setRemember: (page, enabled) => set(st => ({ remember: { ...st.remember, [page]: enabled } })),
  unitMonitor: false, ownerMonitor: false,
  playerNameMode: 'game',
  setPlayerNameMode: playerNameMode => set({ playerNameMode }),
  setUnitMonitor: unitMonitor => set({ unitMonitor }),
  setOwnerMonitor: ownerMonitor => set({ ownerMonitor }),
  resetMonitors: () => set({ unitMonitor: false, ownerMonitor: false }),
}))
