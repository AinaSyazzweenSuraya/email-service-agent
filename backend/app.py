"""Consent-based Gmail access with isolated, server-side browser sessions."""
import os
import time
from urllib.parse import urlsplit, urlencode

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from pydantic import BaseModel, Field

from agent import run_agent
from web_auth import COOKIE, SCOPES, AuthConfigurationError, consume_state, oauth_flow, save_token, session, storage, token_for

app = FastAPI(title='Email Agent API')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
FRONTEND_ORIGIN = '{0.scheme}://{0.netloc}'.format(urlsplit(FRONTEND_URL))
app.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_ORIGIN], allow_credentials=True,
                   allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@app.middleware('http')
async def protect_browser_requests(request: Request, call_next):
    if request.method == 'POST' and request.headers.get('origin') != FRONTEND_ORIGIN:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Request must originate from the app.'}, status_code=403)
    try:
        response = await call_next(request)
    except AuthConfigurationError as error:
        from fastapi.responses import JSONResponse
        response = JSONResponse({'detail': str(error)}, status_code=503)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


class RunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    consent: bool = False


class ConsentRequest(BaseModel):
    consent: bool = False


@app.get('/api/status')
def status(request: Request, response: Response):
    sid = session(request, response)
    configured = bool(os.getenv('GOOGLE_CREDENTIALS_JSON') or os.path.exists('credentials.json')) and bool(os.getenv('OAUTH_REDIRECT_URI'))
    return {'oauth_configured': configured, 'authorized': token_for(sid) is not None,
            'ai_configured': bool(os.getenv('GEMINI_API_KEY'))}


@app.post('/api/authorize')
def authorize(body: ConsentRequest, request: Request):
    if not body.consent:
        raise HTTPException(400, 'Confirm permission to connect Gmail first.')
    sid = session(request)
    if not sid:
        raise HTTPException(401, 'Reload the app to start a session.')
    try:
        flow = oauth_flow()
        url, state = flow.authorization_url(access_type='offline', prompt='consent select_account')
    except (OSError, ValueError, KeyError):
        raise HTTPException(503, 'The service owner must configure Google Web OAuth.')
    db, _ = storage()
    with db:
        db.execute('UPDATE sessions SET state=?, verifier=?, state_expires=? WHERE id=?',
                   (state, flow.code_verifier, time.time() + 600, sid))
    return {'authorization_url': url}


@app.get('/api/oauth/callback')
def callback(request: Request):
    sid = session(request)
    state = request.query_params.get('state', '')
    # With two Vercel projects the cookie belongs to the frontend host.
    # Relay Google's API-host callback to the frontend's same-origin /api proxy.
    # The code is still exchanged with the original registered redirect URI.
    if not sid and request.query_params.get('via_frontend') != '1':
        redirect_origin = urlsplit(os.getenv('OAUTH_REDIRECT_URI', '')).netloc
        if redirect_origin and redirect_origin != urlsplit(FRONTEND_URL).netloc:
            query = {key: request.query_params[key] for key in ('state', 'code', 'error') if key in request.query_params}
            query['via_frontend'] = '1'
            return RedirectResponse(FRONTEND_URL + '/api/oauth/callback?' + urlencode(query), status_code=303)
    try:
        verifier = consume_state(sid, state)
    except ValueError as error:
        raise HTTPException(400, str(error))
    if request.query_params.get('error'):
        return RedirectResponse(FRONTEND_URL + '?connection=cancelled', status_code=303)
    code = request.query_params.get('code')
    if not code:
        raise HTTPException(400, 'Google did not return an authorization code.')
    try:
        flow = oauth_flow(state=state, verifier=verifier)
        flow.fetch_token(code=code)
        credentials = flow.credentials
        scopes = credentials.granted_scopes or credentials.scopes or []
        if not set(SCOPES).issubset(scopes):
            raise ValueError('Gmail permission was not granted')
        save_token(sid, credentials)
    except Exception:
        raise HTTPException(400, 'Could not connect Gmail. Please try connecting again.')
    return RedirectResponse(FRONTEND_URL + '?connection=success', status_code=303)


@app.post('/api/disconnect')
def disconnect(request: Request, response: Response):
    sid = session(request)
    token = token_for(sid)
    db, _ = storage()
    with db:
        db.execute('DELETE FROM sessions WHERE id=?', (sid,))
    response.delete_cookie(COOKIE, path='/')
    revoked = False
    if token:
        try:
            result = requests.post('https://oauth2.googleapis.com/revoke',
                                   data={'token': token.get('refresh_token') or token['token']}, timeout=10)
            revoked = result.status_code == 200
        except requests.RequestException:
            pass
    return {'disconnected': True, 'revoked': revoked}


@app.post('/api/run')
def run(body: RunRequest, request: Request):
    if not body.consent:
        raise HTTPException(400, 'Permission to read email and share it with Gemini is required.')
    if not body.goal.strip():
        raise HTTPException(400, 'Goal cannot be empty.')
    sid = session(request)
    token = token_for(sid)
    if not token:
        raise HTTPException(401, 'Connect your Gmail account first.')
    if not os.getenv('GEMINI_API_KEY'):
        raise HTTPException(503, 'The service owner has not configured the AI service.')
    credentials = Credentials.from_authorized_user_info(token, SCOPES)
    try:
        if not credentials.valid:
            credentials.refresh(GoogleRequest())
            save_token(sid, credentials)
    except Exception:
        raise HTTPException(401, 'Gmail permission expired. Disconnect and connect again.')
    calls = []
    try:
        result = run_agent(body.goal.strip(), verbose=False,
                           on_tool_call=lambda name, args: calls.append(f'{name}({args})'),
                           credentials=credentials)
    except Exception:
        raise HTTPException(502, 'The email service could not complete this request. Please try again.')
    return {'result': result, 'tool_calls': calls}


@app.get('/api/health')
def health():
    return {'ok': True}
