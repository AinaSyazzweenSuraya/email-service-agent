const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8082'

async function handle(response) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export async function getStatus() {
  const res = await fetch(`${API_BASE}/api/status`)
  return handle(res)
}

export async function authorize() {
  const res = await fetch(`${API_BASE}/api/authorize`, { method: 'POST' })
  return handle(res)
}

export async function runAgent(goal) {
  const res = await fetch(`${API_BASE}/api/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ goal }),
  })
  return handle(res)
}