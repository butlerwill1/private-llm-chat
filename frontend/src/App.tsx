import { startTransition, useState } from 'react'
import { Composer } from './components/Composer'
import { ConversationHeader } from './components/ConversationHeader'
import { MessageList } from './components/MessageList'
import { Sidebar } from './components/Sidebar'
import type { ChatApi, Conversation } from './domain/chat'

interface AppProps {
  readonly api: ChatApi
  readonly initialConversations: readonly Conversation[]
}

export function App({ api, initialConversations }: AppProps) {
  const [conversations, setConversations] = useState<readonly Conversation[]>(() => initialConversations)
  const [selectedId, setSelectedId] = useState(initialConversations[0]?.id ?? '')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectedConversation = conversations.find(({ id }) => id === selectedId) ?? conversations[0]

  const selectConversation = (id: string) => {
    setSelectedId(id)
    setSidebarOpen(false)
  }

  const createConversation = async () => {
    setError(null)
    try {
      const conversation = await api.createConversation()
      startTransition(() => {
        setConversations((current) => [conversation, ...current])
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
        setSelectedId(remaining[0]?.id ?? '')
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The conversation could not be deleted.')
    }
  }

  if (!selectedConversation) {
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
        conversations={conversations}
        selectedId={selectedConversation.id}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((open) => !open)}
        onNewConversation={() => void createConversation()}
        onSelectConversation={selectConversation}
      />
      <main className="chat-main">
        <ConversationHeader
          title={selectedConversation.title}
          onDelete={() => void deleteConversation()}
        />
        <MessageList messages={selectedConversation.messages} />
        {error ? <p className="request-error" role="alert">{error}</p> : null}
        <Composer disabled={isSending} onSend={sendMessage} />
      </main>
    </div>
  )
}
