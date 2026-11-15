import { create } from 'zustand'

// UI preferences only, kept for this window. Game identities/snapshots are never
// written to localStorage. Stage remounts remembered pages on reconnection.
type RememberedPage = 'players' | 'quests'
export const usePageMemory = create<{
  remember: Record<RememberedPage, boolean>
  setRemember(page: RememberedPage, enabled: boolean): void
  unitMonitor: boolean
  ownerMonitor: boolean
  setUnitMonitor(enabled: boolean): void
  setOwnerMonitor(enabled: boolean): void
  resetMonitors(): void
}>(set => ({
  remember: { players: true, quests: true },
  setRemember: (page, enabled) => set(st => ({ remember: { ...st.remember, [page]: enabled } })),
  unitMonitor: false, ownerMonitor: false,
  setUnitMonitor: unitMonitor => set({ unitMonitor }),
  setOwnerMonitor: ownerMonitor => set({ ownerMonitor }),
  resetMonitors: () => set({ unitMonitor: false, ownerMonitor: false }),
}))
