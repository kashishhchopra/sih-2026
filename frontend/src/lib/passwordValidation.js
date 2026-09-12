// Password strength -- real-time input rules for any screen that sets a new
// password (Register.jsx's account step, ForgotPassword.jsx's reset step).
// Mirrors the authoritative backend copy in
// backend/app/core/security.py:validate_password_strength; the backend is
// what actually decides whether a password is accepted -- this module only
// gives the user live feedback before they submit.

export const PASSWORD_MIN_LENGTH = 8

export function passwordChecklist(password) {
  return {
    minLength: password.length >= PASSWORD_MIN_LENGTH,
    hasUpper: /[A-Z]/.test(password),
    hasLower: /[a-z]/.test(password),
    hasDigit: /\d/.test(password),
    hasSymbol: /[^A-Za-z0-9]/.test(password),
  }
}

export function validatePassword(password) {
  const c = passwordChecklist(password)
  return c.minLength && c.hasUpper && c.hasLower && c.hasDigit && c.hasSymbol
}

export const PASSWORD_RULES = [
  { key: 'minLength', label: `At least ${PASSWORD_MIN_LENGTH} characters` },
  { key: 'hasUpper', label: 'One uppercase letter' },
  { key: 'hasLower', label: 'One lowercase letter' },
  { key: 'hasDigit', label: 'One number' },
  { key: 'hasSymbol', label: 'One special character' },
]
