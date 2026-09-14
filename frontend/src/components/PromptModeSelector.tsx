import { useState } from 'react'
import type { PromptMode } from '../domain/chat'

interface Props {
  readonly modes: readonly PromptMode[]
  readonly selectedId: string
  readonly disabled: boolean
  readonly onChange: (id: string) => void
  readonly conversationId: string
}

export function PromptModeSelector({ modes, selectedId, disabled, onChange, conversationId }: Props) {
  const [storageError, setStorageError] = useState(false)
  return (
    <div className="prompt-mode-control">
      <label htmlFor="prompt-mode">Prompt mode</label>
      <select id="prompt-mode" className="conversation-model" value={selectedId} disabled={disabled} onChange={(event) => {
        onChange(event.target.value)
        try {
          localStorage.setItem(`private-chat:prompt-mode:v1:${conversationId}`, event.target.value)
          setStorageError(false)
        } catch {
          setStorageError(true)
        }
      }}>
        {modes.map((mode) => <option key={mode.id} value={mode.id}>{mode.label}</option>)}
      </select>
      <small>{storageError ? 'Selected for this session; browser could not save the choice.' : 'Applies to your next message. Previous messages stay in context.'}</small>
    </div>
  )
}
