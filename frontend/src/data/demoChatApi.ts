import type { ChatApi, Conversation, ConversationSummary, ModelConfiguration, ModelOption, SendMessageRequest, SystemMonitor } from '../domain/chat'

const starterConversations: readonly Conversation[] = [
  {
    id: 'sunday-reflection',
    title: 'Sunday reflection',
    activeModelId: 'google/gemini-3.7-flash',
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
    activeModelId: 'google/gemini-3.7-flash',
    messages: [
      { id: 'project-1', author: 'assistant', body: 'What decision would you like to work through?', usage: null },
    ],
  },
  {
    id: 'reading-notes',
    title: 'Reading notes',
    activeModelId: 'google/gemini-3.7-flash',
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
    return Promise.resolve(this.conversations.map(({ id, title, activeModelId }) => ({ id, title, activeModelId })))
  }

  getConversation(conversationId: string): Promise<Conversation> {
    const conversation = this.conversations.find(({ id }) => id === conversationId)
    if (!conversation) return Promise.reject(new Error('The selected conversation could not be found.'))
    return Promise.resolve(conversation)
  }

  listModels(): Promise<readonly ModelOption[]> {
    return Promise.resolve([{
      id: 'google/gemini-3.7-flash', label: 'Gemini 3.7 Flash',
      backend: 'openrouter', provider: 'google-vertex', available: true,
    }])
  }

  getModelConfiguration(): Promise<ModelConfiguration> {
    return Promise.resolve({
      customOpenRouterModelAllowed: false,
      modelBackend: 'openrouter',
      storageLabel: 'Encrypted local database',
    })
  }

  async createConversation(request: { modelId: string }): Promise<Conversation> {
    const conversation: Conversation = {
      id: makeId(),
      title: 'New conversation',
      activeModelId: request.modelId,
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

  async changeModel(conversationId: string, modelId: string): Promise<Conversation> {
    const current = await this.getConversation(conversationId)
    const from = current.activeModelId ?? 'Selected model'
    const to = (await this.listModels()).find((model) => model.id === modelId)?.label ?? modelId
    const updated: Conversation = { ...current, activeModelId: modelId, messages: [
      ...current.messages, { id: makeId(), author: 'event', body: `Model changed from ${from} to ${to}.`, usage: null },
    ] }
    this.conversations = this.conversations.map((conversation) => conversation.id === updated.id ? updated : conversation)
    return updated
  }

  async renameConversation(conversationId: string, title: string): Promise<Conversation> {
    const current = await this.getConversation(conversationId)
    const cleanedTitle = title.trim()
    if (!cleanedTitle) throw new Error('Conversation title must not be blank.')
    const updated = { ...current, title: cleanedTitle }
    this.conversations = this.conversations.map((conversation) =>
      conversation.id === updated.id ? updated : conversation,
    )
    return updated
  }

  async deleteConversation(conversationId: string): Promise<void> {
    this.conversations = this.conversations.filter(({ id }) => id !== conversationId)
    return Promise.resolve()
  }

  getSystemMonitor(): Promise<SystemMonitor> { return Promise.resolve({ snapshot: { sampledAt: new Date().toISOString(), gpuName: { value: 'Demo GPU', unit: null, status: 'ok', detail: null }, gpuTemperature: { value: 54, unit: '°C', status: 'ok', detail: null }, gpuUtilization: { value: 18, unit: '%', status: 'ok', detail: null }, gpuPower: { value: 42, unit: 'W', status: 'ok', detail: null }, vramTotal: { value: 8151 * 1024 * 1024, unit: 'bytes', status: 'ok', detail: null }, vramUsed: { value: 3100 * 1024 * 1024, unit: 'bytes', status: 'ok', detail: null }, vramFree: { value: 5051 * 1024 * 1024, unit: 'bytes', status: 'ok', detail: null }, diskFree: { value: 300 * 1024 ** 3, unit: 'bytes', status: 'ok', detail: null }, diskTotal: { value: 900 * 1024 ** 3, unit: 'bytes', status: 'ok', detail: null }, ollamaStatus: { value: 'reachable', unit: null, status: 'ok', detail: null }, cpuTemperature: { value: null, unit: null, status: 'unavailable', detail: 'Install Libre Hardware Monitor for CPU temperature.' }, loadedModels: [] }, telemetry: { sampleCount: 12, databaseBytes: 4096 } }) }
  async exportSystemMonitor(): Promise<void> { return Promise.resolve() }
}
