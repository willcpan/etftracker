import { createContext, useContext, useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import Overview from './pages/Overview'
import FundPage from './pages/FundPage'
import ActivityPage from './pages/ActivityPage'
import SecuritiesPage from './pages/SecuritiesPage'
import SecurityPage from './pages/SecurityPage'

type Theme = 'auto' | 'light' | 'dark'
export const ThemeContext = createContext<{ theme: Theme; resolved: 'light' | 'dark' }>({ theme: 'auto', resolved: 'light' })
export const useTheme = () => useContext(ThemeContext)

function readTheme(): Theme {
  try {
    const t = localStorage.getItem('etftracker-theme')
    if (t === 'light' || t === 'dark') return t
  } catch { /* ignore */ }
  return 'auto'
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  const [osDark, setOsDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const h = (e: MediaQueryListEvent) => setOsDark(e.matches)
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [])
  useEffect(() => {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    try {
      if (theme === 'auto') localStorage.removeItem('etftracker-theme')
      else localStorage.setItem('etftracker-theme', theme)
    } catch { /* ignore */ }
  }, [theme])
  const resolved: 'light' | 'dark' = theme === 'auto' ? (osDark ? 'dark' : 'light') : theme
  const cycle = () => setTheme(resolved === 'dark' ? 'light' : 'dark')

  return (
    <ThemeContext.Provider value={{ theme, resolved }}>
      <div className="app">
        <header className="topbar">
          <NavLink to="/" className="brand">
            <span className="logo" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 32 32" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><path d="M6 22l6-8 5 5 9-11" /></svg>
            </span>
            ETF Tracker
          </NavLink>
          <nav className="nav">
            <NavLink to="/" end>Funds</NavLink>
            <NavLink to="/activity">Activity</NavLink>
            <NavLink to="/securities">Overlap</NavLink>
          </nav>
          <button className="theme-btn" onClick={cycle} title="Toggle light/dark theme" aria-label="Toggle theme">
            {resolved === 'dark' ? '☾ Dark' : '☼ Light'}
          </button>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/fund/:ticker" element={<FundPage />} />
            <Route path="/activity" element={<ActivityPage />} />
            <Route path="/securities" element={<SecuritiesPage />} />
            <Route path="/security/:key" element={<SecurityPage />} />
          </Routes>
        </main>
        <footer className="footer">
          Holdings are captured daily from each fund's published holdings file. Trade detection is an estimate:
          each day's creation/redemption flow is measured first, positions that merely scaled with it are labelled
          "flow", and only moves beyond it (or positions deliberately left untouched on a flow day) are reported.
        </footer>
      </div>
    </ThemeContext.Provider>
  )
}
