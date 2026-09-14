import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import { DemoChatApi } from '../data/demoChatApi'

afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks() })

it('sends the selected mode and remembers it separately for each conversation', async () => {
  const api = new DemoChatApi()
  const send = vi.spyOn(api, 'sendMessage')
  const conversations = await api.listConversations()
  const props = {
    api, initialConversations: conversations, initialSummaries: await api.listConversationSummaries(),
    models: await api.listModels(), onLock: vi.fn(),
    modelConfiguration: { ...await api.getModelConfiguration(), promptModes: [
      { id: 'standard', label: 'Standard' }, { id: 'custom', label: 'Custom' },
    ] },
  }
  const user = userEvent.setup()
  const first = render(<App {...props} />)
  await user.selectOptions(screen.getByLabelText('Prompt mode'), 'custom')
  await user.type(screen.getByLabelText('Write a message'), 'hello')
  await user.click(screen.getByRole('button', { name: 'Send message' }))
  expect(send).toHaveBeenCalledWith({ conversationId: conversations[0]?.id, body: 'hello', promptModeId: 'custom' })
  await user.click(screen.getByRole('button', { name: 'Project decisions' }))
  expect(screen.getByLabelText('Prompt mode')).toHaveValue('standard')
  first.unmount()
  render(<App {...props} />)
  expect(screen.getByLabelText('Prompt mode')).toHaveValue('custom')
})

it('requires a new choice when a saved private mode has been removed', async () => {
  const api = new DemoChatApi()
  const conversations = await api.listConversations()
  localStorage.setItem(`private-chat:prompt-mode:v1:${conversations[0]?.id}`, 'removed')
  render(<App api={api} initialConversations={conversations} initialSummaries={await api.listConversationSummaries()}
    models={await api.listModels()} modelConfiguration={await api.getModelConfiguration()} onLock={vi.fn()} />)
  expect(screen.getByLabelText('Write a message')).toBeDisabled()
  await userEvent.setup().selectOptions(screen.getByLabelText('Prompt mode'), 'standard')
  expect(screen.getByLabelText('Write a message')).not.toBeDisabled()
})
