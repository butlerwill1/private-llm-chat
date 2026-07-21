import { PrivacyDetails } from './PrivacyDetails'

interface ConversationHeaderProps {
  readonly title: string
  readonly onDelete: () => void
}

export function ConversationHeader({ title, onDelete }: ConversationHeaderProps) {
  return (
    <header className="conversation-header">
      <h1>{title}</h1>
      <div className="conversation-actions">
        <button className="delete-conversation" type="button" onClick={onDelete}>
          Delete conversation
        </button>
        <PrivacyDetails />
      </div>
    </header>
  )
}
