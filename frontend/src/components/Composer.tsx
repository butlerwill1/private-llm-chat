import { useState, type FormEvent } from 'react'
import type { ModelChoice } from '../domain/chat'
import { SendIcon } from './Icons'

interface ComposerProps {
  readonly disabled: boolean
  readonly onSend: (body: string, model: ModelChoice) => Promise<void>
}

export function Composer({ disabled, onSend }: ComposerProps) {
  const [body, setBody] = useState('')
  const [model, setModel] = useState<ModelChoice>('private')

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const message = body.trim()
    if (message.length === 0 || disabled) return
    setBody('')
    await onSend(message, model)
  }

  return (
    <div className="composer-area">
      <form className="composer" onSubmit={(event) => void submit(event)}>
        <label className="sr-only" htmlFor="message">Write a message</label>
        <textarea
          id="message"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="Write a message..."
          rows={1}
          disabled={disabled}
        />
        <label className="sr-only" htmlFor="model">Model</label>
        <select id="model" value={model} onChange={(event) => setModel(event.target.value as ModelChoice)} disabled={disabled}>
          <option value="private">Private model</option>
          <option value="openrouter">OpenRouter</option>
        </select>
        <button className="send-button" type="submit" disabled={disabled || body.trim().length === 0} aria-label="Send message">
          <SendIcon />
        </button>
      </form>
      <p className="disclaimer">AI can make mistakes. For emergencies, contact the appropriate professional service.</p>
    </div>
  )
}
