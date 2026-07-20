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
        <strong>Your conversation is private</strong>
        <p>Messages are encrypted before they are stored. The private model is not exposed directly to the internet.</p>
      </div>
    </details>
  )
}
