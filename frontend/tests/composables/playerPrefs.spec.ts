import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'player-prefs'

type PrefsModule = typeof import('@/composables/playerPrefs')

/** Re-import the module so its one-time read of localStorage is observed again. */
async function freshImport(): Promise<PrefsModule> {
  vi.resetModules()
  return import('@/composables/playerPrefs')
}

describe('playerPrefs', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('starts from the defaults for a browser that never played anything', async () => {
    const { playerPrefs } = await freshImport()

    expect({ ...playerPrefs }).toEqual({
      volume: 1,
      muted: false,
      rate: 1,
      subtitleSize: 0,
      subtitleDelay: 0,
    })
  })

  it('reads back what an earlier visit left', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ volume: 0.3, muted: true, rate: 1.5, subtitleSize: 22, subtitleDelay: -1.5 }),
    )

    const { playerPrefs } = await freshImport()

    expect(playerPrefs.volume).toBe(0.3)
    expect(playerPrefs.muted).toBe(true)
    expect(playerPrefs.rate).toBe(1.5)
    expect(playerPrefs.subtitleSize).toBe(22)
    expect(playerPrefs.subtitleDelay).toBe(-1.5)
  })

  it('drops values a later version would not accept', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ volume: 11, muted: 'yes', rate: 0, subtitleSize: null, subtitleDelay: 'emmet' }),
    )

    const { playerPrefs } = await freshImport()

    expect({ ...playerPrefs }).toEqual({
      volume: 1,
      muted: false,
      rate: 1,
      subtitleSize: 0,
      subtitleDelay: 0,
    })
  })

  it('falls back to the defaults when the stored json is not json', async () => {
    localStorage.setItem(STORAGE_KEY, '{oops')

    const { playerPrefs } = await freshImport()

    expect(playerPrefs.volume).toBe(1)
    expect(playerPrefs.rate).toBe(1)
  })

  it('survives a storage that refuses to be read', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })

    const { playerPrefs } = await freshImport()

    expect(getItem).toHaveBeenCalled()
    expect(playerPrefs.volume).toBe(1)
  })

  it('stores every change for the next visit', async () => {
    const { playerPrefs } = await freshImport()

    playerPrefs.rate = 2
    playerPrefs.subtitleDelay = 0.5
    await nextTick()

    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')).toMatchObject({
      rate: 2,
      subtitleDelay: 0.5,
    })
  })

  it('stays usable when the storage is full', async () => {
    const { playerPrefs } = await freshImport()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })

    playerPrefs.volume = 0.5
    await nextTick()

    expect(playerPrefs.volume).toBe(0.5)
  })
})
