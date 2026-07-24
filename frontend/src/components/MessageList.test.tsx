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
        },
        {
          id: 'user-1',
          author: 'user',
          body: '<strong>This is my literal message</strong>',
        },
      ]} />,
    )

    expect(screen.getByRole('heading', { name: 'Useful answer' })).toBeVisible()
    expect(screen.getByText('Important').tagName).toBe('STRONG')
    expect(screen.getByText('first point')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Safe link' })).toHaveAttribute('href', 'https://example.com')
    expect(screen.getByText('<strong>This is my literal message</strong>')).toBeVisible()
  })
})
