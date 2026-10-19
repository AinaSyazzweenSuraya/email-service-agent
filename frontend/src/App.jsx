import { useState, useEffect, useRef } from 'react'
import { getStatus, authorize, disconnect, runAgent } from './api.js'
import './App.css'

const EXAMPLE_GOALS = [
  'Catch me up on anything urgent',
  "Summarize today's inbox",
  'Did I get any emails I need to reply to?',
  'Any security alerts I should know about?',
]

function Icon({ name = 'mail', ...props }) {
  const paths = {
    mail: <><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m4 7 8 6 8-6" /></>,
    sparkle: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" /><path d="m20 2 .5 1.5L22 4l-1.5.5L20 6l-.5-1.5L18 4l1.5-.5L20 2Z" /></>,
    shield: <><path d="m12 3 8 3v5c0 5-8 10-8 10S4 16 4 11V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
    arrow: <><path d="M4 12h16m-6-6 6 6-6 6" /></>,
    check: <path d="m5 12 4 4L19 6" />,
  }
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.mail}</svg>
}

function useAutoResize(value) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])
  return ref
}

export default function App() {
  const [status, setStatus] = useState(null)
  const [goal, setGoal] = useState('')
  const [phase, setPhase] = useState('idle') // idle | thinking | done | error
  const [toolCalls, setToolCalls] = useState([])
  const [result, setResult] = useState('')
  const [error, setError] = useState('')
  const [authorizing, setAuthorizing] = useState(false)
  const [connectConsent, setConnectConsent] = useState(false)
  const [readConsent, setReadConsent] = useState(false)

  const textareaRef = useAutoResize(goal)

  useEffect(() => {
    refreshStatus()
    const connection = new URLSearchParams(window.location.search).get('connection')
    if (connection === 'cancelled') setError('Gmail connection cancelled. No new permission was granted.')
    if (connection) window.history.replaceState({}, '', window.location.pathname)
  }, [])

  async function refreshStatus() {
    try {
      const s = await getStatus()
      setStatus(s)
    } catch (e) {
      setStatus({ oauth_configured: false, authorized: false, offline: true })
      setError(e.message)
    }
  }

  async function handleAuthorize() {
    setAuthorizing(true)
    setError('')
    try {
      if (!connectConsent) return
      const { authorization_url } = await authorize()
      window.location.assign(authorization_url)
    } catch (e) {
      setError(e.message)
    } finally {
      setAuthorizing(false)
    }
  }

  async function handleDisconnect() {
    setAuthorizing(true)
    setError('')
    try {
      const response = await disconnect()
      setResult('')
      setToolCalls([])
      setGoal('')
      setPhase('idle')
      setReadConsent(false)
      setConnectConsent(false)
      await refreshStatus()
      if (!response.revoked) setError('Disconnected from this app. To ensure Google access is revoked, remove this app in your Google Account connections.')
    } catch (e) { setError(e.message) }
    finally { setAuthorizing(false) }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!goal.trim() || phase === 'thinking' || !readConsent || !status?.authorized || authorizing) return

    setPhase('thinking')
    setError('')
    setResult('')
    setToolCalls([])

    try {
      const res = await runAgent(goal.trim())
      setToolCalls(res.tool_calls || [])
      setResult(res.result)
      setPhase('done')
      setReadConsent(false)
    } catch (e) {
      setError(e.message)
      setPhase('error')
    }
  }

  const needsSetup = status && (!status.oauth_configured || status.offline)
  const needsAuth = status && status.oauth_configured && !status.authorized

  return (
    <div className="page">
      <header className="masthead">
        <a className="brand" href="/" aria-label="Inbox, briefly home">
          <span className="brand__icon"><Icon /></span>
          <span className="masthead__mark">Inbox<span>,</span> briefly<span className="brand__dot">.</span></span>
        </a>
        <div className="masthead__actions">
          <span className={`status-pill ${status?.authorized ? 'status-pill--ok' : ''}`}>
            <span className="status-pill__dot" />
            {!status ? 'Checking connection' : status.authorized ? 'Gmail connected' : 'Gmail not connected'}
          </span>
          {status?.authorized && <button className="disconnect" onClick={handleDisconnect} disabled={authorizing || phase === 'thinking'}>Disconnect</button>}
        </div>
      </header>

      <main className="stage">
        <section className="hero" aria-labelledby="page-title">
          <div className="eyebrow"><span /> A LITTLE SPACE FOR CLARITY</div>
          <h1 id="page-title">Less inbox.<br /><em>More clarity.</em></h1>
          <p className="hero__description">Turn a busy inbox into a clear next step. Ask in your own words,<br className="desktop-break" /> and let your email assistant find what matters.</p>
          <div className="hero__detail"><Icon name="shield" width="16" height="16" /> Your inbox. Your permission. Always.</div>
          <div className="hero__ornament" aria-hidden="true"><span /><span /><Icon name="sparkle" width="42" height="42" /></div>
        </section>

        <div className="workspace">
          <section className="workspace__main" aria-label="Email assistant">
            {error && <div className="notice notice--error" role="alert"><p>{error}</p></div>}
            {!status && <div className="panel loading" role="status"><span className="thinking__dot" /> Getting your space ready…</div>}
            {needsSetup && <div className="panel connection"><span className="panel__eyebrow">CONNECTION STATUS</span><h2>A moment before we begin.</h2><p className="panel__description">{status.offline ? 'The service is temporarily unavailable. Please try again later.' : 'Gmail connection is not available yet. The service owner needs to finish Google sign-in setup.'}</p></div>}

            {needsAuth && !needsSetup && (
              <div className="panel connection">
                <div className="panel__top"><span className="panel__eyebrow">01 / CONNECT YOUR INBOX</span><span className="icon-tile"><Icon /></span></div>
                <h2>Your day, a little lighter.</h2>
                <p className="panel__description">Connect Gmail to find the important updates, the unanswered questions, and the things that need you.</p>
                <div className="permission-info"><Icon name="shield" /><div><strong>Read-only. You stay in control.</strong><p>Choose your account and approve access on Google. You can cancel or disconnect anytime. No passwords or API keys to enter here.</p></div></div>
                <label className="consent"><input type="checkbox" checked={connectConsent} onChange={e => setConnectConsent(e.target.checked)} /><span>I agree to connect my Gmail account with read-only access.</span></label>
                <button className="btn-primary connect-button" onClick={handleAuthorize} disabled={authorizing || !connectConsent}><Icon />{authorizing ? 'Opening Google sign-in…' : 'Connect with Gmail'}<Icon name="arrow" width="19" height="19" /></button>
                <p className="connection__note">Nothing is read until you connect and approve a request.</p>
              </div>
            )}

            {status?.authorized && !status.ai_configured && <div className="notice"><p>The AI service is not available yet. The service owner needs to finish setup.</p></div>}
            {status?.authorized && !needsSetup && (
              <div className="panel compose">
                <div className="panel__top"><span className="panel__eyebrow">02 / ASK YOUR ASSISTANT</span><span className="icon-tile"><Icon name="sparkle" /></span></div>
                <form className="ask" onSubmit={handleSubmit}>
                  <label className="ask__label" htmlFor="goal">What’s on your mind?</label>
                  <p className="panel__description">A quick catch-up, an urgent update, or a reply you missed.</p>
                  <textarea id="goal" ref={textareaRef} className="ask__input" placeholder="Catch me up on anything urgent…" value={goal} onChange={e => setGoal(e.target.value)} maxLength={4000} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); handleSubmit(e) } }} rows={2} />
                  <span className="examples__label">A LITTLE INSPIRATION</span>
                  <div className="examples">{EXAMPLE_GOALS.map(ex => <button type="button" key={ex} className="example-chip" onClick={() => setGoal(ex)}>{ex}<Icon name="arrow" width="14" height="14" /></button>)}</div>
                  <label className="consent"><input type="checkbox" checked={readConsent} onChange={e => setReadConsent(e.target.checked)} /><span>For this request, allow the agent to read matching emails and send their sender, subject, date and body excerpts to Google Gemini to prepare my answer. Google processes and may retain this information under its API terms.</span></label>
                  <div className="ask__row"><span className="keyboard-hint">Enter to ask · Shift + Enter for a new line</span><button className="btn-primary" type="submit" disabled={phase === 'thinking' || !readConsent || !goal.trim() || !status.ai_configured || authorizing}>{phase === 'thinking' ? 'Reading your inbox…' : 'Find my clarity'}<Icon name="sparkle" width="18" height="18" /></button></div>
                </form>
              </div>
            )}
            {phase === 'thinking' && <div className="thinking" role="status"><span className="thinking__dot" /><div>Finding what matters<span>Reading matching emails and preparing your brief.</span></div></div>}
            {phase === 'done' && <article className="panel digest" aria-live="polite"><div className="panel__top"><span className="panel__eyebrow">YOUR INBOX, BRIEFLY</span><Icon name="sparkle" /></div><h2>A little more clarity.</h2>{toolCalls.length > 0 && <details className="digest__sources"><summary>View email searches</summary><div className="digest__trace">{toolCalls.map((call, i) => <span className="trace-chip" key={i}>{call}</span>)}</div></details>}<div className="digest__body">{result.split('\n').map((line, i) => line.trim() ? <p key={i}>{line}</p> : null)}</div></article>}
          </section>

          <aside className="sidebar" aria-label="How your assistant works">
            <div className="preview-card">
              <div className="preview-card__header"><span><Icon name="sparkle" width="16" height="16" /> A calmer kind of inbox</span><span className="sample-label">EXAMPLE</span></div>
              <div className="preview-card__body"><span className="preview-card__eyebrow">THE BIG PICTURE, WITHOUT THE NOISE</span><h3>From scrolling<br />to knowing.</h3><div className="preview-message"><span className="preview-message__icon"><Icon name="check" width="17" height="17" /></span><div><strong>The update you needed</strong><p>Your project is on track. The next milestone is ready for your review.</p></div></div><div className="preview-line" /><div className="preview-line preview-line--short" /><p className="sample-note">An illustration of a brief, not your inbox.</p></div>
            </div>
            <div className="benefits"><div className="benefit"><Icon name="mail" /><div><h3>Connect on your terms</h3><p>Choose your own Gmail account. Grant read-only access through Google.</p></div></div><div className="benefit"><Icon name="sparkle" /><div><h3>Ask naturally</h3><p>Find urgent updates, follow-ups, or a summary of your day.</p></div></div><div className="benefit"><Icon name="shield" /><div><h3>Approve every request</h3><p>You decide when email excerpts can be shared with Gemini.</p></div></div></div>
          </aside>
        </div>
      </main>
      <footer className="footer"><span>Made for a little less overwhelm.</span><span><Icon name="shield" width="14" height="14" /> Read-only Gmail access · Disconnect anytime</span></footer>
    </div>
  )
}
