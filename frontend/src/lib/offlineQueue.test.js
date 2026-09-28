import { describe, it, expect, vi, beforeEach } from 'vitest'
import { enqueueSOS, getQueue, queueLength, flushQueue } from './offlineQueue'

beforeEach(() => localStorage.clear())

describe('offline SOS queue', () => {
  it('starts empty', () => {
    expect(getQueue()).toEqual([])
    expect(queueLength()).toBe(0)
  })

  it('enqueue persists the payload and returns an id', () => {
    const id = enqueueSOS({ lat: 26.1, lng: 91.7, message: 'help' })
    expect(typeof id).toBe('string')
    expect(queueLength()).toBe(1)
    expect(getQueue()[0].payload).toEqual({ lat: 26.1, lng: 91.7, message: 'help' })
  })

  it('preserves insertion order across multiple entries', () => {
    enqueueSOS({ message: 'first' })
    enqueueSOS({ message: 'second' })
    const queue = getQueue()
    expect(queue.map((e) => e.payload.message)).toEqual(['first', 'second'])
  })

  it('survives being read back after a simulated reload (re-reads localStorage)', () => {
    enqueueSOS({ message: 'persisted' })
    // No in-memory state to reset -- every call reads localStorage fresh.
    expect(getQueue()[0].payload.message).toBe('persisted')
  })

  it('flushQueue sends every entry and empties the queue on full success', async () => {
    enqueueSOS({ message: 'a' })
    enqueueSOS({ message: 'b' })
    const sendFn = vi.fn().mockResolvedValue(undefined)

    const sent = await flushQueue(sendFn)

    expect(sent).toBe(2)
    expect(sendFn).toHaveBeenCalledTimes(2)
    expect(queueLength()).toBe(0)
  })

  it('flushQueue sends oldest first', async () => {
    enqueueSOS({ message: 'first' })
    enqueueSOS({ message: 'second' })
    const order = []
    await flushQueue(async (payload) => { order.push(payload.message) })
    expect(order).toEqual(['first', 'second'])
  })

  it('flushQueue stops at the first failure, leaving the rest queued', async () => {
    enqueueSOS({ message: 'sends-ok' })
    enqueueSOS({ message: 'fails' })
    enqueueSOS({ message: 'never-attempted' })

    let call = 0
    const sendFn = vi.fn().mockImplementation(async () => {
      call += 1
      if (call === 2) throw new Error('still offline')
    })

    const sent = await flushQueue(sendFn)

    expect(sent).toBe(1)
    expect(sendFn).toHaveBeenCalledTimes(2) // never attempted the third
    expect(queueLength()).toBe(2)
    expect(getQueue().map((e) => e.payload.message)).toEqual(['fails', 'never-attempted'])
  })

  it('a second flush call resumes from where the first left off', async () => {
    enqueueSOS({ message: 'a' })
    enqueueSOS({ message: 'b' })

    let shouldFail = true
    const sendFn = vi.fn().mockImplementation(async () => {
      if (shouldFail) throw new Error('offline')
    })

    await flushQueue(sendFn) // fails immediately, nothing sent
    expect(queueLength()).toBe(2)

    shouldFail = false
    const sent = await flushQueue(sendFn) // "back online"
    expect(sent).toBe(2)
    expect(queueLength()).toBe(0)
  })

  it('does not crash when localStorage.setItem throws (quota exceeded)', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(() => enqueueSOS({ message: 'x' })).not.toThrow()
    spy.mockRestore()
  })

  it('treats corrupted localStorage content as an empty queue', () => {
    localStorage.setItem('stsOfflineSosQueue', 'not valid json{{{')
    expect(getQueue()).toEqual([])
  })
})
