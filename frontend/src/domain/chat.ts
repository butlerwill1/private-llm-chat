export type MessageAuthor = 'assistant' | 'user'

export interface ChatMessage {
  readonly id: string
  readonly author: MessageAuthor
  readonly body: string
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
}

export interface ModelConfiguration {
  readonly customOpenRouterModelAllowed: boolean
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
