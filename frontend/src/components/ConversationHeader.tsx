import { PrivacyDetails } from './PrivacyDetails'
import type { ModelOption } from '../domain/chat'

interface ConversationHeaderProps {
  readonly title: string
  readonly onDelete: () => void
  readonly models: readonly ModelOption[]
  readonly activeModelId: string | null
  readonly disabled: boolean
  readonly onChangeModel: (modelId: string) => void
}

export function ConversationHeader({ title, onDelete, models, activeModelId, disabled, onChangeModel }: ConversationHeaderProps) {
  return (
    <header className="conversation-header">
      <h1>{title}</h1>
      <div className="conversation-actions">
        <label className="sr-only" htmlFor="conversation-model">Conversation model</label>
        <select id="conversation-model" className="conversation-model" value={activeModelId ?? ''} disabled={disabled} onChange={(event) => onChangeModel(event.target.value)}>
          {models.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
        </select>
        <button className="delete-conversation" type="button" onClick={onDelete}>
          Delete conversation
        </button>
        <PrivacyDetails />
      </div>
    </header>
  )
}
