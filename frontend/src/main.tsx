import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { HttpChatApi } from './data/httpChatApi'
import './styles.css'

const api = new HttpChatApi()

async function bootstrap() {
  const root = createRoot(document.getElementById('root')!)
  try {
    const initialConversations = await api.listConversations()
    root.render(
      <StrictMode>
        <App api={api} initialConversations={initialConversations} />
      </StrictMode>,
    )
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : 'The local chat API is unavailable.'
    root.render(
      <main className="empty-app">
        <h1>Private Chat could not start</h1>
        <p role="alert">{message}</p>
        <p>Start the FastAPI backend on 127.0.0.1:8000, then refresh this page.</p>
      </main>,
    )
  }
}

void bootstrap()
