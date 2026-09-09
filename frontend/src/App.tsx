import { startTransition, useState } from 'react'
import { Composer } from './components/Composer'
import { ConversationHeader } from './components/ConversationHeader'
import { MessageList } from './components/MessageList'
import { Sidebar } from './components/Sidebar'
import { SystemMonitor } from './components/SystemMonitor'
import type { ChatApi, Conversation, ConversationSummary, ModelConfiguration, ModelOption } from './domain/chat'

interface AppProps {
  readonly api: ChatApi
  readonly initialConversations: readonly Conversation[]
  readonly initialSummaries: readonly ConversationSummary[]
  readonly models: readonly ModelOption[]
  readonly modelConfiguration: ModelConfiguration
  readonly onLock: () => void
}

export function App({ api, initialConversations, initialSummaries, models, modelConfiguration, onLock }: AppProps) {
  const [conversations, setConversations] = useState<readonly Conversation[]>(() => initialConversations)
  const [summaries, setSummaries] = useState<readonly ConversationSummary[]>(() => initialSummaries)
  const [selectedId, setSelectedId] = useState(initialSummaries[0]?.id ?? '')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [isRenaming, setIsRenaming] = useState(false)
  const [isLoadingConversation, setIsLoadingConversation] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState(models[0]?.id ?? '')
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'chat' | 'monitor'>('chat')
  const selectedConversation = conversations.find(({ id }) => id === selectedId)

  const selectConversation = async (id: string) => {
    if (id === selectedId) return
    setSelectedId(id)
    setSidebarOpen(false)
    setIsLoadingConversation(true)
    setError(null)
    try {
      const conversation = await api.getConversation(id)
      setConversations((current) => [
        ...current.filter((item) => item.id !== conversation.id),
        conversation,
      ])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The conversation could not be loaded.')
    } finally {
      setIsLoadingConversation(false)
    }
  }

  const createConversation = async () => {
    setError(null)
    try {
      const conversation = await api.createConversation({ modelId: selectedModelId })
      startTransition(() => {
        setConversations((current) => [conversation, ...current])
        setSummaries((current) => [{ id: conversation.id, title: conversation.title, activeModelId: conversation.activeModelId }, ...current])
        setSelectedId(conversation.id)
        setSidebarOpen(false)
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The conversation could not be created.')
    }
  }

  const sendMessage = async (body: string) => {
    if (!selectedConversation) return
    setIsSending(true)
    setError(null)
    try {
      const updated = await api.sendMessage({ conversationId: selectedConversation.id, body })
      startTransition(() => {
        setConversations((current) => current.map((conversation) =>
          conversation.id === updated.id ? updated : conversation,
        ))
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The message could not be sent.')
    } finally {
      setIsSending(false)
    }
  }

  const changeModel = async (modelId: string) => {
    if (!selectedConversation || modelId === selectedConversation.activeModelId) return
    setIsSending(true)
    setError(null)
    try {
      const updated = await api.changeModel(selectedConversation.id, modelId)
      startTransition(() => {
        setConversations((current) => current.map((item) => item.id === updated.id ? updated : item))
        setSummaries((current) => current.map((item) => item.id === updated.id ? { ...item, activeModelId: updated.activeModelId } : item))
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The model could not be changed.')
    } finally {
      setIsSending(false)
    }
  }

  const renameConversation = async (title: string) => {
    if (!selectedConversation || title === selectedConversation.title) return
    setIsRenaming(true)
    setError(null)
    try {
      const updated = await api.renameConversation(selectedConversation.id, title)
      startTransition(() => {
        setConversations((current) => current.map((item) => item.id === updated.id ? updated : item))
        setSummaries((current) => current.map((item) =>
          item.id === updated.id ? { ...item, title: updated.title } : item,
        ))
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The conversation could not be renamed.')
    } finally {
      setIsRenaming(false)
    }
  }

  const deleteConversation = async () => {
    if (!selectedConversation
      || !window.confirm('Delete this conversation and its encrypted transcript?')) return
    setError(null)
    try {
      await api.deleteConversation(selectedConversation.id)
      const remaining = conversations.filter(({ id }) => id !== selectedConversation.id)
      startTransition(() => {
        setConversations(remaining)
        const remainingSummaries = summaries.filter(({ id }) => id !== selectedConversation.id)
        setSummaries(remainingSummaries)
        setSelectedId(remainingSummaries[0]?.id ?? '')
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The conversation could not be deleted.')
    }
  }

  if (!selectedConversation && !isLoadingConversation && view === 'chat') {
    return (
      <main className="empty-app">
        <p>No conversations are available.</p>
        <label htmlFor="new-conversation-model">Model for this conversation</label>
        <select id="new-conversation-model" value={selectedModelId} onChange={(event) => setSelectedModelId(event.target.value)}>
          {models.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
        </select>
        <button type="button" onClick={() => void createConversation()}>Start a conversation</button>
        <button type="button" onClick={() => setView('monitor')}>Open System Monitor</button>
        {error ? <p className="request-error" role="alert">{error}</p> : null}
      </main>
    )
  }

  return (
    <div className="app-shell">
      <button className="privacy-lock-button" type="button" onClick={onLock}>Lock now</button>
      <Sidebar
        conversations={summaries}
        selectedId={selectedId}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((open) => !open)}
        onNewConversation={() => void createConversation()}
        onSelectConversation={(id) => void selectConversation(id)}
        onSettings={() => setSettingsOpen(true)}
        onMonitor={() => { setView('monitor'); setSidebarOpen(false) }}
      />
      {view === 'monitor' ? <SystemMonitor api={api} /> : <main className="chat-main">
        <ConversationHeader
          key={selectedConversation?.id}
          title={selectedConversation?.title ?? 'Loading conversation'}
          onDelete={() => void deleteConversation()}
          models={models}
          activeModelId={selectedConversation?.activeModelId ?? null}
          disabled={isSending || isRenaming}
          onRename={(title) => void renameConversation(title)}
          onChangeModel={(modelId) => void changeModel(modelId)}
        />
        {selectedConversation ? <MessageList messages={selectedConversation.messages} /> : <p className="conversation-loading">Loading encrypted conversation…</p>}
        {isSending ? <p className="response-pending" role="status">The selected model is generating a response…</p> : null}
        {error ? <p className="request-error" role="alert">{error}</p> : null}
        <Composer disabled={isSending} onSend={sendMessage} />
      </main>}
      {settingsOpen ? (
        <div className="settings-backdrop" role="presentation" onClick={() => setSettingsOpen(false)}>
          <section className="settings-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title" onClick={(event) => event.stopPropagation()}>
            <div className="settings-heading"><h2 id="settings-title">Session settings</h2><button type="button" onClick={() => setSettingsOpen(false)}>Close</button></div>
            <dl><dt>New-chat model</dt><dd>{models.find((item) => item.id === selectedModelId)?.label ?? selectedModelId}</dd><dt>Provider</dt><dd>{models.find((item) => item.id === selectedModelId)?.provider ?? 'Local or test adapter'}</dd><dt>Transcript storage</dt><dd>{modelConfiguration.storageLabel}</dd><dt>Inference mode</dt><dd>{modelConfiguration.modelBackend === 'openrouter' ? 'Privacy-restricted hosted inference' : 'Self-hosted inference'}</dd><dt>Response display</dt><dd>Shown once generation completes</dd></dl>
            <label className="settings-model-label" htmlFor="settings-model">Default for new conversations</label>
            <select id="settings-model" value={models.some((item) => item.id === selectedModelId) ? selectedModelId : ''} onChange={(event) => setSelectedModelId(event.target.value)}>
              {models.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
              {modelConfiguration.customOpenRouterModelAllowed ? <option value="">Custom OpenRouter model ID</option> : null}
            </select>
            {modelConfiguration.customOpenRouterModelAllowed ? <input className="settings-model-input" aria-label="Custom OpenRouter model ID" value={models.some((item) => item.id === selectedModelId) ? '' : selectedModelId} onChange={(event) => setSelectedModelId(event.target.value)} placeholder="organisation/model-name" /> : null}
            <p className="settings-note">GPU temperature and total GPU memory require a dedicated remote telemetry endpoint; they are not inferred from the browser.</p>
          </section>
        </div>
      ) : null}
    </div>
  )
}
