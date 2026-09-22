import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ReadingPane, type LiveTurn } from './ReadingPane'

afterEach(cleanup)

it('keeps manual scroll position as chunks arrive and exposes stop/follow controls', () => {
  const live: LiveTurn = { id: 'draft', conversationId: 'chat', user: 'hello', answer: 'First line', status: 'Generating…', phase: 'generating' }
  const stop = vi.fn()
  const props = { messages: [], live, onStop: stop, onDiscard: vi.fn() }
  const { container, rerender } = render(<ReadingPane {...props} />)
  const viewport = container.querySelector('.reading-viewport')!
  viewport.scrollTop = 150
  rerender(<ReadingPane {...props} live={{ ...live, answer: 'First line\nMore text' }} />)
  expect(viewport.scrollTop).toBe(150)
  expect(screen.getByRole('checkbox', { name: 'Follow latest' })).not.toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
  expect(stop).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Follow latest' }))
  fireEvent.wheel(viewport)
  expect(screen.getByRole('checkbox', { name: 'Follow latest' })).not.toBeChecked()
})
