# Inbox, Briefly — Email Agent (Web Version)

A web frontend for the Email Summarizer Agent. You type a goal in plain
English ("catch me up on anything urgent"), and the agent decides what to
search for in your Gmail inbox and returns a digest.

```
React frontend (port 5173)  →  FastAPI backend (port 8000)  →  Gmail API + Gemini API
```

The backend reuses `agent.py`, `gmail_auth.py`, and `gmail_client.py` from the
original CLI project unchanged — it's the exact same agent, just exposed over
HTTP instead of run from a terminal.

## Project structure

```
email-agent-web/
├── backend/
│   ├── app.py            <- FastAPI server (new)
│   ├── agent.py           <- the agent loop (from the CLI project)
│   ├── gmail_auth.py       <- OAuth handling (from the CLI project)
│   ├── gmail_client.py     <- Gmail fetching (from the CLI project)
│   ├── requirements.txt
│   ├── .env.example
│   ├── credentials.json    <- you add this (OAuth client, see below)
│   └── .env                <- you add this (Gemini API key)
└── frontend/
    ├── src/
    │   ├── App.jsx          <- main UI
    │   ├── App.css
    │   ├── api.js            <- talks to the backend
    │   ├── main.jsx
    │   └── index.css
    ├── index.html
    ├── package.json
    └── vite.config.js
```

## Setup

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
cp .env.example .env          # then edit .env with your Gemini API key
```

Add your `credentials.json` (same Gmail OAuth file from the CLI project setup)
into the `backend/` folder.

Start the server:

```bash
uvicorn app:app --reload --port 8000
```

Visit `http://localhost:8000/api/health` in your browser — you should see
`{"ok":true}`.

### 2. Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`. The app will tell you if the backend isn't
reachable or if Gmail isn't connected yet — click **Connect Gmail** to run the
OAuth flow (same browser popup as the CLI version).

### 3. Use it

Type a goal, or click one of the example prompts, and hit **Ask**. The agent
decides what Gmail search(es) to run and returns a digest. The small pill
above the response shows exactly which search query the agent chose — useful
for understanding what it's doing, and handy if you want to debug an odd answer.

## Notes

- **This is a single-user local setup.** The backend uses one shared
  `token.json` / `credentials.json`, the same way the CLI version did — it's
  not yet built for multiple different people to log into their own accounts
  from the same running server.
- **CORS** is currently locked to `http://localhost:5173` in `app.py`. If you
  deploy the frontend somewhere else, update `allow_origins` there.

## Turning this into a real multi-user deployed app

The current backend is intentionally the simplest version that works locally.
To let other people actually use a hosted version of this (not just you), a
few real changes are needed:

1. **Per-user OAuth** — instead of one shared `token.json`, each visitor needs
   their own login flow and their own stored token (typically in a database,
   keyed by user session — not a flat file).
2. **Hosting** — the FastAPI backend needs a real host (Render, Fly.io,
   Railway, etc.) instead of your own machine; the React build can be
   deployed as static files (Vercel, Netlify, Cloudflare Pages).
3. **Secrets management** — `GEMINI_API_KEY` moves from a local `.env` file
   to your hosting provider's secret/environment variable settings.
4. **Production OAuth consent screen** — Google's "Testing" mode (what you're
   using now) only allows a small number of manually-added test users. A
   public app needs to go through Google's verification process for the
   `gmail.readonly` scope.
5. **Rate limiting / cost control** — since the Gemini key would now be
   shared across all users of your hosted app, you'd want limits so one
   person can't run up unexpected API costs.

Each of these is a meaningful chunk of work on its own — worth tackling one
at a time rather than all together.