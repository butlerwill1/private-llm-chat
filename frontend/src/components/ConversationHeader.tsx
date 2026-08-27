import { useState } from 'react'
import { PrivacyDetails } from './PrivacyDetails'
import type { ModelOption } from '../domain/chat'

interface ConversationHeaderProps {
  readonly title: string
  readonly onDelete: () => void
  readonly models: readonly ModelOption[]
  readonly activeModelId: string | null
  readonly disabled: boolean
  readonly onRename: (title: string) => void
  readonly onChangeModel: (modelId: string) => void
}

export function ConversationHeader({ title, onDelete, models, activeModelId, disabled, onRename, onChangeModel }: ConversationHeaderProps) {
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [draftTitle, setDraftTitle] = useState(title)

  const saveTitle = () => {
    const cleanedTitle = draftTitle.trim()
    if (!cleanedTitle || cleanedTitle === title) return
    onRename(cleanedTitle)
    setIsEditingTitle(false)
  }

  return (
    <header className="conversation-header">
      <div className="conversation-title-area">
        {isEditingTitle ? (
          <form className="conversation-title-form" onSubmit={(event) => { event.preventDefault(); saveTitle() }}>
            <label className="sr-only" htmlFor="conversation-title">Conversation name</label>
            <input
              id="conversation-title"
              value={draftTitle}
              maxLength={200}
              autoFocus
              disabled={disabled}
              onChange={(event) => setDraftTitle(event.target.value)}
            />
            <button type="submit" disabled={disabled || !draftTitle.trim() || draftTitle.trim() === title}>Save</button>
            <button type="button" onClick={() => { setDraftTitle(title); setIsEditingTitle(false) }}>Cancel</button>
          </form>
        ) : (
          <>
            <h1>{title}</h1>
            <button className="edit-conversation-title" type="button" disabled={disabled} onClick={() => { setDraftTitle(title); setIsEditingTitle(true) }}>Edit name</button>
          </>
        )}
      </div>
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
