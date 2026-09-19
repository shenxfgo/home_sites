import { reactive, watch } from 'vue'

/** Playback choices the site remembers per browser, not per video. */
export interface PlayerPrefs {
  volume: number
  muted: boolean
  rate: number
  /** Cue font size in pixels; 0 keeps the player's automatic sizing. */
  subtitleSize: number
  /** Shift every subtitle cue by this many seconds. */
  subtitleDelay: number
}

const STORAGE_KEY = 'player-prefs'

const defaults: PlayerPrefs = {
  volume: 1,
  muted: false,
  rate: 1,
  subtitleSize: 0,
  subtitleDelay: 0,
}

function bounded(value: unknown, min: number, max: number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
    ? value
    : fallback
}

function load(): PlayerPrefs {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(STORAGE_KEY)
  } catch {
    return { ...defaults }
  }
  if (!raw) return { ...defaults }
  try {
    const stored = JSON.parse(raw) as Partial<PlayerPrefs>
    return {
      volume: bounded(stored.volume, 0, 1, defaults.volume),
      muted: typeof stored.muted === 'boolean' ? stored.muted : defaults.muted,
      rate: bounded(stored.rate, 0.25, 4, defaults.rate),
      subtitleSize: bounded(stored.subtitleSize, 0, 40, defaults.subtitleSize),
      subtitleDelay: bounded(stored.subtitleDelay, -15, 15, defaults.subtitleDelay),
    }
  } catch {
    return { ...defaults }
  }
}

export const playerPrefs = reactive<PlayerPrefs>(load())

watch(
  playerPrefs,
  (prefs) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
    } catch {
      // Private mode or a full quota: the player still works, just forgetful
    }
  },
  { deep: true },
)
