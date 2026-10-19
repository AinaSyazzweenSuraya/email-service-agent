import { useState, useEffect, useRef } from 'react'
import { getStatus, authorize, disconnect, runAgent } from './api.js'
import './App.css'

const EXAMPLE_GOALS = [
  'Catch me up on anything urgent',
  "Summarize today's inbox",
  'Did I get any emails I need to reply to?',
  'Any security alerts I should know about?',
]

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
        <span className="masthead__mark">Inbox, briefly</span>
        {status && !needsSetup && (
          <span className={`status-pill ${status.authorized ? 'status-pill--ok' : ''}`}>
            {status.authorized ? 'Connected to Gmail' : 'Not connected'}
          </span>
        )}
      </header>

      <main className="stage">
        {needsSetup && (
          <div className="notice">
            <p>
              {status.offline ? 'The service is temporarily unavailable. Please try again later.' : 'Gmail connection is not available yet. The service owner needs to finish Google sign-in setup.'}
            </p>
          </div>
        )}

        {needsAuth && !needsSetup && (
          <div className="notice">
            <p>Connect your own Gmail account. Google will ask you to choose an account and approve read-only access. You can cancel or disconnect at any time. Never enter your email password or API keys here.</p>
            <label><input type="checkbox" checked={connectConsent} onChange={e => setConnectConsent(e.target.checked)} /> I agree to connect Gmail with read-only access.</label>
            <button className="btn-secondary" onClick={handleAuthorize} disabled={authorizing || !connectConsent}>
              {authorizing ? 'Opening Google sign-in…' : 'Connect Gmail'}
            </button>
          </div>
        )}

        {error && phase !== 'error' && <div className="notice notice--error" role="alert"><p>{error}</p></div>}
        {status?.authorized && <button className="btn-secondary" onClick={handleDisconnect} disabled={authorizing || phase === 'thinking'}>Disconnect Gmail</button>}
        {status?.authorized && !status.ai_configured && <div className="notice"><p>The AI service is not available yet. The service owner needs to finish setup.</p></div>}
        {status?.authorized && !needsSetup && (
          <>
            <form className="ask" onSubmit={handleSubmit}>
              <label className="ask__label" htmlFor="goal">
                What do you want to know?
              </label>
              <textarea
                id="goal"
                ref={textareaRef}
                className="ask__input"
                placeholder="Catch me up on anything urgent"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSubmit(e)
                  }
                }}
                rows={1}
              />
              <label><input type="checkbox" checked={readConsent} onChange={e => setReadConsent(e.target.checked)} /> For this request, allow the agent to read matching emails and send their sender, subject, date and body excerpts to Google Gemini to prepare my answer. Google processes and may retain this information under its API terms.</label>
              <div className="ask__row">
                <div className="examples">
                  {EXAMPLE_GOALS.map((ex) => (
                    <button
                      type="button"
                      key={ex}
                      className="example-chip"
                      onClick={() => setGoal(ex)}
                    >
                      {ex}
                    </button>
                  ))}
                </div>
                <button className="btn-primary" type="submit" disabled={phase === 'thinking' || !readConsent || !status.ai_configured || authorizing}>
                  {phase === 'thinking' ? 'Reading…' : 'Ask'}
                </button>
              </div>
            </form>

            {phase === 'thinking' && (
              <div className="thinking">
                <span className="thinking__dot" />
                Checking your inbox
              </div>
            )}

            {phase === 'error' && (
              <div className="notice notice--error">
                <p>{error}</p>
              </div>
            )}

            {phase === 'done' && (
              <article className="digest">
                {toolCalls.length > 0 && (
                  <div className="digest__trace">
                    {toolCalls.map((call, i) => (
                      <span className="trace-chip" key={i}>{call}</span>
                    ))}
                  </div>
                )}
                <div className="digest__body">
                  {result.split('\n').map((line, i) =>
                    line.trim() ? <p key={i}>{line}</p> : null
                  )}
                </div>
              </article>
            )}
          </>
        )}
      </main>
    </div>
  )
}