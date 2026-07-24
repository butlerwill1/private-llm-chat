import { startTransition, useState } from 'react'
import { Composer } from './components/Composer'
import { ConversationHeader } from './components/ConversationHeader'
import { MessageList } from './components/MessageList'
import { Sidebar } from './components/Sidebar'
import type { ChatApi, Conversation, ConversationSummary } from './domain/chat'

interface AppProps {
  readonly api: ChatApi
  readonly initialConversations: readonly Conversation[]
  readonly initialSummaries: readonly ConversationSummary[]
}

export function App({ api, initialConversations, initialSummaries }: AppProps) {
  const [conversations, setConversations] = useState<readonly Conversation[]>(() => initialConversations)
  const [summaries, setSummaries] = useState<readonly ConversationSummary[]>(() => initialSummaries)
  const [selectedId, setSelectedId] = useState(initialSummaries[0]?.id ?? '')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [isLoadingConversation, setIsLoadingConversation] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
      const conversation = await api.createConversation()
      startTransition(() => {
        setConversations((current) => [conversation, ...current])
        setSummaries((current) => [{ id: conversation.id, title: conversation.title }, ...current])
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

  if (!selectedConversation && !isLoadingConversation) {
    return (
      <main className="empty-app">
        <p>No conversations are available.</p>
        <button type="button" onClick={() => void createConversation()}>Start a conversation</button>
        {error ? <p className="request-error" role="alert">{error}</p> : null}
      </main>
    )
  }

  return (
    <div className="app-shell">
      <Sidebar
        conversations={summaries}
        selectedId={selectedId}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((open) => !open)}
        onNewConversation={() => void createConversation()}
        onSelectConversation={(id) => void selectConversation(id)}
        onSettings={() => setSettingsOpen(true)}
      />
      <main className="chat-main">
        <ConversationHeader
          title={selectedConversation?.title ?? 'Loading conversation'}
          onDelete={() => void deleteConversation()}
        />
        {selectedConversation ? <MessageList messages={selectedConversation.messages} /> : <p className="conversation-loading">Loading encrypted conversation…</p>}
        {isSending ? <p className="response-pending" role="status">The local model is generating a response…</p> : null}
        {error ? <p className="request-error" role="alert">{error}</p> : null}
        <Composer disabled={isSending} onSend={sendMessage} />
      </main>
      {settingsOpen ? (
        <div className="settings-backdrop" role="presentation" onClick={() => setSettingsOpen(false)}>
          <section className="settings-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title" onClick={(event) => event.stopPropagation()}>
            <div className="settings-heading"><h2 id="settings-title">Session settings</h2><button type="button" onClick={() => setSettingsOpen(false)}>Close</button></div>
            <dl><dt>Model</dt><dd>private-chat (Qwen3 8B, Q4_K_M)</dd><dt>Connection</dt><dd>Private SSM tunnel to Ollama</dd><dt>Transcript storage</dt><dd>Envelope encrypted, stored in S3</dd><dt>Response display</dt><dd>Shown once generation completes</dd></dl>
            <p className="settings-note">GPU temperature and total GPU memory require a dedicated remote telemetry endpoint; they are not inferred from the browser.</p>
          </section>
        </div>
      ) : null}
    </div>
  )
}
