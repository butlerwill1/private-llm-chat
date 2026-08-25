import type { ChatApi, Conversation, ConversationSummary, ModelConfiguration, ModelOption, SendMessageRequest } from '../domain/chat'

const starterConversations: readonly Conversation[] = [
  {
    id: 'sunday-reflection',
    title: 'Sunday reflection',
    messages: [
      { id: 'sunday-1', author: 'assistant', body: 'What would you like to reflect on?', usage: null },
      {
        id: 'sunday-2',
        author: 'user',
        body: 'I want to think through what went well this week and what I should change.',
        usage: null,
      },
      {
        id: 'sunday-3',
        author: 'assistant',
        body: 'Let’s take it one step at a time. What felt most meaningful?',
        usage: null,
      },
    ],
  },
  {
    id: 'project-decisions',
    title: 'Project decisions',
    messages: [
      { id: 'project-1', author: 'assistant', body: 'What decision would you like to work through?', usage: null },
    ],
  },
  {
    id: 'reading-notes',
    title: 'Reading notes',
    messages: [
      { id: 'reading-1', author: 'assistant', body: 'What would you like to remember from your reading?', usage: null },
    ],
  },
]

const makeId = (): string => crypto.randomUUID()

export class DemoChatApi implements ChatApi {
  private conversations: Conversation[] = [...structuredClone(starterConversations)]

  async listConversations(): Promise<readonly Conversation[]> {
    return Promise.resolve(this.conversations)
  }

  listConversationSummaries(): Promise<readonly ConversationSummary[]> {
    return Promise.resolve(this.conversations.map(({ id, title }) => ({ id, title })))
  }

  getConversation(conversationId: string): Promise<Conversation> {
    const conversation = this.conversations.find(({ id }) => id === conversationId)
    if (!conversation) return Promise.reject(new Error('The selected conversation could not be found.'))
    return Promise.resolve(conversation)
  }

  listModels(): Promise<readonly ModelOption[]> {
    return Promise.resolve([{
      id: 'meta-llama/llama-3.3-70b-instruct', label: 'OpenRouter ZDR: Llama 3.3 70B',
      backend: 'openrouter', provider: 'deepinfra',
    }])
  }

  getModelConfiguration(): Promise<ModelConfiguration> {
    return Promise.resolve({
      customOpenRouterModelAllowed: false,
      modelBackend: 'openrouter',
      storageLabel: 'Encrypted local database',
    })
  }

  async createConversation(): Promise<Conversation> {
    const conversation: Conversation = {
      id: makeId(),
      title: 'New conversation',
      messages: [{ id: makeId(), author: 'assistant', body: 'What would you like to reflect on?', usage: null }],
    }
    this.conversations = [conversation, ...this.conversations]
    return Promise.resolve(conversation)
  }

  async sendMessage(request: SendMessageRequest): Promise<Conversation> {
    const current = this.conversations.find(({ id }) => id === request.conversationId)
    if (!current) {
      throw new Error('The selected conversation could not be found.')
    }

    const response = 'Thank you for sharing that. What feels most important about it?'
    const updated: Conversation = {
      ...current,
      messages: [
        ...current.messages,
        { id: makeId(), author: 'user', body: request.body, usage: null },
        { id: makeId(), author: 'assistant', body: response, usage: null },
      ],
    }
    this.conversations = this.conversations.map((conversation) =>
      conversation.id === updated.id ? updated : conversation,
    )
    return Promise.resolve(updated)
  }

  async deleteConversation(conversationId: string): Promise<void> {
    this.conversations = this.conversations.filter(({ id }) => id !== conversationId)
    return Promise.resolve()
  }
}
