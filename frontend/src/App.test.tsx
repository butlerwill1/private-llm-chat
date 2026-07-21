import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { DemoChatApi } from './data/demoChatApi'

// React Testing Library leaves rendered DOM and spies in process by default.
// Resetting both after every case prevents one interaction influencing another.
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function renderApp() {
  // The in-memory API exercises the same ChatApi interface as the HTTP adapter,
  // while keeping component tests deterministic and independent of FastAPI.
  const api = new DemoChatApi()
  const conversations = await api.listConversations()
  return { user: userEvent.setup(), ...render(<App api={api} initialConversations={conversations} />) }
}

describe('Private Chat', () => {
  it('selects a conversation', async () => {
    // Selecting a sidebar item must change both the header and transcript. This
    // proves the application changed its selected ID, not just the button style.
    const { user } = await renderApp()
    await user.click(screen.getByRole('button', { name: 'Project decisions' }))
    expect(screen.getByRole('heading', { name: 'Project decisions' })).toBeInTheDocument()
    expect(screen.getByText('What decision would you like to work through?')).toBeInTheDocument()
  })

  it('creates a new conversation', async () => {
    // New conversation creation crosses the asynchronous ChatApi boundary, so
    // findByRole waits for the returned aggregate to become selected and visible.
    const { user } = await renderApp()
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(await screen.findByRole('heading', { name: 'New conversation' })).toBeInTheDocument()
  })

  it('sends a message through the API boundary', async () => {
    // Interact through accessible controls as a user would. Seeing both messages
    // verifies the user's text reached the API and its returned state replaced
    // the conversation displayed by the application.
    const { user } = await renderApp()
    await user.type(screen.getByLabelText('Write a message'), 'A calm morning walk.')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('A calm morning walk.')).toBeInTheDocument()
    expect(screen.getByText('Thank you for sharing that. What feels most important about it?')).toBeInTheDocument()
  })

  it('discloses privacy details', async () => {
    // Privacy information must be discoverable from the visible encryption label
    // instead of existing only in documentation outside the application.
    const { user } = await renderApp()
    await user.click(screen.getByText('Encrypted'))
    expect(screen.getByText('Your conversation is private')).toBeVisible()
  })

  it('deletes the selected conversation after confirmation', async () => {
    // Stub only the browser confirmation boundary; deletion itself still travels
    // through ChatApi and must remove the selected transcript from rendered state.
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { user } = await renderApp()
    await user.click(screen.getByRole('button', { name: 'Delete conversation' }))
    // queryByRole returns null rather than throwing, making it suitable for an
    // assertion that the deleted conversation is no longer present.
    expect(screen.queryByRole('heading', { name: 'Sunday reflection' })).not.toBeInTheDocument()
  })
})
