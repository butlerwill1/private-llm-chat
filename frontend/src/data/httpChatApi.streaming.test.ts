import { afterEach, expect, it, vi } from 'vitest'
import { HttpChatApi } from './httpChatApi'

afterEach(() => vi.unstubAllGlobals())

function transport() {
  let controller: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({ start(value) { controller = value } })
  const fetchMock = vi.fn().mockResolvedValue(new Response(body))
  vi.stubGlobal('fetch', fetchMock)
  return {
    fetchMock,
    feed(event: unknown) { controller.enqueue(new TextEncoder().encode(JSON.stringify(event) + '\n')) },
    close() { controller.close() },
  }
}

it('delivers text before completion and maps the saved conversation at done', async () => {
  const wire = transport()
  const update = vi.fn()
  const abort = new AbortController()
  const result = new HttpChatApi().streamMessage({ conversationId: 'chat/id', body: 'hello', promptModeId: 'standard' }, abort.signal, update)
  wire.feed({ type: 'heartbeat' })
  wire.feed({ type: 'status', text: 'Thinking…' })
  wire.feed({ type: 'text', text: 'Hello 世界' })
  await vi.waitFor(() => expect(update).toHaveBeenCalledWith({ type: 'text', text: 'Hello 世界' }))
  wire.feed({ type: 'done', conversation: { id: 'chat/id', title: 'Test', active_model_id: 'model', messages: [{ id: 'answer', role: 'assistant', content: 'Hello 世界', usage: null }] } })
  expect((await result).messages[0]?.body).toBe('Hello 世界')
  expect(wire.fetchMock).toHaveBeenCalledWith('/v1/conversations/chat%2Fid/messages/stream', expect.objectContaining({ signal: abort.signal, method: 'POST' }))
})

it('does not mistake a disconnected stream for a saved answer', async () => {
  const wire = transport()
  const result = new HttpChatApi().streamMessage({ conversationId: 'chat', body: 'hello' }, new AbortController().signal, vi.fn())
  wire.feed({ type: 'text', text: 'partial' })
  wire.close()
  await expect(result).rejects.toThrow('Connection ended before the answer was saved')
})

it('surfaces the sanitized stream error and rejects unknown events', async () => {
  for (const event of [{ type: 'error', text: 'Response interrupted.' }, { type: 'unexpected' }]) {
    const wire = transport()
    const result = new HttpChatApi().streamMessage({ conversationId: 'chat', body: 'hello' }, new AbortController().signal, vi.fn())
    wire.feed(event)
    await expect(result).rejects.toThrow(event.type === 'error' ? 'Response interrupted.' : 'Invalid response stream event.')
  }
})
