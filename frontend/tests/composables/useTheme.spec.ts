import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { getPreferences, updatePreferences } from '@/api/preferences'
import { getTheme, initTheme, loadAccountTheme, setTheme, useTheme } from '@/composables/useTheme'

// 主题会写回账号，这一层用 mock 挡住真实请求，顺带断言"什么时候该发"。
vi.mock('@/api/preferences', () => ({
  getPreferences: vi.fn(),
  updatePreferences: vi.fn(),
}))

function stubPrefersDark(prefersDark: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      media: query,
      matches: prefersDark,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
}

describe('useTheme', () => {
  beforeEach(() => {
    vi.mocked(updatePreferences).mockResolvedValue({ theme: 'light' })
    vi.mocked(getPreferences).mockResolvedValue({ theme: 'light' })
    setTheme('light')
    vi.mocked(updatePreferences).mockClear()
  })

  it('saves the choice on the account, not just on this browser', () => {
    setTheme('dark')

    expect(updatePreferences).toHaveBeenCalledWith({ theme: 'dark' })
  })

  it('still switches the look when the server cannot be reached', () => {
    vi.mocked(updatePreferences).mockRejectedValue(new Error('网络不可用'))

    setTheme('dark')

    expect(getTheme()).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('applies an account theme without writing it back', async () => {
    vi.mocked(getPreferences).mockResolvedValue({ theme: 'dark' })

    await loadAccountTheme()

    expect(getTheme()).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(updatePreferences).not.toHaveBeenCalled()
  })

  it('leaves this browser alone when the account has nothing stored', async () => {
    stubPrefersDark(false)
    setTheme('auto', { sync: false })
    vi.mocked(getPreferences).mockResolvedValue({ theme: 'auto' })

    await loadAccountTheme()

    expect(updatePreferences).not.toHaveBeenCalled()
  })

  it('applies an explicit theme to the document root and persists it', () => {
    setTheme('dark')

    expect(getTheme()).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('drops the element-plus dark class when switching back to light', () => {
    setTheme('dark')
    setTheme('light')

    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('resolves auto against the system preference', () => {
    stubPrefersDark(true)

    setTheme('auto')

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('restores the saved theme on init and listens for system changes', () => {
    localStorage.setItem('theme', 'dark')
    stubPrefersDark(false)
    const addEventListener = vi.fn()
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener,
      removeEventListener: vi.fn(),
    })))

    initTheme()

    expect(getTheme()).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(addEventListener).toHaveBeenCalledWith('change', expect.any(Function))
  })

  it('keeps reacting to theme changes while mounted', async () => {
    stubPrefersDark(false)
    const Subject = defineComponent({
      setup() {
        const { theme, setTheme: apply } = useTheme()
        return { theme, apply }
      },
      template: '<div />',
    })

    const wrapper = mount(Subject)
    wrapper.vm.apply('dark')
    await nextTick()

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    wrapper.unmount()
  })
})
