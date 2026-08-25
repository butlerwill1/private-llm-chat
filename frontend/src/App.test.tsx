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
  // Create a fresh API for each test, so mutations such as create/delete do not
  // leak into the next test case.
  const api = new DemoChatApi()
  // App expects its initial data as a prop, just as main.tsx loads data before
  // first render. `await` unwraps the Promise returned by the API interface.
  const conversations = await api.listConversations()
  const summaries = await api.listConversationSummaries()
  const models = await api.listModels()
  const modelConfiguration = await api.getModelConfiguration()
  // userEvent.setup returns an async user controller. `render` mounts App in
  // JSDOM. Object spread combines render's query helpers with `user` in one result.
  return {
    user: userEvent.setup(),
    ...render(<App api={api} initialConversations={conversations} initialSummaries={summaries} models={models} modelConfiguration={modelConfiguration} />),
  }
}

describe('Private Chat', () => {
  it('selects a conversation', async () => {
    // Selecting a sidebar item must change both the header and transcript. This
    // proves the application changed its selected ID, not just the button style.
    // Arrange: render the application and destructure its simulated user.
    const { user } = await renderApp()
    // Act: locate the button by its accessible role/name and perform a real click.
    await user.click(screen.getByRole('button', { name: 'Project decisions' }))
    // Assert both title and content. getByRole/getByText throw if no match exists,
    // and jest-dom's matcher then verifies the element is attached to the document.
    expect(screen.getByRole('heading', { name: 'Project decisions' })).toBeInTheDocument()
    expect(screen.getByText('What decision would you like to work through?')).toBeInTheDocument()
  })

  it('creates a new conversation', async () => {
    // New conversation creation crosses the asynchronous ChatApi boundary, so
    // findByRole waits for the returned aggregate to become selected and visible.
    const { user } = await renderApp()
    // Clicking calls App.createConversation, which awaits api.createConversation
    // and inserts the returned conversation into React state.
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    // `findByRole` repeatedly checks until the async state update renders or the
    // testing-library timeout expires; unlike getByRole it need not exist instantly.
    expect(await screen.findByRole('heading', { name: 'New conversation' })).toBeInTheDocument()
  })

  it('sends a message through the API boundary', async () => {
    // Interact through accessible controls as a user would. Seeing both messages
    // verifies the user's text reached the API and its returned state replaced
    // the conversation displayed by the application.
    const { user } = await renderApp()
    // getByLabelText connects the visible/accessible label to the textarea. `type`
    // emits the same sequence of keyboard/input events a browser user produces.
    await user.type(screen.getByLabelText('Write a message'), 'A calm morning walk.')
    // The button becomes enabled after non-blank text exists; clicking submits the form.
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    // Wait for the Promise returned by ChatApi.sendMessage to update React state.
    expect(await screen.findByText('A calm morning walk.')).toBeInTheDocument()
    // The deterministic DemoChatApi also appends this assistant response.
    expect(screen.getByText('Thank you for sharing that. What feels most important about it?')).toBeInTheDocument()
  })

  it('discloses privacy details', async () => {
    // Privacy information must be discoverable from the visible encryption label
    // instead of existing only in documentation outside the application.
    const { user } = await renderApp()
    // The encryption badge is found by its rendered text and clicked to open the panel.
    await user.click(screen.getByText('Encrypted'))
    // toBeVisible is stronger than presence: it also checks that CSS/attributes do
    // not hide the explanation after the disclosure control has been activated.
    expect(screen.getByText('Encrypted local storage')).toBeVisible()
    expect(screen.getByText(/privacy-restricted hosted inference/)).toBeVisible()
  })

  it('opens and closes the session settings panel', async () => {
    // Settings must be an interactive status panel rather than a decorative button.
    // Render the real sidebar and use the accessible button name a screen reader
    // would announce. This verifies that the click reaches App's panel state.
    const { user } = await renderApp()
    await user.click(screen.getByRole('button', { name: 'Settings' }))
    expect(await screen.findByRole('dialog', { name: 'Session settings' })).toBeVisible()

    // Closing through the visible button verifies the panel does not trap the
    // interface after a user has reviewed the local session information.
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog', { name: 'Session settings' })).not.toBeInTheDocument()
  })

  it('deletes the selected conversation after confirmation', async () => {
    // Stub only the browser confirmation boundary; deletion itself still travels
    // through ChatApi and must remove the selected transcript from rendered state.
    // Replace only window.confirm and force the equivalent of clicking "OK".
    // Without this, JSDOM cannot provide an interactive native confirmation box.
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { user } = await renderApp()
    // The initially selected demo conversation is "Sunday reflection". Clicking
    // invokes confirmation, calls the API, removes it and selects the next item.
    await user.click(screen.getByRole('button', { name: 'Delete conversation' }))
    // queryByRole returns null rather than throwing, making it suitable for an
    // assertion that the deleted conversation is no longer present.
    expect(screen.queryByRole('heading', { name: 'Sunday reflection' })).not.toBeInTheDocument()
  })
})
