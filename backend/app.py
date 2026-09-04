"""
FastAPI backend for the Email Agent frontend.

Wraps the existing agent.py (unchanged) behind two HTTP endpoints:
  GET  /api/status        -> whether Gmail is currently authorized
  POST /api/run           -> runs the agent with a user-supplied goal

Run locally with:
    uvicorn app:app --reload --port 8000

This is intentionally a single-user local server for now (it reuses the same
token.json / credentials.json pattern as the CLI version). Turning this into a
true multi-user hosted service is a separate step -- see the README section
"Multi-user deployment" for what that involves.
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import run_agent
from gmail_auth import get_gmail_credentials, TOKEN_PATH, CREDENTIALS_PATH

app = FastAPI(title="Email Agent API")

# Allow the local React dev server (Vite default port) to call this API.
# When you deploy, replace "*" with your actual frontend's domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    goal: str


class RunResponse(BaseModel):
    result: str
    tool_calls: list[str]


@app.get("/api/status")
def status():
    """Reports whether Gmail auth is ready, without triggering a new login."""
    has_credentials_file = os.path.exists(CREDENTIALS_PATH)
    has_token_file = os.path.exists(TOKEN_PATH)
    return {
        "credentials_file_present": has_credentials_file,
        "authorized": has_token_file,
    }


@app.post("/api/authorize")
def authorize():
    """
    Triggers the OAuth login flow if needed (opens a browser on the server
    machine -- fine for local use, not for a real hosted multi-user deploy).
    """
    if not os.path.exists(CREDENTIALS_PATH):
        raise HTTPException(
            status_code=400,
            detail="credentials.json not found on the server. Add it next to app.py.",
        )
    try:
        get_gmail_credentials()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"authorized": True}


@app.post("/api/run", response_model=RunResponse)
def run(req: RunRequest):
    """Runs the agent with the given goal and returns its final answer."""
    if not req.goal or not req.goal.strip():
        raise HTTPException(status_code=400, detail="Goal cannot be empty.")

    if not os.path.exists(TOKEN_PATH):
        raise HTTPException(
            status_code=401,
            detail="Not authorized yet. Call /api/authorize first.",
        )

    tool_calls_log: list[str] = []

    def on_tool_call(name: str, args: dict):
        tool_calls_log.append(f"{name}({args})")

    try:
        result = run_agent(req.goal, verbose=False, on_tool_call=on_tool_call)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RunResponse(result=result, tool_calls=tool_calls_log)


@app.get("/api/health")
def health():
    return {"ok": True}