import { create } from 'zustand'
import { api } from '../../lib/api'
import { useSystem } from './system'
import type { CandidateUnit, SelectedUnitData } from '../../lib/types'

/** The four-character type id inside unitTypeId, e.g. "Hpal". */
export function rawcodeOf(unitTypeId: string | undefined | null): string | null {
  return unitTypeId?.match(/\b[A-Za-z0-9]{4}\b/)?.[0] ?? null
}

interface UnitName { zh: string; en: string }

interface UnitState {
  unit: SelectedUnitData | null
  candidates: CandidateUnit[]
  /** Catalogue names by rawcode, looked up once per type. */
  names: Record<string, UnitName | null>
  reading: boolean

  /** Apply a read result, from a command or from a unit_read notification. */
  received(unit: SelectedUnitData | null | undefined, candidates?: CandidateUnit[] | null): void
  /** Load what the backend already has, without reading game memory. */
  loadSnapshot(): Promise<void>
  /** Read every selected unit in the game (Ctrl+F11 in game). */
  readAll(): Promise<void>
  /** Read the current selection for the optional timer, without overlapping. */
  monitorSelected(): Promise<boolean>
}

export const useUnit = create<UnitState>()((set, get) => {
  async function lookupName(code: string) {
    if (code in get().names) return
    set(st => ({ names: { ...st.names, [code]: null } }))
    try {
      const data = await api.searchIdCatalog('unit', code)
      const row = data?.rows?.find(r => r.rawcode === code)
      if (row) set(st => ({ names: { ...st.names, [code]: { zh: row.name_zh, en: row.name_en } } }))
    } catch { /* the console falls back to the rawcode */ }
  }

  return {
    unit: null,
    candidates: [],
    names: {},
    reading: false,

    received(unit, candidates) {
      set(st => ({ unit: unit ?? st.unit, candidates: candidates ?? st.candidates }))
      const code = rawcodeOf(unit?.unitTypeId)
      if (code) void lookupName(code)
    },

    async loadSnapshot() {
      try {
        const [unit, candidates] = await Promise.all([api.getSelectedUnitSnapshot(), api.getUnitCandidatesSnapshot()])
        get().received(unit, candidates)
      } catch { /* reported by callApi */ }
    },

    async monitorSelected() {
      if (get().reading) return true
      const before = useSystem.getState().status
      if (!before.connected) return false
      set({ reading: true })
      try {
        // Same selection read as the manual command; no new native/parameters.
        const result = await api.readAllSelectedUnits()
        const after = useSystem.getState().status
        if (!after.connected || before.pid !== after.pid || before.connectionId !== after.connectionId) return false
        if (result?.unit) get().received(result.unit, result.candidates)
        else set({ unit: null, candidates: result?.candidates ?? [] })
        return true
      } catch {
        // A failed/no-selection read must not keep displaying the old unit as
        // the monitored selection. Do not clear a different connection's data.
        const after = useSystem.getState().status
        if (before.pid === after.pid && before.connectionId === after.connectionId) set({ unit: null, candidates: [] })
        return false // Shared API reports once; the page stops polling.
      }
      finally { set({ reading: false }) }
    },

    async readAll() {
      if (get().reading) return
      set({ reading: true })
      try {
        const result = await api.readAllSelectedUnits()
        get().received(result?.unit, result?.candidates)
      } catch {
        // reported by callApi
      } finally {
        set({ reading: false })
      }
    },
  }
})
