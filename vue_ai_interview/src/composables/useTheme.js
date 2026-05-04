import { ref, watch } from 'vue'

const THEME_KEY = 'ai_interview_theme'
const theme = ref(localStorage.getItem(THEME_KEY) || 'light')

export function useTheme() {
  function setTheme(name) {
    theme.value = name
    localStorage.setItem(THEME_KEY, name)
    document.documentElement.setAttribute('data-theme', name)
  }

  // Init on first call
  if (!document.documentElement.getAttribute('data-theme')) {
    document.documentElement.setAttribute('data-theme', theme.value)
  }

  return { theme, setTheme }
}
