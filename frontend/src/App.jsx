import { useState, useEffect, useRef } from 'react'
import { getStatus, authorize, runAgent } from './api.js'
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

  const textareaRef = useAutoResize(goal)

  useEffect(() => {
    refreshStatus()
  }, [])

  async function refreshStatus() {
    try {
      const s = await getStatus()
      setStatus(s)
    } catch (e) {
      setStatus({ credentials_file_present: false, authorized: false, offline: true })
    }
  }

  async function handleAuthorize() {
    setAuthorizing(true)
    setError('')
    try {
      await authorize()
      await refreshStatus()
    } catch (e) {
      setError(e.message)
    } finally {
      setAuthorizing(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!goal.trim() || phase === 'thinking') return

    setPhase('thinking')
    setError('')
    setResult('')
    setToolCalls([])

    try {
      const res = await runAgent(goal.trim())
      setToolCalls(res.tool_calls || [])
      setResult(res.result)
      setPhase('done')
    } catch (e) {
      setError(e.message)
      setPhase('error')
    }
  }

  const needsSetup = status && (!status.credentials_file_present || status.offline)
  const needsAuth = status && status.credentials_file_present && !status.authorized

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
              The backend server isn't reachable, or <code>credentials.json</code> is
              missing. Start the FastAPI server and make sure your Gmail OAuth file is
              in place, then reload this page.
            </p>
          </div>
        )}

        {needsAuth && !needsSetup && (
          <div className="notice">
            <p>Connect your Gmail account to let the agent read your inbox.</p>
            <button className="btn-secondary" onClick={handleAuthorize} disabled={authorizing}>
              {authorizing ? 'Opening Google sign-in…' : 'Connect Gmail'}
            </button>
          </div>
        )}

        {!needsSetup && !needsAuth && (
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
                <button className="btn-primary" type="submit" disabled={phase === 'thinking'}>
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