import { create } from 'zustand'

type Mode = 'modern' | 'classic' | 'legacy19'
const KEY = 'war3-interface-mode'
function initialMode(): Mode {
  try { const mode = localStorage.getItem(KEY); return mode === 'classic' || mode === 'legacy19' ? mode : 'modern' } catch { return 'modern' }
}
const initial = initialMode()
document.documentElement.dataset.interface = initial
let revision = 0
function remember(mode: Mode) {
  document.documentElement.dataset.interface = mode
  try { localStorage.setItem(KEY, mode) } catch { /* storage may be unavailable */ }
}

// Presentation only: keep the mounted pages, connection and backend caches.
export const useInterface = create<{ mode: Mode; choose(mode: Mode): void; toggle(): void; hydrate(): () => void }>()((set, get) => ({
  mode: initial,
  hydrate() {
    let active = true
    const started = revision
    const load = async () => {
      try {
        const result = await window.pywebview?.api?.get_interface_mode?.()
        if (active && started === revision && result?.success && ['classic', 'modern', 'legacy19'].includes(result.mode)) {
          remember(result.mode); set({ mode: result.mode })
        }
      } catch { /* keep the local choice when the desktop bridge is unavailable */ }
    }
    if (window.pywebview?.api) void load()
    else window.addEventListener('pywebviewready', load, { once: true })
    return () => { active = false; window.removeEventListener('pywebviewready', load) }
  },
  toggle() {
    const mode = get().mode === 'modern' ? 'classic' : 'modern'
    get().choose(mode)
  },
  choose(mode) {
    ++revision; remember(mode)
    set({ mode })
    // WebView2 private storage can be cleared at exit. Save this UI preference
    // separately; no connection or game state is serialized.
    const save = window.pywebview?.api?.save_interface_mode
    if (save) void Promise.resolve(save(mode)).catch(() => {})
  },
}))
