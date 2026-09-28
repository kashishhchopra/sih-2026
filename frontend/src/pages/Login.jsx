import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth.jsx'
import { DEMO_LOGINS, SHOW_DEMO_LOGINS } from '../config'
import LanguageSwitcher from '../components/LanguageSwitcher.jsx'
import ThemeToggle from '../components/ThemeToggle.jsx'
import logo from '../assets/musafir-logo.png'

export default function Login() {
  const { login } = useAuth()
  const { t } = useTranslation()
  const nav = useNavigate()
  // Never prefill a password, demo or otherwise -- a shoulder-surfed or
  // screen-shared login screen shouldn't leak a working credential just by
  // being open. Demo buttons (below) still fill both fields on click.
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const doLogin = async (emailValue, passwordValue) => {
    setError('')
    setLoading(true)
    try {
      const u = await login(emailValue, passwordValue)
      nav(u.role === 'admin' ? '/admin' : u.role === 'responder' ? '/responder' : '/app')
      return true
    } catch {
      setError(t('auth.invalid_credentials'))
      return false
    } finally {
      setLoading(false)
    }
  }

  const submit = (e) => {
    e.preventDefault()
    doLogin(email, password)
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-100 dark:bg-slate-900">
      <div className="w-full max-w-md">
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl w-full p-8">
          <div className="flex justify-end mb-2 gap-2">
            <LanguageSwitcher className="!border-slate-200 dark:!border-slate-600 !text-slate-600 dark:!text-slate-300" />
            <ThemeToggle className="!border-slate-200 dark:!border-slate-600 !text-slate-600 dark:!text-slate-300" />
          </div>
          <div className="text-center mb-6">
            <img src={logo} alt="" className="w-16 h-16 rounded-full mx-auto mb-2 shadow-md" />
            <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">{t('app.name')}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">{t('auth.tagline')}</p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-600 dark:text-slate-300">{t('auth.email')}</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 focus:ring-2 focus:ring-sky-500 outline-none"
                type="email" required />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-600 dark:text-slate-300">{t('auth.password')}</label>
              <input value={password} onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 focus:ring-2 focus:ring-sky-500 outline-none"
                type="password" required />
            </div>
            {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
            <button disabled={loading}
              className="w-full bg-sky-600 hover:bg-sky-700 text-white font-semibold py-2 rounded-lg transition disabled:opacity-60">
              {loading ? 'Signing in…' : t('auth.sign_in')}
            </button>
          </form>

          {SHOW_DEMO_LOGINS && DEMO_LOGINS.length > 0 && (
            <div className="mt-6 border-t border-slate-100 dark:border-slate-700 pt-4">
              <p className="text-xs text-slate-400 dark:text-slate-500 mb-2">Quick demo login:</p>
              <div className="flex gap-2">
                {DEMO_LOGINS.map((d) => (
                  <button key={d.email}
                    onClick={() => { setEmail(d.email); setPassword(d.password) }}
                    className="flex-1 text-xs border border-slate-200 dark:border-slate-600 dark:text-slate-300 rounded-lg py-2 hover:bg-slate-50 dark:hover:bg-slate-700">
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <p className="text-center text-sm text-slate-500 dark:text-slate-400 mt-4">
            <Link to="/forgot-password" className="text-sky-600 dark:text-sky-400 font-medium">Forgot password?</Link>
          </p>
          <p className="text-center text-sm text-slate-500 dark:text-slate-400 mt-2">
            <Link to="/register" className="text-sky-600 dark:text-sky-400 font-medium">{t('auth.register_prompt')}</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
