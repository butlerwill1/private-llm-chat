import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { PrivacyGate } from './PrivacyGate'

afterEach(() => {
  cleanup()
  localStorage.clear()
})

describe('PrivacyGate', () => {
  it('sets a privacy PIN and locks again when requested', async () => {
    const user = userEvent.setup()
    render(<PrivacyGate>{(lock) => <button type="button" onClick={lock}>Lock now</button>}</PrivacyGate>)

    await user.type(screen.getByLabelText('Privacy PIN or password'), '1234')
    await user.type(screen.getByLabelText('Confirm privacy PIN or password'), '1234')
    await user.click(screen.getByRole('button', { name: 'Create privacy PIN' }))

    expect(await screen.findByRole('button', { name: 'Lock now' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Lock now' }))
    expect(screen.getByRole('heading', { name: 'Private Chat is locked' })).toBeVisible()
  })

  it('does not unlock when the privacy PIN is wrong', async () => {
    const user = userEvent.setup()
    localStorage.setItem('private-chat.privacy-pin.v1', JSON.stringify({ version: 1, salt: 'AAAAAAAAAAAAAAAAAAAAAA==', digest: 'not-a-real-digest' }))
    render(<PrivacyGate>{() => <p>Private conversation</p>}</PrivacyGate>)

    await user.type(screen.getByLabelText('Privacy PIN'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Unlock' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('not correct')
    expect(screen.queryByText('Private conversation')).not.toBeInTheDocument()
  })
})
