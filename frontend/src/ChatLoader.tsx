import { useEffect, useState } from 'react'
import { App } from './App'
import type { ChatApi, Conversation, ConversationSummary, ModelConfiguration, ModelOption } from './domain/chat'

interface LoadedApp {
  readonly conversation: Conversation | null
  readonly summaries: readonly ConversationSummary[]
  readonly models: readonly ModelOption[]
  readonly modelConfiguration: ModelConfiguration
}

interface ChatLoaderProps {
  readonly api: ChatApi
  readonly onLock: () => void
}

export function ChatLoader({ api, onLock }: ChatLoaderProps) {
  const [loaded, setLoaded] = useState<LoadedApp | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [summaries, models, modelConfiguration] = await Promise.all([
          api.listConversationSummaries(), api.listModels(), api.getModelConfiguration(),
        ])
        const conversation = summaries[0] ? await api.getConversation(summaries[0].id) : null
        if (!cancelled) setLoaded({ conversation, summaries, models, modelConfiguration })
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'The local chat API is unavailable.')
      }
    }
    void load()
    return () => { cancelled = true }
  }, [api])

  if (error) return <main className="empty-app"><h1>Private Chat could not start</h1><p role="alert">{error}</p><p>Start the FastAPI backend on 127.0.0.1:8000, then refresh this page.</p></main>
  if (!loaded) return <main className="empty-app"><p>Loading Private Chat…</p></main>
  return <App api={api} initialConversations={loaded.conversation ? [loaded.conversation] : []} initialSummaries={loaded.summaries} models={loaded.models} modelConfiguration={loaded.modelConfiguration} onLock={onLock} />
}
