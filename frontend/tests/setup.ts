import { config } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import { afterEach, vi } from 'vitest'

config.global.plugins = [ElementPlus]
config.global.components = { ...ElementPlusIconsVue }

// Element Plus measures with ResizeObserver, which jsdom does not implement.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= NoopResizeObserver as unknown as typeof ResizeObserver

afterEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.classList.remove('dark')
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
