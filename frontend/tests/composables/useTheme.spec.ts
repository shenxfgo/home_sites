import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { getTheme, initTheme, setTheme, useTheme } from '@/composables/useTheme'

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
    setTheme('light')
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
