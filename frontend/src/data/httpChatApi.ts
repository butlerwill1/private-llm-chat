import type { ChatApi, ChatMessage, Conversation, ConversationSummary, CostBasis, ModelConfiguration, ModelOption, SendMessageRequest, TurnUsage } from '../domain/chat'

interface ApiMessage {
  readonly id: string
  readonly role: 'assistant' | 'user'
  readonly content: string
  readonly usage: ApiTurnUsage | null
}

interface ApiTurnUsage {
  readonly input_tokens: number | null
  readonly output_tokens: number | null
  readonly total_tokens: number | null
  readonly cached_input_tokens: number | null
  readonly cache_write_input_tokens: number | null
  readonly reasoning_tokens: number | null
  readonly cost_usd: string | null
  readonly cost_basis: CostBasis
  readonly model: string
  readonly provider: string
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
    || typeof value.content !== 'string'
    || !(value.usage === null || parseUsage(value.usage) !== null)) {
    throw new Error('The chat API returned an invalid message.')
  }
  return { id: value.id, role: value.role, content: value.content, usage: value.usage as ApiTurnUsage | null }
}

const isTokenCount = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0

const isOptionalTokenCount = (value: unknown): value is number | null =>
  value === null || isTokenCount(value)

function parseUsage(value: unknown): ApiTurnUsage | null {
  if (!isRecord(value)
    || !isOptionalTokenCount(value.input_tokens)
    || !isOptionalTokenCount(value.output_tokens)
    || !isOptionalTokenCount(value.total_tokens)
    || !isOptionalTokenCount(value.cached_input_tokens)
    || !isOptionalTokenCount(value.cache_write_input_tokens)
    || !isOptionalTokenCount(value.reasoning_tokens)
    || !(value.cost_usd === null || (typeof value.cost_usd === 'string' && /^\d+(?:\.\d+)?$/.test(value.cost_usd)))
    || (value.cost_basis !== 'provider_reported' && value.cost_basis !== 'self_hosted_unallocated' && value.cost_basis !== 'unavailable')
    || typeof value.model !== 'string' || !value.model
    || typeof value.provider !== 'string' || !value.provider) {
    return null
  }
  return value as unknown as ApiTurnUsage
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
    usage: message.usage === null ? null : {
      inputTokens: message.usage.input_tokens,
      outputTokens: message.usage.output_tokens,
      totalTokens: message.usage.total_tokens,
      cachedInputTokens: message.usage.cached_input_tokens,
      cacheWriteInputTokens: message.usage.cache_write_input_tokens,
      reasoningTokens: message.usage.reasoning_tokens,
      costUsd: message.usage.cost_usd,
      costBasis: message.usage.cost_basis,
      model: message.usage.model,
      provider: message.usage.provider,
    },
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

  async listModels(): Promise<readonly ModelOption[]> {
    const value = await readJson(await fetch(`${this.baseUrl}/models`))
    if (!Array.isArray(value) || value.some((item) => !isRecord(item)
      || typeof item.id !== 'string' || typeof item.label !== 'string'
      || !(typeof item.provider === 'string' || item.provider === null)
      || (item.backend !== 'self_hosted' && item.backend !== 'openrouter' && item.backend !== 'test'))) {
      throw new Error('The chat API returned an invalid model catalogue.')
    }
    return value as ModelOption[]
  }

  async getModelConfiguration(): Promise<ModelConfiguration> {
    const value = await readJson(await fetch(`${this.baseUrl}/model-configuration`))
    if (!isRecord(value) || typeof value.custom_openrouter_model_allowed !== 'boolean'
      || (value.model_backend !== 'self_hosted' && value.model_backend !== 'openrouter')
      || typeof value.storage_label !== 'string') {
      throw new Error('The chat API returned invalid model configuration.')
    }
    return {
      customOpenRouterModelAllowed: value.custom_openrouter_model_allowed,
      modelBackend: value.model_backend,
      storageLabel: value.storage_label,
    }
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
        body: JSON.stringify({ content: request.body, model_id: request.modelId }),
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
