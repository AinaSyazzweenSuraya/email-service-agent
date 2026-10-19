// Always use the frontend's /api proxy: cookies stay first-party on Vercel.
const API_BASE = ''

async function request(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...(body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please try again.')
  return data
}

export const getStatus = () => request('/api/status')
export const authorize = () => request('/api/authorize', { consent: true })
export const disconnect = () => request('/api/disconnect', {})
export const runAgent = goal => request('/api/run', { goal, consent: true })
