import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { DemoChatApi } from './data/demoChatApi'
import './styles.css'

const api = new DemoChatApi()
const initialConversations = await api.listConversations()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App api={api} initialConversations={initialConversations} />
  </StrictMode>,
)
