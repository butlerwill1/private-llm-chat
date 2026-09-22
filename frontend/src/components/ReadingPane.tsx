import { useLayoutEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../domain/chat'
import { MessageList } from './MessageList'

export interface LiveTurn {
  readonly id: string
  readonly conversationId: string
  readonly user: string
  readonly answer: string
  readonly reasoning?: string
  readonly status: string
  readonly phase: 'generating' | 'interrupted'
}

interface ReadingPaneProps {
  readonly messages: readonly ChatMessage[]
  readonly live: LiveTurn | null
  readonly onStop: () => void
  readonly onDiscard: () => void
}

export function ReadingPane({ messages, live, onStop, onDiscard }: ReadingPaneProps) {
  const viewport = useRef<HTMLDivElement>(null)
  const anchoredTurn = useRef<string | null>(null)
  const [follow, setFollow] = useState(false)
  const streamId = live?.id
  const answer = live?.answer
  const reasoning = live?.reasoning
  const displayed = live ? [...messages,
    { id: `${live.id}-user`, author: 'user' as const, body: live.user, usage: null },
    { id: live.id, author: 'assistant' as const, body: live.answer, usage: null, reasoning: live.reasoning ?? null },
  ] : messages

  useLayoutEffect(() => {
    const pane = viewport.current
    if (!pane) return
    if (streamId && anchoredTurn.current !== streamId) {
      anchoredTurn.current = streamId
      const start = pane.querySelector<HTMLElement>('[data-stream-answer]')
      if (start) pane.scrollTop += start.getBoundingClientRect().top - pane.getBoundingClientRect().top - 24
    } else if (follow) {
      const end = pane.querySelector<HTMLElement>('[data-answer-end]')
      if (end) pane.scrollTop += end.getBoundingClientRect().bottom - pane.getBoundingClientRect().bottom + 24
    }
  }, [streamId, answer, reasoning, follow])

  const jump = () => {
    const pane = viewport.current
    const end = pane?.querySelector<HTMLElement>('[data-answer-end]')
    if (pane && end) pane.scrollTop += end.getBoundingClientRect().bottom - pane.getBoundingClientRect().bottom + 24
  }

  return <section className="reading-pane" aria-label="Response reading area">
    <div className="reading-viewport" ref={viewport} tabIndex={0} onWheel={() => setFollow(false)} onTouchStart={() => setFollow(false)} onPointerDown={() => setFollow(false)} onKeyDown={(event) => { if (['ArrowUp', 'PageUp', 'Home'].includes(event.key)) setFollow(false) }}>
      <MessageList messages={displayed} draftId={live?.id} />
      <div data-answer-end />
      <div className="reading-spacer" aria-hidden="true" />
    </div>
    <div className="stream-controls">
      <span role="status">{live?.status ?? 'Ready'}</span>
      <label><input type="checkbox" checked={follow} onChange={(event) => setFollow(event.target.checked)} /> Follow latest</label>
      <button type="button" onClick={jump}>Jump to latest</button>
      {live?.phase === 'generating' ? <button className="stream-action" type="button" onClick={onStop}>Stop</button> : null}
      {live?.phase === 'interrupted' ? <button className="stream-action" type="button" onClick={onDiscard}>Discard unsaved draft</button> : null}
    </div>
  </section>
}
