import { ChevronIcon, LockIcon } from './Icons'

export function PrivacyDetails() {
  return (
    <details className="privacy-details">
      <summary>
        <LockIcon />
        <span>Encrypted</span>
        <ChevronIcon className="privacy-chevron" />
      </summary>
      <div className="privacy-panel">
        <strong>Encrypted local storage</strong>
        <p>Messages are encrypted before local storage. The selected OpenRouter provider receives the prompt to generate a response; this is privacy-restricted hosted inference, not end-to-end private inference.</p>
      </div>
    </details>
  )
}
