import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MessageList } from './MessageList'

describe('MessageList', () => {
  it('renders completed thinking as safe Markdown in a separate disclosure', async () => {
    const user = userEvent.setup()
    const { container } = render(<MessageList messages={[
      { id: 'answer', author: 'assistant', body: 'Final answer', usage: null, reasoning: '<img src=x onerror=alert(1)>\n\n## Consider the options\n\n**Check** the `details`.' },
      { id: 'plain', author: 'assistant', body: 'No thinking', usage: null },
    ]} />)
    const trace = screen.getByRole('heading', { name: 'Consider the options' })
    expect(trace).not.toBeVisible()
    expect(screen.getAllByText('Thinking')).toHaveLength(1)
    await user.click(screen.getByText('Thinking'))
    expect(trace).toBeVisible()
    expect(screen.getByText('Check').tagName).toBe('STRONG')
    expect(screen.getByText('details').tagName).toBe('CODE')
    expect(screen.getByText('Final answer')).toBeVisible()
    expect(container.querySelector('img')).toBeNull()
    await user.click(screen.getByText('Thinking'))
    expect(trace).not.toBeVisible()
  })

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

  it('renders extended Markdown in a completed assistant reply', () => {
    const { container } = render(<MessageList messages={[
      {
        id: 'assistant-gfm', author: 'assistant', usage: null,
        body: '> A useful note\n\n- [x] Done\n- [ ] Next\n\n~~Old wording~~\n\n| Name | Value |\n| --- | --- |\n| Pause | Helpful |\n\n`inline code`',
      },
    ]} />)

    expect(screen.getByText('A useful note').closest('blockquote')).not.toBeNull()
    const tasks = container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')
    expect(tasks).toHaveLength(2)
    expect(tasks[0]).toBeChecked()
    expect(tasks[1]).not.toBeChecked()
    expect(screen.getByText('Old wording').tagName).toBe('DEL')
    expect(screen.getByRole('table')).toBeVisible()
    expect(screen.getByText('inline code').tagName).toBe('CODE')
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

  it('keeps only an in-progress streamed reply as plain text', () => {
    const heading = '### 3. The Value of Pausing'
    const { rerender, container, getByText, getByRole } = render(<MessageList messages={[
      { id: 'reply', author: 'assistant', body: heading, usage: null },
    ]} draftId="reply" />)

    expect(container.querySelector('h1, h2, h3')).toBeNull()
    expect(getByText(heading)).toHaveClass('stream-text')

    rerender(<MessageList messages={[
      { id: 'reply', author: 'assistant', body: heading, usage: null },
    ]} />)

    expect(getByRole('heading', { name: '3. The Value of Pausing' })).toBeVisible()
  })
})
