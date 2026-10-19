import { useState, useEffect, useRef } from 'react'
import { getStatus, authorize, disconnect, runAgent } from './api.js'
import './App.css'

const EXAMPLE_GOALS = [
  "Summarize today's emails",
  'Show urgent emails',
  'Which emails need a reply?',
  'Find security alerts',
]

function Icon({ name = 'mail', ...props }) {
  const paths = {
    mail: <><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m4 7 8 6 8-6" /></>,
    shield: <><path d="m12 3 8 3v5c0 5-8 10-8 10S4 16 4 11V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
    arrow: <><path d="M4 12h16m-6-6 6 6-6 6" /></>,
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
        <div className="masthead__inner">
          <a className="brand" href="/" aria-label="Email Assistant home"><span className="brand__icon"><Icon /></span>Email Assistant</a>
          <div className="masthead__actions">
            <span className={`status-pill ${status?.authorized ? 'status-pill--ok' : ''}`}><span className="status-pill__dot" />{!status ? 'Checking…' : status.authorized ? 'Gmail connected' : 'Not connected'}</span>
            {status?.authorized && <button className="disconnect" onClick={handleDisconnect} disabled={authorizing || phase === 'thinking'}>Disconnect</button>}
          </div>
        </div>
      </header>
      <main className="stage">
        <section className="intro" aria-labelledby="page-title">
          <h1 id="page-title">Check your emails</h1>
          <p>Get a summary or ask a question about your Gmail inbox.</p>
        </section>
        <section className="workspace" aria-label="Email assistant">
          {error && <div className="notice notice--error" role="alert"><p>{error}</p></div>}
          {!status && <div className="panel loading" role="status"><span className="thinking__dot" /> Checking your connection…</div>}
          {needsSetup && <div className="panel"><h2>Unable to connect</h2><p className="description">{status.offline ? 'The service is unavailable. Please try again later.' : 'Gmail sign-in is not set up yet. Please contact the app owner.'}</p></div>}
          {needsAuth && !needsSetup && (
            <div className="panel connection">
              <div className="connection__heading"><span className="mail-icon"><Icon width="27" height="27" /></span><div><h2>Connect your Gmail</h2><p className="description">Choose your Google account to get started.</p></div></div>
              <div className="permission-info"><Icon name="shield" width="19" height="19" /><div><strong>Read-only access</strong><p>The app can read emails. It cannot send or delete them. You can disconnect at any time.</p></div></div>
              <label className="consent"><input type="checkbox" checked={connectConsent} onChange={e => setConnectConsent(e.target.checked)} /><span>Allow this app to read my Gmail emails.</span></label>
              <button className="btn-primary connect-button" onClick={handleAuthorize} disabled={authorizing || !connectConsent}>{authorizing ? 'Opening Google…' : 'Connect Gmail'}<Icon name="arrow" width="17" height="17" /></button>
              <p className="connection__note">Google will ask you to approve access before connecting. Read our <a href="/privacy.html">Privacy Policy</a> and <a href="/terms.html">Terms of Service</a>.</p>
            </div>
          )}
          {status?.authorized && !status.ai_configured && <div className="notice"><p>Email summaries are not set up yet. Please contact the app owner.</p></div>}
          {status?.authorized && !needsSetup && (
            <div className="panel compose">
              <form className="ask" onSubmit={handleSubmit}>
                <label className="ask__label" htmlFor="goal">What would you like to know?</label>
                <textarea id="goal" ref={textareaRef} className="ask__input" placeholder="For example: Summarize today's emails" value={goal} onChange={e => setGoal(e.target.value)} maxLength={4000} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); handleSubmit(e) } }} rows={3} />
                <span className="examples__label">Try a question</span>
                <div className="examples">{EXAMPLE_GOALS.map(ex => <button type="button" key={ex} className="example-chip" onClick={() => setGoal(ex)}>{ex}</button>)}</div>
                <div className="request-permission"><label className="consent"><input type="checkbox" checked={readConsent} onChange={e => setReadConsent(e.target.checked)} /><span>For this question, allow the app to read matching emails and share their sender, subject, date and text excerpts with Google Gemini.</span></label><p>Gemini uses these details to answer you. Google may keep this information under its API terms.</p></div>
                <div className="ask__row"><span className="keyboard-hint">Enter to ask · Shift + Enter for a new line</span><button className="btn-primary" type="submit" disabled={phase === 'thinking' || !readConsent || !goal.trim() || !status.ai_configured || authorizing}>{phase === 'thinking' ? 'Reading emails…' : 'Ask'}<Icon name="arrow" width="17" height="17" /></button></div>
              </form>
            </div>
          )}
          {phase === 'thinking' && <div className="thinking" role="status"><span className="thinking__dot" /> Reading emails and writing your summary…</div>}
          {phase === 'done' && <article className="panel digest" aria-live="polite"><div className="digest__heading"><Icon width="21" height="21" /><h2>Email summary</h2></div><div className="digest__body">{result.split('\n').map((line, i) => line.trim() ? <p key={i}>{line}</p> : null)}</div>{toolCalls.length > 0 && <details className="digest__sources"><summary>View email searches</summary><div className="digest__trace">{toolCalls.map((call, i) => <span className="trace-chip" key={i}>{call}</span>)}</div></details>}</article>}
        </section>
        {!status?.authorized && <section className="how-it-works" aria-labelledby="how-title"><h2 id="how-title">How it works</h2><ol><li><span>1</span><div><h3>Connect Gmail</h3><p>Sign in with Google and approve access.</p></div></li><li><span>2</span><div><h3>Ask a question</h3><p>Choose what you want to read or find.</p></div></li><li><span>3</span><div><h3>Read your summary</h3><p>Get an answer based on your emails.</p></div></li></ol></section>}
      </main>
      <footer className="footer"><span>Email Assistant</span><nav className="footer__links" aria-label="Legal"><a href="/privacy.html">Privacy Policy</a><a href="/terms.html">Terms of Service</a></nav></footer>
    </div>
  )
}
