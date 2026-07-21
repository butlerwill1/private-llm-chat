import { afterEach, describe, expect, it, vi } from 'vitest'
import { HttpChatApi } from './httpChatApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('HttpChatApi', () => {
  it('validates and maps backend conversations', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([{
      id: 'conversation-id',
      title: 'New conversation',
      created_at: '2026-07-21T12:00:00Z',
      messages: [{
        id: 'message-id',
        role: 'assistant',
        content: 'Private response',
        created_at: '2026-07-21T12:00:01Z',
      }],
    }]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const conversations = await new HttpChatApi().listConversations()

    expect(conversations[0]?.messages[0]).toEqual({
      id: 'message-id',
      author: 'assistant',
      body: 'Private response',
    })
    expect(fetchMock).toHaveBeenCalledWith('/v1/conversations')
  })

  it('fails closed when a response does not match the API contract', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify([{ id: 'conversation-id', title: 'Missing messages' }]),
      { status: 200 },
    )))

    await expect(new HttpChatApi().listConversations()).rejects.toThrow(
      'invalid conversation',
    )
  })
})
