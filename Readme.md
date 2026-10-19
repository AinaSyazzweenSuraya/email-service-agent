# Inbox, Briefly

A React + FastAPI Gmail assistant. Each browser gets an independent session;
there is no shared inbox in the web application.

## Permission flow

1. The visitor agrees to connect Gmail, then chooses their Google account and
   grants **read-only Gmail access** on Google's consent screen. Cancelling
   grants no access. The app never asks for an email password or personal API key.
2. Before **each** request, the visitor explicitly agrees to let the agent read
   matching emails and send sender, subject, date and body excerpts to Google
   Gemini. The agent uses Google's stateful Interactions API, so email content is
   processed and may be retained by Google under its API terms. Explain this in
   your public privacy policy before launch.
3. Disconnect deletes this browser's stored tokens and attempts to revoke the
   Google grant. If Google cannot be reached, the UI explains how to revoke it
   in Google Account connections. A request already in progress can finish.

Opaque HttpOnly, SameSite=Lax cookies identify browser sessions (7 days).
OAuth requests expire after 10 minutes, use PKCE and single-use state bound to
that browser. The backend rejects mutation requests from other origins.
Tokens are encrypted at rest in Postgres (or SQLite for local development), never returned to the frontend, and
never loaded from the CLI's shared `token.json`. Sessions do not sync between
devices. Clearing cookies or session expiry requires reconnecting Gmail.

## Local development

Use Python 3.12 and Node 20+.

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The service owner creates a **Web application** OAuth client in Google Cloud,
enables Gmail API, and adds this exact authorized redirect URI:
`http://localhost:5173/api/oauth/callback`.
Download its client configuration to the ignored `backend/credentials.json`,
or inject actual JSON through `GOOGLE_CREDENTIALS_JSON` using your hosting
provider's secret manager. A proxy placeholder cannot replace this local JSON
configuration. Do not use a Desktop OAuth client or a shared Gmail token.

Start the backend from `backend/`, supplying the owner's `GEMINI_API_KEY`
through secure environment configuration or an ignored `.env` file:

```bash
export FRONTEND_URL=http://localhost:5173
export OAUTH_REDIRECT_URI=http://localhost:5173/api/oauth/callback
export COOKIE_SECURE=false # local HTTP only
export AUTH_DATA_DIR=/workspace/.email-agent-auth
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev -- --host localhost --strictPort
```

Vite proxies `/api` to the backend. Use the same `localhost` hostname throughout
login; switching to `127.0.0.1` loses the browser session. The frontend defaults
to same-origin `/api`, including in production. `VITE_API_BASE` is ignored so
browsers never require third-party cookies for this app.
The health endpoint works before credentials are configured; the UI explains
which service setup is missing.

```bash
# From backend/; Google calls and the AI boundary are mocked in these tests.
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
# From frontend/
npm run build
```

## Vercel deployment: two projects and Neon

Use `frontend/` as the Root Directory of **email-service-agent-web** and
`backend/` as the Root Directory of **email-service-agent-api**. The API uses
Vercel's FastAPI support with `app.py` as its entry point. Deploy the updated
code to both projects; redeploying an older Git commit does not upload local changes.

Set these **backend Production** variables:

| Name | Value |
| --- | --- |
| `GEMINI_API_KEY` | Owner's secret Gemini key |
| `GOOGLE_CREDENTIALS_JSON` | Full secret Google **Web application** client JSON |
| `FRONTEND_URL` | `https://email-service-agent-web.vercel.app` |
| `OAUTH_REDIRECT_URI` | `https://email-service-agent-api.vercel.app/api/oauth/callback` |
| `COOKIE_SECURE` | `true` |
| `DATABASE_URL` | Neon integration's pooled Postgres connection URL |
| `TOKEN_ENCRYPTION_KEY` | A single persistent secret Fernet key, generated below |

The Neon integration already provides `DATABASE_URL`; leave its other generated
variables alone. The app verifies certificates and hostnames on remote database
connections. On Vercel the app refuses to fall back to ephemeral local files.
It creates its `sessions` table automatically; no manual SQL is needed. A failed
database setup returns an actionable 503 response, without exposing credentials.

Generate `TOKEN_ENCRYPTION_KEY` privately on your computer or in Google Cloud Shell:

```bash
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

Copy the generated value into a **Sensitive** backend Production variable. Never
paste it into chat, source code, or build logs. Keep the same key across all
instances and redeployments. Rotating it makes existing users reconnect. Do not
reuse a Gemini key or Google client secret as the encryption key.

The **frontend needs no environment variables**. Remove the old `VITE_API_BASE`
when convenient; the code intentionally ignores it. `frontend/vercel.json`
rewrites `/api/*` to your API project, which makes session cookies first-party
on the frontend host. The API-host Google callback relays to the frontend
`/api/oauth/callback` route, where the browser's session cookie is available.
The original registered API redirect URI is still used in the code exchange.
You can keep the Google callback URL you have already registered. No
`SameSite=None` or third-party-cookie permission is required.

If using different project domains, update the rewrite destination and backend
URLs together. Set the Google Web client's authorized JavaScript origin to the
frontend origin and its redirect URI to the exact `OAUTH_REDIRECT_URI`. Enable
Gmail API and add `gmail.readonly` in Data access. While the consent screen is in
Testing, list each test account under Audience > Test users.

After deployment:

1. API `/api/health` must return `{"ok":true}`.
2. **Frontend** `/api/status` must return `oauth_configured`, `ai_configured` and
   `authorized` flags and set an HttpOnly secure session cookie. The old
   `credentials_file_present` response means old code is still deployed.
3. In the frontend agree to read-only access and click Connect Gmail. The browser
   should navigate to Google. Cancelled consent must not connect any mailbox.
4. After approval the frontend status should be connected. A separate private
   browser window must remain disconnected.
5. Approve sending excerpts to Gemini and ask for a summary; then disconnect.

Tests use mocked Google/AI calls; live OAuth and summaries require the owner's
real hosting configuration and a user's explicit consent. This workspace does
not have the private Vercel/Neon variables, so a successful local test does not
establish successful live deployment.

For a real Postgres test run, point `TEST_DATABASE_URL` only at a **disposable test
database**, never your Neon production database. The tests exercise all consent,
callback, token isolation and replay checks against both SQLite and Postgres:

```bash
# From backend/; use your disposable test database URL in the local process.
TEST_DATABASE_URL=postgresql://postgres@localhost:55432/postgres .venv/bin/python -m unittest discover -s tests -v
```

## Before opening access to everybody

Google restricted Gmail-scope verification (and potentially a security
assessment), a public privacy policy and appropriate consent-screen production
publishing are external prerequisites. Configure hosting rate limits, capacity,
billing limits, monitoring, retention and abuse controls before public launch.
The free database is suitable for initial testing, not a guarantee of capacity.
A Google grant can cover multiple sessions for the same account; revoking it
can require that account to reconnect in other browsers too.

Allow outbound HTTPS to `generativelanguage.googleapis.com`,
`accounts.google.com`, `oauth2.googleapis.com`, `gmail.googleapis.com` and
`www.googleapis.com`, plus package registries during installation.

Legacy CLI scripts still use their explicit local authentication flow. Their
shared credential files are never used by web requests.
