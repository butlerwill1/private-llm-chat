import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage, TurnUsage } from '../domain/chat'

interface MessageListProps {
  readonly messages: readonly ChatMessage[]
  readonly draftId?: string | undefined
}

function formatTokenCount(tokens: number | null): string {
  return tokens === null ? 'Not reported' : `${tokens.toLocaleString()} tokens`
}

function costText(usage: TurnUsage): string {
  if (usage.costBasis === 'provider_reported' && usage.costUsd !== null) {
    return `$${usage.costUsd}`
  }
  if (usage.costBasis === 'self_hosted_unallocated') {
    return 'Self-hosted cost not allocated'
  }
  return 'Cost unavailable'
}

function usageText(author: ChatMessage['author'], usage: TurnUsage | null): string {
  if (usage === null) return 'Usage unavailable — predates tracking.'
  const primaryTokens = author === 'user' ? usage.inputTokens : usage.outputTokens
  if (primaryTokens === null) return 'Usage unavailable — provider did not report token counts.'
  const parts = [
    author === 'assistant' ? usage.modelLabel : '',
    author === 'user' ? `Request input: ${primaryTokens.toLocaleString()} tokens` : `Response output: ${primaryTokens.toLocaleString()} tokens`,
  ]
  if (author === 'user' && usage.cachedInputTokens !== null && usage.cachedInputTokens > 0) {
    parts.push(`${usage.cachedInputTokens.toLocaleString()} cached`)
  }
  if (author === 'assistant' && usage.reasoningTokens !== null && usage.reasoningTokens > 0) {
    parts.push(`${usage.reasoningTokens.toLocaleString()} reasoning`)
  }
  if (usage.costBasis === 'provider_reported' && usage.costUsd !== null) {
    parts.push(`Shared turn cost: ${costText(usage)}`)
  } else if (usage.costBasis === 'self_hosted_unallocated') {
    parts.push(costText(usage))
  } else {
    parts.push(costText(usage))
  }
  return parts.filter(Boolean).join(' · ')
}

function UsageBreakdown({ usage }: { readonly usage: TurnUsage }) {
  return (
    <details className="message-usage-details">
      <summary>Token and cost breakdown</summary>
      <dl>
        <div><dt>Request input</dt><dd>{formatTokenCount(usage.inputTokens)}</dd></div>
        <div><dt>Cached input read</dt><dd>{formatTokenCount(usage.cachedInputTokens)}</dd></div>
        <div><dt>Cache write</dt><dd>{formatTokenCount(usage.cacheWriteInputTokens)}</dd></div>
        <div><dt>Response output</dt><dd>{formatTokenCount(usage.outputTokens)}</dd></div>
        <div><dt>Reasoning</dt><dd>{formatTokenCount(usage.reasoningTokens)}</dd></div>
        <div><dt>Total tokens</dt><dd>{formatTokenCount(usage.totalTokens)}</dd></div>
        <div><dt>Model</dt><dd>{usage.modelLabel}</dd></div>
        <div><dt>Provider</dt><dd>{usage.provider}</dd></div>
        <div><dt>Charged total</dt><dd>{costText(usage)}</dd></div>
      </dl>
      <p>Request input is the full prompt sent for this turn. Cached input is still processed, but may be charged at a lower provider rate; it is not necessarily free.</p>
      <p>The charged total is the single provider charge for this request/reply pair. It appears on both messages for context and must be counted only once.</p>
    </details>
  )
}

function RenderedMarkdown({ children }: { readonly children: string }) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children: linkChildren }) => (
          <a href={href} target="_blank" rel="noreferrer">
            {linkChildren}
          </a>
        ),
      }}
    >
      {children}
    </Markdown>
  )
}

export function MessageList({ messages, draftId }: MessageListProps) {
  return (
    <ol className="message-list" aria-label="Conversation messages">
      {messages.map((message) => (
        <li className={`message message--${message.author}`} key={message.id} data-stream-answer={message.id === draftId ? '' : undefined}>
          {message.author === 'assistant' ? <div className="assistant-avatar" aria-hidden="true">AI</div> : null}
          <div className="message-content">
            {message.author === 'event' ? null : <strong>{message.author === 'assistant' ? 'Private Chat' : 'You'}</strong>}
            {message.author === 'assistant' && message.reasoning ? (
              <details className="message-thinking">
                <summary>Thinking</summary>
                {message.id === draftId ? <div className="stream-text">{message.reasoning}</div> : (
                  <div className="thinking-markdown"><RenderedMarkdown>{message.reasoning}</RenderedMarkdown></div>
                )}
              </details>
            ) : null}
            {message.author === 'assistant' && message.id === draftId ? (
              <div className="stream-text">{message.body}</div>
            ) : message.author === 'assistant' ? (
              <RenderedMarkdown>{message.body}</RenderedMarkdown>
            ) : <p className="stream-text">{message.body}</p>}
            {message.author === 'event' || message.id === draftId ? null : <p className="message-usage" title={message.usage === null ? undefined : `${message.usage.model} via ${message.usage.provider}; cost is shared with the paired message.`}>
              {usageText(message.author, message.usage)}
            </p>}
            {message.author === 'event' || message.usage === null ? null : <UsageBreakdown usage={message.usage} />}
          </div>
        </li>
      ))}
    </ol>
  )
}
