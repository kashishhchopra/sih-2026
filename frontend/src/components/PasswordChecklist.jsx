import { PASSWORD_RULES, passwordChecklist } from '../lib/passwordValidation.js'

// Real-time password-strength feedback: every rule is always listed (never
// color-only) with a check/cross, so the user sees exactly what's still
// missing rather than a single pass/fail message. Shared by Register.jsx's
// account step and ForgotPassword.jsx's reset step.
export default function PasswordChecklist({ password }) {
  const c = passwordChecklist(password)
  return (
    <ul className="mt-1 space-y-0.5 text-xs">
      {PASSWORD_RULES.map((rule) => (
        <li key={rule.key} className={c[rule.key] ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'}>
          {c[rule.key] ? '✓' : '○'} {rule.label}
        </li>
      ))}
    </ul>
  )
}
