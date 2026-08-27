import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ChatLoader } from './ChatLoader'
import { PrivacyGate } from './components/PrivacyGate'
import { HttpChatApi } from './data/httpChatApi'
import './styles.css'

const api = new HttpChatApi()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PrivacyGate>{(lock) => <ChatLoader api={api} onLock={lock} />}</PrivacyGate>
  </StrictMode>,
)
