import { createContext, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext(null)
const STORAGE_KEY = 'stsTheme'

function systemPrefersDark() {
  return typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false
}

// A first-ever visit (no stored preference yet) defaults to the mode that
// matches the section of the app being opened -- the police/admin consoles
// read as a security operations center, the tourist app as a light travel
// companion (see index.css's [data-role-theme] palettes). This only ever
// picks the STARTING value: an explicit choice (stored or toggled) always
// wins from then on, on every route, exactly as before -- the toggle itself
// is untouched.
function defaultThemeForRoute() {
  const path = typeof window !== 'undefined' ? window.location.pathname : ''
  if (path.startsWith('/admin') || path.startsWith('/responder')) return 'dark'
  return systemPrefersDark() ? 'dark' : 'light'
}

function apply(theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    const stored = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
    return stored || defaultThemeForRoute()
  })

  useEffect(() => {
    apply(theme)
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const toggle = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
