import { ref, watch, onMounted } from 'vue'
import { getPreferences, updatePreferences } from '@/api/preferences'

export type Theme = 'light' | 'dark' | 'auto'

const theme = ref<Theme>('light')

/** Apply theme to document */
function applyTheme(newTheme: Theme) {
  const root = document.documentElement

  if (newTheme === 'auto') {
    // Check system preference
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    root.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
  } else {
    root.setAttribute('data-theme', newTheme)
  }

  // Update Element Plus dark mode
  if (newTheme === 'dark' || (newTheme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
}

/**
 * Set the theme on this browser and, unless told otherwise, on the account.
 *
 * localStorage 是这台设备的即时缓存（刷新不必等请求），账号那份才是"换台设备
 * 登录还是这个界面"。同步失败不打扰用户：界面已经切了，下次登录会拉回服务端值。
 */
export function setTheme(newTheme: Theme, options: { sync?: boolean } = {}) {
  theme.value = newTheme
  localStorage.setItem('theme', newTheme)
  applyTheme(newTheme)

  if (options.sync !== false) {
    void updatePreferences({ theme: newTheme }).catch(() => {
      // 未登录（登录页）或服务端不可达：只当本机生效
    })
  }
}

/** Pull this person's stored preference in, after a session became known. */
export async function loadAccountTheme(): Promise<void> {
  const prefs = await getPreferences()
  if (prefs.theme !== theme.value) setTheme(prefs.theme, { sync: false })
}

/** Get current theme */
export function getTheme(): Theme {
  return theme.value
}

/** Initialize theme from localStorage or system preference */
export function initTheme() {
  const savedTheme = localStorage.getItem('theme') as Theme | null
  if (savedTheme) {
    theme.value = savedTheme
  }
  applyTheme(theme.value)

  // Listen for system theme changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (theme.value === 'auto') {
      applyTheme('auto')
    }
  })
}

/** Composable for theme management */
export function useTheme() {
  onMounted(() => {
    initTheme()
  })

  watch(theme, (newTheme) => {
    applyTheme(newTheme)
  })

  return {
    theme,
    setTheme,
    getTheme,
  }
}
