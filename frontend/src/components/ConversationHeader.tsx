import { PrivacyDetails } from './PrivacyDetails'

interface ConversationHeaderProps {
  readonly title: string
}

export function ConversationHeader({ title }: ConversationHeaderProps) {
  return (
    <header className="conversation-header">
      <h1>{title}</h1>
      <PrivacyDetails />
    </header>
  )
}
