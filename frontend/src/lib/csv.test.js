import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { toCSV, downloadCSV } from './csv'

// jsdom does not implement URL.createObjectURL/revokeObjectURL at all, so
// there's nothing for vi.spyOn to wrap -- assign plain stubs instead, fresh
// for every test, rather than spying on a property that doesn't exist.
beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:fake')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => {
  delete URL.createObjectURL
  delete URL.revokeObjectURL
})

describe('toCSV', () => {
  it('returns an empty string for no rows', () => {
    expect(toCSV([])).toBe('')
    expect(toCSV(null)).toBe('')
  })

  it('uses the first row keys as the header', () => {
    const csv = toCSV([{ zone: 'Old Market', count: 3 }])
    expect(csv.split('\r\n')[0]).toBe('zone,count')
  })

  it('renders one line per row in order', () => {
    const csv = toCSV([{ a: 1 }, { a: 2 }, { a: 3 }])
    expect(csv.split('\r\n')).toEqual(['a', '1', '2', '3'])
  })

  it('quotes a value containing a comma', () => {
    const csv = toCSV([{ message: 'Entered high, risk zone' }])
    expect(csv.split('\r\n')[1]).toBe('"Entered high, risk zone"')
  })

  it('quotes and escapes a value containing a double quote', () => {
    const csv = toCSV([{ message: 'Said "help me"' }])
    expect(csv.split('\r\n')[1]).toBe('"Said ""help me"""')
  })

  it('quotes a value containing a newline', () => {
    const csv = toCSV([{ note: 'line one\nline two' }])
    expect(csv.split('\r\n')[1]).toBe('"line one\nline two"')
  })

  it('renders null/undefined cells as empty', () => {
    const csv = toCSV([{ a: null, b: undefined, c: 0 }])
    expect(csv.split('\r\n')[1]).toBe(',,0')
  })

  it('does not quote a plain value unnecessarily', () => {
    const csv = toCSV([{ zone: 'CityCenter' }])
    expect(csv.split('\r\n')[1]).toBe('CityCenter')
  })
})

describe('downloadCSV', () => {
  it('creates and revokes an object URL, and triggers a click on an anchor', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    downloadCSV('report', [{ a: 1 }])

    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(clickSpy).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake')

    clickSpy.mockRestore()
  })

  it('appends .csv to a filename that lacks it', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
      capturedName = this.download
    })
    let capturedName = null

    downloadCSV('report', [{ a: 1 }])
    expect(capturedName).toBe('report.csv')

    clickSpy.mockRestore()
  })

  it('does not double up .csv when already present', () => {
    let capturedName = null
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
      capturedName = this.download
    })

    downloadCSV('report.csv', [{ a: 1 }])
    expect(capturedName).toBe('report.csv')

    clickSpy.mockRestore()
  })
})
