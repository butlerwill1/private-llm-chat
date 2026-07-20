import { startTransition, useState } from 'react'
import { Composer } from './components/Composer'
import { ConversationHeader } from './components/ConversationHeader'
import { MessageList } from './components/MessageList'
import { Sidebar } from './components/Sidebar'
import type { ChatApi, Conversation, ModelChoice } from './domain/chat'

interface AppProps {
  readonly api: ChatApi
  readonly initialConversations: readonly Conversation[]
}

export function App({ api, initialConversations }: AppProps) {
  const [conversations, setConversations] = useState<readonly Conversation[]>(() => initialConversations)
  const [selectedId, setSelectedId] = useState(initialConversations[0]?.id ?? '')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const selectedConversation = conversations.find(({ id }) => id === selectedId) ?? conversations[0]

  const selectConversation = (id: string) => {
    setSelectedId(id)
    setSidebarOpen(false)
  }

  const createConversation = async () => {
    const conversation = await api.createConversation()
    startTransition(() => {
      setConversations((current) => [conversation, ...current])
      setSelectedId(conversation.id)
      setSidebarOpen(false)
    })
  }

  const sendMessage = async (body: string, model: ModelChoice) => {
    if (!selectedConversation) return
    setIsSending(true)
    try {
      const updated = await api.sendMessage({ conversationId: selectedConversation.id, body, model })
      startTransition(() => {
        setConversations((current) => current.map((conversation) =>
          conversation.id === updated.id ? updated : conversation,
        ))
      })
    } finally {
      setIsSending(false)
    }
  }

  if (!selectedConversation) {
    return <main className="empty-app">No conversations are available.</main>
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
        <ConversationHeader title={selectedConversation.title} />
        <MessageList messages={selectedConversation.messages} />
        <Composer disabled={isSending} onSend={sendMessage} />
      </main>
    </div>
  )
}
