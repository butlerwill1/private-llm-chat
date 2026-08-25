export type MessageAuthor = 'assistant' | 'user'
export type CostBasis = 'provider_reported' | 'self_hosted_unallocated' | 'unavailable'

export interface TurnUsage {
  readonly inputTokens: number | null
  readonly outputTokens: number | null
  readonly totalTokens: number | null
  readonly cachedInputTokens: number | null
  readonly cacheWriteInputTokens: number | null
  readonly reasoningTokens: number | null
  readonly costUsd: string | null
  readonly costBasis: CostBasis
  readonly model: string
  readonly provider: string
}

export interface ChatMessage {
  readonly id: string
  readonly author: MessageAuthor
  readonly body: string
  readonly usage: TurnUsage | null
}

export interface Conversation {
  readonly id: string
  readonly title: string
  readonly messages: readonly ChatMessage[]
}

export interface ConversationSummary {
  readonly id: string
  readonly title: string
}

export interface ModelOption {
  readonly id: string
  readonly label: string
  readonly backend: 'self_hosted' | 'openrouter' | 'test'
  readonly provider: string | null
}

export interface ModelConfiguration {
  readonly customOpenRouterModelAllowed: boolean
  readonly modelBackend: 'self_hosted' | 'openrouter'
  readonly storageLabel: string
}

export interface SendMessageRequest {
  readonly conversationId: string
  readonly body: string
  readonly modelId: string
}

export interface ChatApi {
  listConversations(): Promise<readonly Conversation[]>
  listConversationSummaries(): Promise<readonly ConversationSummary[]>
  getConversation(conversationId: string): Promise<Conversation>
  listModels(): Promise<readonly ModelOption[]>
  getModelConfiguration(): Promise<ModelConfiguration>
  createConversation(): Promise<Conversation>
  sendMessage(request: SendMessageRequest): Promise<Conversation>
  deleteConversation(conversationId: string): Promise<void>
}
