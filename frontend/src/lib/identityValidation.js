// Smart Identity & Contact Validation -- real-time input rules for
// registration (Register.jsx). Mirrors the authoritative backend copy in
// backend/app/core/identity_validators.py; the backend is what actually
// decides whether a registration is accepted -- this module only gives the
// user feedback and restricts keystrokes as they type.

export const NAME_REGEX = /^[A-Za-z ]+$/
// Indian mobile numbers only, on purpose -- see the backend module
// docstring for why this must not be loosened for international numbers.
export const PHONE_REGEX = /^[6-9][0-9]{9}$/

export const DOCUMENT_REGEX = {
  aadhaar: /^[0-9]{12}$/,
  passport: /^[A-Z][0-9]{7}$/,
  voterid: /^[A-Z]{3}[0-9]{7}$/,
  pan: /^[A-Z]{5}[0-9]{4}[A-Z]$/,
}

// Per-position character class for each document type: 'L' = uppercase
// letter, 'D' = digit. Drives both the real-time keystroke filter and the
// max length -- one definition instead of two that could drift apart.
const DOCUMENT_SHAPE = {
  aadhaar: 'D'.repeat(12),
  passport: 'L' + 'D'.repeat(7),
  voterid: 'L'.repeat(3) + 'D'.repeat(7),
  pan: 'L'.repeat(5) + 'D'.repeat(4) + 'L',
}

export const NAME_ERROR = 'Name can contain only letters and spaces.'
export const PHONE_ERROR = 'Enter a valid 10-digit mobile number starting with 6–9.'
export const DOCUMENT_ERRORS = {
  aadhaar: 'Aadhaar number must contain exactly 12 digits.',
  passport: 'Passport number must contain 1 uppercase letter followed by 7 digits.',
  voterid: 'Voter ID must contain 3 uppercase letters followed by 7 digits.',
  pan: 'PAN must contain 5 uppercase letters, 4 digits, and 1 uppercase letter.',
}

export function documentMaxLength(documentType) {
  return DOCUMENT_SHAPE[documentType]?.length ?? 40
}

export function validateName(value) {
  return NAME_REGEX.test(value)
}

export function validatePhone(value) {
  return PHONE_REGEX.test(value)
}

export function validateDocumentNumber(documentType, value) {
  return DOCUMENT_REGEX[documentType]?.test(value) ?? false
}

// Trim + collapse repeated internal spaces. Never removes letters -- an
// invalid character stays invalid, it just doesn't get a free pass because
// of surrounding whitespace.
export function normalizeName(value) {
  return value.trim().replace(/ {2,}/g, ' ')
}

// Level 1 input restriction: only letters and spaces are ever accepted as
// keystrokes, so a digit or symbol can never make it into the field at
// all (rather than being typed and then flagged as an error afterwards).
export function filterNameInput(raw) {
  return raw.replace(/[^A-Za-z ]/g, '')
}

// Indian mobile: first character must be 6-9, the rest 0-9, capped at 10
// digits -- filters every keystroke AND a pasted value the same way, so a
// user can never end up with a string that starts wrong or runs long.
export function filterPhoneInput(raw) {
  const digits = raw.replace(/[^0-9]/g, '')
  let out = ''
  for (const ch of digits) {
    if (out.length === 0) {
      if (ch >= '6' && ch <= '9') out += ch
    } else if (out.length < 10) {
      out += ch
    }
  }
  return out
}

// Shape-based filter for the four document types: walks the raw input and
// keeps only characters that fit the required class (letter/digit) at
// that position, auto-uppercasing letters. Once the full shape length is
// reached, further characters are dropped. This is why an "Invalid format"
// state basically never happens from normal typing -- bad characters are
// screened out before they ever land in the field; the regex check in
// validateDocumentNumber is the safety net for anything that still gets
// through (e.g. a programmatic value set) and, authoritatively, the
// backend re-check.
export function filterDocumentNumberInput(documentType, raw) {
  const shape = DOCUMENT_SHAPE[documentType]
  if (!shape) return raw.slice(0, 40)
  let out = ''
  for (const ch of raw) {
    if (out.length >= shape.length) break
    const want = shape[out.length]
    if (want === 'L' && /[A-Za-z]/.test(ch)) out += ch.toUpperCase()
    else if (want === 'D' && /[0-9]/.test(ch)) out += ch
  }
  return out
}

// Trim + uppercase for the alphanumeric document types (case-insensitive
// by convention); Aadhaar is numeric-only so case never applies. Never
// strips characters -- "ABCDE-1234-F" stays exactly that and still fails
// validateDocumentNumber, rather than having its hyphens silently dropped.
export function normalizeDocumentNumber(documentType, value) {
  const trimmed = value.trim()
  return documentType === 'aadhaar' ? trimmed : trimmed.toUpperCase()
}

// One-call status for a document-number field's real-time feedback:
// distinguishes "still typing, not done yet" (neutral) from "complete but
// wrong" (error) -- see Register.jsx's use of this for the inline hint.
export function documentFieldStatus(documentType, value) {
  const shape = DOCUMENT_SHAPE[documentType]
  if (!value) return { state: 'empty' }
  if (!shape) return { state: 'empty' }
  if (value.length < shape.length) {
    return { state: 'incomplete', message: DOCUMENT_ERRORS[documentType] }
  }
  return validateDocumentNumber(documentType, value)
    ? { state: 'valid' }
    : { state: 'invalid', message: DOCUMENT_ERRORS[documentType] }
}

export function phoneFieldStatus(value) {
  if (!value) return { state: 'empty' }
  if (value.length < 10) return { state: 'incomplete', message: PHONE_ERROR }
  return validatePhone(value) ? { state: 'valid' } : { state: 'invalid', message: PHONE_ERROR }
}

export function nameFieldStatus(value) {
  if (!value.trim()) return { state: 'empty' }
  return validateName(value) ? { state: 'valid' } : { state: 'invalid', message: NAME_ERROR }
}
