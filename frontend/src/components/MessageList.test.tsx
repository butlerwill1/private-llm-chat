import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MessageList } from './MessageList'

describe('MessageList', () => {
  it('renders assistant Markdown while preserving user text literally', () => {
    render(
      <MessageList messages={[
        {
          id: 'assistant-1',
          author: 'assistant',
          body: '## Useful answer\n\n**Important** detail\n\n- first point\n- second point\n\n[Safe link](https://example.com)',
          usage: null,
        },
        {
          id: 'user-1',
          author: 'user',
          body: '<strong>This is my literal message</strong>',
          usage: null,
        },
      ]} />,
    )

    expect(screen.getByRole('heading', { name: 'Useful answer' })).toBeVisible()
    expect(screen.getByText('Important').tagName).toBe('STRONG')
    expect(screen.getByText('first point')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Safe link' })).toHaveAttribute('href', 'https://example.com')
    expect(screen.getByText('<strong>This is my literal message</strong>')).toBeVisible()
  })

  it('labels request-level tokens and a shared provider cost on both messages', () => {
    const usage = {
      inputTokens: 1284,
      outputTokens: 96,
      totalTokens: 1380,
      cachedInputTokens: 1024,
      cacheWriteInputTokens: 0,
      reasoningTokens: 18,
      costUsd: '0.002341',
      costBasis: 'provider_reported' as const,
      model: 'provider/model',
      modelLabel: 'Provider Model',
      provider: 'provider',
    }
    render(<MessageList messages={[
      { id: 'user-usage', author: 'user', body: 'Question', usage },
      { id: 'assistant-usage', author: 'assistant', body: 'Answer', usage },
    ]} />)

    expect(screen.getByText('Request input: 1,284 tokens · 1,024 cached · Shared turn cost: $0.002341')).toBeVisible()
    expect(screen.getByText('Provider Model · Response output: 96 tokens · 18 reasoning · Shared turn cost: $0.002341')).toBeVisible()
    expect(screen.getAllByText('Token and cost breakdown')).toHaveLength(2)
    expect(screen.getAllByText('Cached input read')).toHaveLength(2)
    expect(screen.getAllByText('1,024 tokens')).toHaveLength(2)
    expect(screen.getAllByText('Cache write')).toHaveLength(2)
    expect(screen.getAllByText('0 tokens')).toHaveLength(2)
    expect(screen.getAllByText('Total tokens')).toHaveLength(2)
    expect(screen.getAllByText('1,380 tokens')).toHaveLength(2)
    expect(screen.getAllByText('Charged total')).toHaveLength(2)
    expect(screen.getAllByText('$0.002341')).toHaveLength(2)
    expect(screen.getAllByText(/must be counted only once/)).toHaveLength(2)
  })
})
