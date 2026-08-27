import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import './PrivacyGate.css'

const PRIVACY_PIN_KEY = 'private-chat.privacy-pin.v1'
const IDLE_TIMEOUT_MS = 5 * 60 * 1000
const AWAY_TIMEOUT_MS = 15 * 1000
const PBKDF2_ITERATIONS = 200_000

interface PrivacyPinRecord {
  readonly version: 1
  readonly salt: string
  readonly digest: string
}

interface PrivacyGateProps {
  readonly children: (lock: () => void) => ReactNode
}

function toBase64(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
}

function fromBase64(value: string): Uint8Array {
  return Uint8Array.from(atob(value), (character) => character.charCodeAt(0))
}

async function deriveDigest(pin: string, salt: Uint8Array): Promise<string> {
  const material = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveBits'],
  )
  const derived = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', hash: 'SHA-256', salt, iterations: PBKDF2_ITERATIONS }, material, 256,
  )
  return toBase64(new Uint8Array(derived))
}

function readStoredPin(): PrivacyPinRecord | null {
  try {
    const raw = localStorage.getItem(PRIVACY_PIN_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (
      typeof parsed !== 'object' || parsed === null
      || !('version' in parsed) || !('salt' in parsed) || !('digest' in parsed)
      || parsed.version !== 1 || typeof parsed.salt !== 'string' || typeof parsed.digest !== 'string'
    ) return null
    return parsed as PrivacyPinRecord
  } catch {
    return null
  }
}

async function pinsMatch(pin: string, record: PrivacyPinRecord): Promise<boolean> {
  return deriveDigest(pin, fromBase64(record.salt)).then((digest) => digest === record.digest)
}

export function PrivacyGate({ children }: PrivacyGateProps) {
  const [storedPin, setStoredPin] = useState<PrivacyPinRecord | null>(readStoredPin)
  const [unlocked, setUnlocked] = useState(false)
  const [pin, setPin] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const awayTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const lock = useCallback(() => {
    setUnlocked(false)
    setPin('')
    setConfirmation('')
    setError(null)
  }, [])

  useEffect(() => {
    if (!unlocked) return
    const clearTimers = () => {
      if (idleTimer.current !== null) clearTimeout(idleTimer.current)
      if (awayTimer.current !== null) clearTimeout(awayTimer.current)
    }
    const resetIdleTimer = () => {
      if (idleTimer.current !== null) clearTimeout(idleTimer.current)
      idleTimer.current = setTimeout(lock, IDLE_TIMEOUT_MS)
    }
    const scheduleAwayLock = () => {
      if (awayTimer.current !== null) clearTimeout(awayTimer.current)
      awayTimer.current = setTimeout(lock, AWAY_TIMEOUT_MS)
    }
    const resume = () => {
      if (awayTimer.current !== null) clearTimeout(awayTimer.current)
      resetIdleTimer()
    }
    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') scheduleAwayLock()
      else resume()
    }
    const activityEvents: (keyof DocumentEventMap)[] = ['keydown', 'pointerdown', 'pointermove', 'scroll', 'touchstart']
    activityEvents.forEach((event) => document.addEventListener(event, resetIdleTimer, { passive: true }))
    window.addEventListener('blur', scheduleAwayLock)
    window.addEventListener('focus', resume)
    document.addEventListener('visibilitychange', onVisibilityChange)
    resetIdleTimer()
    return () => {
      clearTimers()
      activityEvents.forEach((event) => document.removeEventListener(event, resetIdleTimer))
      window.removeEventListener('blur', scheduleAwayLock)
      window.removeEventListener('focus', resume)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [lock, unlocked])

  const setUpPin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (pin.length < 4) return setError('Choose at least four characters.')
    if (pin !== confirmation) return setError('The two entries do not match.')
    setIsSubmitting(true)
    try {
      const salt = crypto.getRandomValues(new Uint8Array(16))
      const record: PrivacyPinRecord = { version: 1, salt: toBase64(salt), digest: await deriveDigest(pin, salt) }
      localStorage.setItem(PRIVACY_PIN_KEY, JSON.stringify(record))
      setStoredPin(record)
      setUnlocked(true)
      setPin('')
      setConfirmation('')
      setError(null)
    } catch {
      setError('The privacy PIN could not be saved in this browser.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const unlock = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!storedPin) return
    setIsSubmitting(true)
    try {
      if (await pinsMatch(pin, storedPin)) {
        setUnlocked(true)
        setPin('')
        setError(null)
      } else setError('That privacy PIN is not correct.')
    } catch {
      setError('The privacy PIN could not be checked in this browser.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (unlocked) return <>{children(lock)}</>
  const isFirstUse = storedPin === null
  return (
    <main className="privacy-gate">
      <section className="privacy-card" aria-labelledby="privacy-title">
        <p className="privacy-eyebrow">Private Chat</p>
        <h1 id="privacy-title">{isFirstUse ? 'Create a privacy PIN' : 'Private Chat is locked'}</h1>
        <p className="privacy-copy">{isFirstUse ? 'Choose a small PIN or password to keep conversations out of casual view.' : 'Enter your privacy PIN to view conversations.'}</p>
        <form onSubmit={isFirstUse ? setUpPin : unlock}>
          <label htmlFor="privacy-pin">{isFirstUse ? 'Privacy PIN or password' : 'Privacy PIN'}</label>
          <input id="privacy-pin" type="password" autoComplete={isFirstUse ? 'new-password' : 'current-password'} autoFocus value={pin} disabled={isSubmitting} onChange={(event) => setPin(event.target.value)} />
          {isFirstUse ? <><label htmlFor="privacy-pin-confirmation">Confirm privacy PIN or password</label><input id="privacy-pin-confirmation" type="password" autoComplete="new-password" value={confirmation} disabled={isSubmitting} onChange={(event) => setConfirmation(event.target.value)} /></> : null}
          {error ? <p className="privacy-error" role="alert">{error}</p> : null}
          <button type="submit" disabled={isSubmitting || !pin || (isFirstUse && !confirmation)}>{isFirstUse ? 'Create privacy PIN' : 'Unlock'}</button>
        </form>
        <p className="privacy-note">This is a privacy shield for casual viewing, not a replacement for Windows sign-in security.</p>
      </section>
    </main>
  )
}
