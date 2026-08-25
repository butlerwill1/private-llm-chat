import Markdown from 'react-markdown'
import type { ChatMessage, TurnUsage } from '../domain/chat'

interface MessageListProps {
  readonly messages: readonly ChatMessage[]
}

function usageText(author: ChatMessage['author'], usage: TurnUsage | null): string {
  if (usage === null) return 'Usage unavailable — predates tracking.'
  const primaryTokens = author === 'user' ? usage.inputTokens : usage.outputTokens
  if (primaryTokens === null) return 'Usage unavailable — provider did not report token counts.'
  const parts = [
    author === 'user' ? `Request input: ${primaryTokens.toLocaleString()} tokens` : `Response output: ${primaryTokens.toLocaleString()} tokens`,
  ]
  if (author === 'user' && usage.cachedInputTokens !== null && usage.cachedInputTokens > 0) {
    parts.push(`${usage.cachedInputTokens.toLocaleString()} cached`)
  }
  if (author === 'assistant' && usage.reasoningTokens !== null && usage.reasoningTokens > 0) {
    parts.push(`${usage.reasoningTokens.toLocaleString()} reasoning`)
  }
  if (usage.costBasis === 'provider_reported' && usage.costUsd !== null) {
    parts.push(`Shared turn cost: $${usage.costUsd}`)
  } else if (usage.costBasis === 'self_hosted_unallocated') {
    parts.push('Self-hosted cost not allocated')
  } else {
    parts.push('Cost unavailable')
  }
  return parts.join(' · ')
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <ol className="message-list" aria-label="Conversation messages" aria-live="polite">
      {messages.map((message) => (
        <li className={`message message--${message.author}`} key={message.id}>
          {message.author === 'assistant' ? <div className="assistant-avatar" aria-hidden="true">AI</div> : null}
          <div className="message-content">
            <strong>{message.author === 'assistant' ? 'Private Chat' : 'You'}</strong>
            {message.author === 'assistant' ? (
              <Markdown
                components={{
                  a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  ),
                }}
              >
                {message.body}
              </Markdown>
            ) : <p>{message.body}</p>}
            <p className="message-usage" title={message.usage === null ? undefined : `${message.usage.model} via ${message.usage.provider}; cost is shared with the paired message.`}>
              {usageText(message.author, message.usage)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  )
}
