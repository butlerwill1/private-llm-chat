import type { ConversationSummary } from '../domain/chat'
import { LockIcon, MenuIcon, MessageIcon, PlusCircleIcon, SettingsIcon } from './Icons'

interface SidebarProps {
  readonly conversations: readonly ConversationSummary[]
  readonly selectedId: string
  readonly isOpen: boolean
  readonly onToggle: () => void
  readonly onNewConversation: () => void
  readonly onSelectConversation: (id: string) => void
  readonly onSettings: () => void
}

export function Sidebar({ conversations, selectedId, isOpen, onToggle, onNewConversation, onSelectConversation, onSettings }: SidebarProps) {
  return (
    <aside className={isOpen ? 'sidebar sidebar--open' : 'sidebar'} aria-label="Chat navigation">
      <div className="brand-row">
        <LockIcon className="brand-icon" />
        <span>Private Chat</span>
        <button className="mobile-menu-button" type="button" onClick={onToggle} aria-expanded={isOpen} aria-label="Toggle conversations">
          <MenuIcon />
        </button>
      </div>
      <div className="sidebar-content">
        <button className="new-conversation" type="button" onClick={onNewConversation}>
          <PlusCircleIcon />
          New conversation
        </button>
        <nav aria-label="Conversations">
          <p className="nav-label">Conversations</p>
          <ul className="conversation-list">
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <button
                  className={conversation.id === selectedId ? 'conversation-link conversation-link--selected' : 'conversation-link'}
                  type="button"
                  onClick={() => onSelectConversation(conversation.id)}
                  aria-current={conversation.id === selectedId ? 'page' : undefined}
                >
                  <MessageIcon />
                  <span>{conversation.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="sidebar-divider" />
        <button className="settings-button" type="button" onClick={onSettings}>
          <SettingsIcon />
          Settings
        </button>
      </div>
    </aside>
  )
}
