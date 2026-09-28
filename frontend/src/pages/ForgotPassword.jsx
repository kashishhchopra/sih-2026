import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import ThemeToggle from '../components/ThemeToggle.jsx'
import PasswordChecklist from '../components/PasswordChecklist.jsx'
import { validatePassword } from '../lib/passwordValidation.js'

export default function ForgotPassword() {
  const [step, setStep] = useState('request') // request | reset | done
  const [email, setEmail] = useState('')
  const [token, setToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [message, setMessage] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const requestReset = async (e) => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const { data } = await api.post('/auth/forgot-password', { email })
      setMessage(data.message)
      setStep('reset')
    } catch {
      // The endpoint never errors on a bad email by design; a network/5xx
      // failure is the only realistic case that lands here.
      setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const submitReset = async (e) => {
    e.preventDefault()
    if (!validatePassword(newPassword)) {
      setError('Please choose a password that meets all the requirements below.')
      return
    }
    setLoading(true); setError('')
    try {
      await api.post('/auth/reset-password', { token, new_password: newPassword })
      setStep('done')
    } catch (err) {
      setError(
        err.response?.data?.detail?.[0]?.msg
        || err.response?.data?.detail
        || 'Reset failed. The code may be invalid or expired.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-sky-600 to-indigo-700 dark:from-slate-900 dark:to-indigo-950 p-4">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl w-full max-w-md p-8">
        <div className="flex justify-end mb-2">
          <ThemeToggle className="!border-slate-200 dark:!border-slate-600 !text-slate-600 dark:!text-slate-300" />
        </div>
        <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100 text-center mb-6">
          Reset your password
        </h1>

        {step === 'request' && (
          <form onSubmit={requestReset} className="space-y-4">
            <div>
              <label htmlFor="fp-email" className="text-sm font-medium text-slate-600 dark:text-slate-300">Email</label>
              <input id="fp-email" value={email} onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 focus:ring-2 focus:ring-sky-500 outline-none"
                type="email" required />
            </div>
            {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
            <button disabled={loading}
              className="w-full bg-sky-600 hover:bg-sky-700 text-white font-semibold py-2 rounded-lg transition disabled:opacity-60">
              {loading ? 'Sending…' : 'Send reset code'}
            </button>
          </form>
        )}

        {step === 'reset' && (
          <div className="space-y-4">
            <div className="text-sm text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/30 rounded-lg p-3">
              {message}
            </div>
            <p className="text-xs text-slate-400 dark:text-slate-500">
              This demo has no real email service configured, so the reset code was
              logged on the server instead of emailed — check the backend console output.
            </p>
            <form onSubmit={submitReset} className="space-y-4">
              <div>
                <label htmlFor="fp-token" className="text-sm font-medium text-slate-600 dark:text-slate-300">Reset code</label>
                <input id="fp-token" value={token} onChange={(e) => setToken(e.target.value)}
                  className="mt-1 w-full border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 focus:ring-2 focus:ring-sky-500 outline-none"
                  required />
              </div>
              <div>
                <label htmlFor="fp-new-password" className="text-sm font-medium text-slate-600 dark:text-slate-300">New password</label>
                <input id="fp-new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                  className="mt-1 w-full border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 focus:ring-2 focus:ring-sky-500 outline-none"
                  type="password" required />
                {newPassword && <PasswordChecklist password={newPassword} />}
              </div>
              {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
              <button disabled={loading || !validatePassword(newPassword)}
                className="w-full bg-sky-600 hover:bg-sky-700 text-white font-semibold py-2 rounded-lg transition disabled:opacity-60">
                {loading ? 'Resetting…' : 'Reset password'}
              </button>
            </form>
          </div>
        )}

        {step === 'done' && (
          <div className="space-y-4 text-center">
            <div className="text-sm text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/30 rounded-lg p-3">
              Your password has been reset. You can now sign in.
            </div>
            <Link to="/login"
              className="inline-block w-full bg-sky-600 hover:bg-sky-700 text-white font-semibold py-2 rounded-lg transition">
              Back to sign in
            </Link>
          </div>
        )}

        {step !== 'done' && (
          <p className="text-center text-sm text-slate-500 dark:text-slate-400 mt-6">
            <Link to="/login" className="text-sky-600 dark:text-sky-400 font-medium">Back to sign in</Link>
          </p>
        )}
      </div>
    </div>
  )
}
