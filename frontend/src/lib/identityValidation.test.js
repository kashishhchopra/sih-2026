import { describe, it, expect } from 'vitest'
import {
  validateName, validatePhone, validateDocumentNumber,
  filterNameInput, filterPhoneInput, filterDocumentNumberInput,
  normalizeName, normalizeDocumentNumber, documentFieldStatus, phoneFieldStatus,
} from './identityValidation.js'

describe('name validation', () => {
  it.each(['Rahul Sharma', 'Rahul', 'Amit Kumar', 'Priya'])('accepts %s', (v) => {
    expect(validateName(v)).toBe(true)
  })
  it.each(['Rahul123', 'Rahul@Sharma', 'Rahul-Sharma', 'Rahul_123'])('rejects %s', (v) => {
    expect(validateName(v)).toBe(false)
  })
  it('filters out digits and symbols as they are typed', () => {
    expect(filterNameInput('Rahul123')).toBe('Rahul')
    expect(filterNameInput('Rahul@Sharma!')).toBe('RahulSharma')
  })
  it('normalizes by trimming and collapsing internal whitespace only', () => {
    expect(normalizeName('  Rahul   Sharma  ')).toBe('Rahul Sharma')
  })
})

describe('phone validation', () => {
  it.each(['9876543210', '8765432109', '7654321098', '6123456789'])('accepts %s', (v) => {
    expect(validatePhone(v)).toBe(true)
  })
  it.each(['987654321', '98765432101', '5123456789', '98765abc10', '98765 43210', '98765-43210'])(
    'rejects %s', (v) => {
      expect(validatePhone(v)).toBe(false)
    })
  it('filter enforces first-digit 6-9 and 10-digit cap', () => {
    // Typed one keystroke at a time, a leading 5/0-5 digit is simply never
    // added to the field at all (out stays empty until a 6-9 digit
    // arrives) -- this only looks like "skipping ahead" when a whole
    // already-invalid string is pasted in at once.
    expect(filterPhoneInput('5123456789')).toBe('6789')
    expect(filterPhoneInput('98765abc10')).toBe('9876510') // letters dropped
    expect(filterPhoneInput('987654321012345')).toBe('9876543210') // capped at 10
  })
  it('reports incomplete vs invalid vs valid', () => {
    expect(phoneFieldStatus('987').state).toBe('incomplete')
    expect(phoneFieldStatus('9876543210').state).toBe('valid')
    expect(phoneFieldStatus('').state).toBe('empty')
  })
})

describe('document number validation', () => {
  it.each(['123456789012'])('aadhaar accepts %s', (v) => {
    expect(validateDocumentNumber('aadhaar', v)).toBe(true)
  })
  it.each(['12345678901', '1234567890123', '1234abcd9012', '1234 5678 9012', '1234-5678-9012'])(
    'aadhaar rejects %s', (v) => {
      expect(validateDocumentNumber('aadhaar', v)).toBe(false)
    })

  it.each(['A1234567', 'P7654321', 'Z1234567'])('passport accepts %s', (v) => {
    expect(validateDocumentNumber('passport', v)).toBe(true)
  })
  it.each(['AB123456', 'a1234567', 'A123456', 'A12345678', 'A1234ABC', '12345678'])(
    'passport rejects %s', (v) => {
      expect(validateDocumentNumber('passport', v)).toBe(false)
    })

  it.each(['ABC1234567', 'XYZ7654321', 'DEL1234567'])('voter id accepts %s', (v) => {
    expect(validateDocumentNumber('voterid', v)).toBe(true)
  })
  it.each(['AB12345678', 'ABCD123456', 'abc1234567', 'ABC123456'])('voter id rejects %s', (v) => {
    expect(validateDocumentNumber('voterid', v)).toBe(false)
  })

  it.each(['ABCDE1234F', 'PQRSX5678K'])('pan accepts %s', (v) => {
    expect(validateDocumentNumber('pan', v)).toBe(true)
  })
  it.each(['ABCD1234F', 'ABCDEF1234G', 'abcde1234f', 'ABCDE12345'])('pan rejects %s', (v) => {
    expect(validateDocumentNumber('pan', v)).toBe(false)
  })

  it('filter auto-uppercases letters and enforces shape as you type', () => {
    expect(filterDocumentNumberInput('pan', 'abcde1234f')).toBe('ABCDE1234F')
    expect(filterDocumentNumberInput('passport', 'ab1234567')).toBe('A1234567') // 2nd letter dropped, uppercased
    expect(filterDocumentNumberInput('aadhaar', '123456789012xyz')).toBe('123456789012') // capped at 12, letters dropped
  })

  it('typing straight through in the correct shape needs no correction', () => {
    expect(filterDocumentNumberInput('pan', 'ABCDE1234F')).toBe('ABCDE1234F')
    expect(filterDocumentNumberInput('voterid', 'ABC1234567')).toBe('ABC1234567')
  })

  it('normalization uppercases alphanumeric types but never strips characters', () => {
    expect(normalizeDocumentNumber('pan', 'abcde1234f')).toBe('ABCDE1234F')
    expect(normalizeDocumentNumber('aadhaar', ' 123456789012 ')).toBe('123456789012')
    // A hyphen is not silently removed -- normalization alone must not turn
    // this into a valid PAN.
    const withHyphens = normalizeDocumentNumber('pan', 'ABCDE-1234-F')
    expect(withHyphens).toBe('ABCDE-1234-F')
    expect(validateDocumentNumber('pan', withHyphens)).toBe(false)
  })

  it('distinguishes incomplete from invalid by required length', () => {
    expect(documentFieldStatus('pan', 'ABCDE123').state).toBe('incomplete')
    expect(documentFieldStatus('pan', 'ABCDE1234F').state).toBe('valid')
    expect(documentFieldStatus('pan', '').state).toBe('empty')
  })
})
