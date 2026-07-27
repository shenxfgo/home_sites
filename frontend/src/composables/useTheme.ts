import { ref, watch, onMounted } from 'vue'

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

/** Set theme */
export function setTheme(newTheme: Theme) {
  theme.value = newTheme
  localStorage.setItem('theme', newTheme)
  applyTheme(newTheme)
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
