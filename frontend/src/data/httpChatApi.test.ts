import { afterEach, describe, expect, it, vi } from 'vitest'
import { HttpChatApi } from './httpChatApi'

// Fetch is replaced globally in each test because HttpChatApi deliberately uses
// the browser transport directly. Restore it so other suites see a clean runtime.
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('HttpChatApi', () => {
  it('validates and maps backend conversations', async () => {
    // This payload uses the backend's snake_case/role schema. The assertion below
    // proves the adapter converts it into the frontend's body/author vocabulary.
    // vi.fn records how it is called. mockResolvedValue makes each invocation
    // return a fulfilled Promise containing this browser-standard Response.
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
    // JSON.stringify turns the object into the wire-format text that fetch returns.
    }]), { status: 200 }))
    // Replace global fetch so the real adapter talks to the mock instead of a server.
    vi.stubGlobal('fetch', fetchMock)

    // Act: this runs fetch, checks the HTTP status, parses JSON, validates every
    // field and maps the backend representation to the frontend representation.
    const conversations = await new HttpChatApi().listConversations()

    // Optional chaining safely reads the first message; a missing conversation or
    // message would produce undefined and cause this equality assertion to fail.
    expect(conversations[0]?.messages[0]).toEqual({
      id: 'message-id',
      author: 'assistant',
      body: 'Private response',
    })
    // A relative URL keeps browser traffic on the local Vite/FastAPI origin and
    // avoids accidentally embedding an internet-facing API address in the UI.
    expect(fetchMock).toHaveBeenCalledWith('/v1/conversations')
  })

  it('fails closed when a response does not match the API contract', async () => {
    // The response is valid JSON but omits `messages`. Transport success alone is
    // insufficient: malformed server data must never enter trusted React state.
    // Arrange a successful HTTP response whose conversation shape is incomplete.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify([{ id: 'conversation-id', title: 'Missing messages' }]),
      { status: 200 },
    )))

    // Rejecting makes contract drift visible instead of silently inventing a
    // default transcript or displaying partially validated private data.
    // Passing the Promise directly to expect lets `rejects` unwrap its rejection;
    // toThrow then checks that the resulting Error contains this useful phrase.
    await expect(new HttpChatApi().listConversations()).rejects.toThrow(
      'invalid conversation',
    )
  })
})
