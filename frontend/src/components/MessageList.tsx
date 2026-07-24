import Markdown from 'react-markdown'
import type { ChatMessage } from '../domain/chat'

interface MessageListProps {
  readonly messages: readonly ChatMessage[]
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
          </div>
        </li>
      ))}
    </ol>
  )
}
