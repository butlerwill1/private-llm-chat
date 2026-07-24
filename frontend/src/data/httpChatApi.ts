import type { ChatApi, ChatMessage, Conversation, ConversationSummary, SendMessageRequest } from '../domain/chat'

interface ApiMessage {
  readonly id: string
  readonly role: 'assistant' | 'user'
  readonly content: string
}

interface ApiConversation {
  readonly id: string
  readonly title: string
  readonly messages: readonly ApiMessage[]
}

interface ApiConversationSummary {
  readonly id: string
  readonly title: string
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

function parseMessage(value: unknown): ApiMessage {
  if (!isRecord(value)
    || typeof value.id !== 'string'
    || (value.role !== 'assistant' && value.role !== 'user')
    || typeof value.content !== 'string') {
    throw new Error('The chat API returned an invalid message.')
  }
  return { id: value.id, role: value.role, content: value.content }
}

function parseConversation(value: unknown): ApiConversation {
  if (!isRecord(value)
    || typeof value.id !== 'string'
    || typeof value.title !== 'string'
    || !Array.isArray(value.messages)) {
    throw new Error('The chat API returned an invalid conversation.')
  }
  return {
    id: value.id,
    title: value.title,
    messages: value.messages.map(parseMessage),
  }
}

const toDomain = (conversation: ApiConversation): Conversation => ({
  id: conversation.id,
  title: conversation.title,
  messages: conversation.messages.map<ChatMessage>((message) => ({
    id: message.id,
    author: message.role,
    body: message.content,
  })),
})

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) {
    const errorBody: unknown = await response.json().catch(() => null)
    const detail = isRecord(errorBody) && typeof errorBody.detail === 'string'
      ? errorBody.detail
      : `The chat API request failed with status ${response.status}.`
    throw new Error(detail)
  }
  return response.json()
}

export class HttpChatApi implements ChatApi {
  constructor(private readonly baseUrl = '/v1') {}

  async listConversations(): Promise<readonly Conversation[]> {
    const value = await readJson(await fetch(`${this.baseUrl}/conversations`))
    if (!Array.isArray(value)) {
      throw new Error('The chat API returned an invalid conversation list.')
    }
    return value.map((item) => toDomain(parseConversation(item)))
  }

  async listConversationSummaries(): Promise<readonly ConversationSummary[]> {
    const value = await readJson(await fetch(`${this.baseUrl}/conversation-summaries`))
    if (!Array.isArray(value) || value.some((item) => !isRecord(item)
      || typeof item.id !== 'string' || typeof item.title !== 'string')) {
      throw new Error('The chat API returned an invalid conversation summary list.')
    }
    return value.map((item) => {
      const summary = item as ApiConversationSummary
      return { id: summary.id, title: summary.title }
    })
  }

  async getConversation(conversationId: string): Promise<Conversation> {
    const value = await readJson(await fetch(
      `${this.baseUrl}/conversations/${encodeURIComponent(conversationId)}`,
    ))
    return toDomain(parseConversation(value))
  }

  async createConversation(): Promise<Conversation> {
    const value = await readJson(await fetch(`${this.baseUrl}/conversations`, {
      method: 'POST',
    }))
    return toDomain(parseConversation(value))
  }

  async sendMessage(request: SendMessageRequest): Promise<Conversation> {
    const value = await readJson(await fetch(
      `${this.baseUrl}/conversations/${encodeURIComponent(request.conversationId)}/messages`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: request.body }),
      },
    ))
    return toDomain(parseConversation(value))
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const response = await fetch(
      `${this.baseUrl}/conversations/${encodeURIComponent(conversationId)}`,
      { method: 'DELETE' },
    )
    if (!response.ok) {
      await readJson(response)
    }
  }
}
