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

export type ModelChoice = 'private' | 'openrouter'

export interface SendMessageRequest {
  readonly conversationId: string
  readonly body: string
  readonly model: ModelChoice
}

export interface ChatApi {
  listConversations(): Promise<readonly Conversation[]>
  createConversation(): Promise<Conversation>
  sendMessage(request: SendMessageRequest): Promise<Conversation>
}
