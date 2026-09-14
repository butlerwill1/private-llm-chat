import { describe, expect, it } from 'vitest'
import { streamLines } from './streamLines'

describe('stream framing', () => {
  it('preserves Unicode split across bytes, combined frames, and a final line without a newline', async () => {
    const wire = new TextEncoder().encode('{"text":"世界"}\n\n{"type":"done"}')
    const stream = new ReadableStream<Uint8Array>({ start(controller) {
      for (const byte of wire) controller.enqueue(new Uint8Array([byte]))
      controller.close()
    } })
    const lines = []
    for await (const line of streamLines(stream)) lines.push(JSON.parse(line))
    expect(lines).toEqual([{ text: '世界' }, { type: 'done' }])
  })

  it('cancels the underlying stream when its consumer stops', async () => {
    let cancelled = false
    const stream = new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(new TextEncoder().encode('one\ntwo\n')) },
      cancel() { cancelled = true },
    })
    for await (const line of streamLines(stream)) { expect(line).toBe('one'); break }
    expect(cancelled).toBe(true)
  })
})
