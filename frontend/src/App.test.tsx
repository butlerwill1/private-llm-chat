import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { DemoChatApi } from './data/demoChatApi'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function renderApp() {
  const api = new DemoChatApi()
  const conversations = await api.listConversations()
  return { user: userEvent.setup(), ...render(<App api={api} initialConversations={conversations} />) }
}

describe('Private Chat', () => {
  it('selects a conversation', async () => {
    const { user } = await renderApp()
    await user.click(screen.getByRole('button', { name: 'Project decisions' }))
    expect(screen.getByRole('heading', { name: 'Project decisions' })).toBeInTheDocument()
    expect(screen.getByText('What decision would you like to work through?')).toBeInTheDocument()
  })

  it('creates a new conversation', async () => {
    const { user } = await renderApp()
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(await screen.findByRole('heading', { name: 'New conversation' })).toBeInTheDocument()
  })

  it('sends a message through the API boundary', async () => {
    const { user } = await renderApp()
    await user.type(screen.getByLabelText('Write a message'), 'A calm morning walk.')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('A calm morning walk.')).toBeInTheDocument()
    expect(screen.getByText('Thank you for sharing that. What feels most important about it?')).toBeInTheDocument()
  })

  it('discloses privacy details', async () => {
    const { user } = await renderApp()
    await user.click(screen.getByText('Encrypted'))
    expect(screen.getByText('Your conversation is private')).toBeVisible()
  })

  it('deletes the selected conversation after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { user } = await renderApp()
    await user.click(screen.getByRole('button', { name: 'Delete conversation' }))
    expect(screen.queryByRole('heading', { name: 'Sunday reflection' })).not.toBeInTheDocument()
  })
})
