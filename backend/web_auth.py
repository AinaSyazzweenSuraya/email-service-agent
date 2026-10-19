"""Browser-scoped sessions and encrypted OAuth tokens; never use CLI token.json."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

import certifi
import psycopg

from cryptography.fernet import Fernet, InvalidToken
from google_auth_oauthlib.flow import Flow

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TTL = 7 * 24 * 3600
COOKIE = 'email_session'


class AuthConfigurationError(RuntimeError):
    """Safe configuration message that may be shown to the service owner."""


class Database:
    """Small DB-API adapter; always close connections after each transaction."""
    def __init__(self, connection, postgres=False):
        self.connection = connection
        self.postgres = postgres

    def execute(self, sql, params=()):
        if self.postgres:
            sql = sql.replace('?', '%s')
        return self.connection.execute(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()


def cipher_for(directory=None):
    key = os.getenv('TOKEN_ENCRYPTION_KEY')
    if key:
        try:
            return Fernet(key.encode())
        except (ValueError, UnicodeError):
            raise AuthConfigurationError('TOKEN_ENCRYPTION_KEY must be a valid Fernet key.') from None
    if os.getenv('DATABASE_URL') or os.getenv('VERCEL'):
        raise AuthConfigurationError('The service owner must configure TOKEN_ENCRYPTION_KEY on the backend.')
    key_path = directory / 'token.key'
    if not key_path.exists():
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(Fernet.generate_key())
    return Fernet(key_path.read_bytes())


def storage():
    url = os.getenv('DATABASE_URL')
    if os.getenv('VERCEL') and not url:
        raise AuthConfigurationError('Connect the Neon database to the backend Production environment (DATABASE_URL).')
    if url:
        cipher = cipher_for()
        # Local disposable Postgres tests can use HTTP-loopback-equivalent TLS settings.
        # All remote database connections verify both the CA and server hostname.
        tls = {} if urlsplit(url).hostname in ('localhost', '127.0.0.1', '::1') else {
            'sslmode': 'verify-full', 'sslrootcert': certifi.where()}
        try:
            connection = psycopg.connect(url, connect_timeout=10, **tls)
        except (psycopg.Error, ValueError):
            raise AuthConfigurationError('Session database is unavailable. Check the backend DATABASE_URL and Neon connection.') from None
        db = Database(connection, postgres=True)
        schema = 'CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, expires DOUBLE PRECISION, token BYTEA, state TEXT, verifier TEXT, state_expires DOUBLE PRECISION)'
    else:
        directory = Path(os.getenv('AUTH_DATA_DIR', str(Path.home() / '.local/share/email-agent')))
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        cipher = cipher_for(directory)
        db = Database(sqlite3.connect(directory / 'auth.sqlite', timeout=30))
        os.chmod(directory / 'auth.sqlite', 0o600)
        schema = 'CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, expires REAL, token BLOB, state TEXT, verifier TEXT, state_expires REAL)'
    try:
        db.execute(schema)
        db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
        db.connection.commit()
    except Exception:
        db.connection.rollback()
        db.connection.close()
        raise AuthConfigurationError('Could not initialize session storage. Check database access and table permissions.') from None
    return db, cipher


def consume_state(sid, state):
    db, _ = storage()
    with db:
        if not db.postgres:
            db.execute('BEGIN IMMEDIATE')
        lock = ' FOR UPDATE' if db.postgres else ''
        row = db.execute('SELECT state, verifier, state_expires FROM sessions WHERE id=?' + lock, (sid,)).fetchone()
        if not row or not row[0] or not secrets.compare_digest(row[0], state) or row[2] < time.time():
            raise ValueError('Invalid or expired connection request. Connect Gmail again.')
        db.execute('UPDATE sessions SET state=NULL, verifier=NULL, state_expires=NULL WHERE id=?', (sid,))
    return row[1]


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def session(request, response=None):
    raw = request.cookies.get(COOKIE, '')
    db, _ = storage()
    with db:
        row = db.execute('SELECT id FROM sessions WHERE id=? AND expires>?', (digest(raw), time.time())).fetchone() if raw else None
        if row:
            return row[0]
        if response is None:
            return None
        raw = secrets.token_urlsafe(32)
        sid = digest(raw)
        db.execute('INSERT INTO sessions(id, expires) VALUES (?, ?)', (sid, time.time() + TTL))
    response.set_cookie(COOKIE, raw, httponly=True, secure=os.getenv('COOKIE_SECURE', 'true').lower() == 'true', samesite='lax', max_age=TTL, path='/')
    return sid


def oauth_flow(state=None, verifier=None):
    config = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if config:
        config = json.loads(config)
    else:
        config = json.loads(Path('credentials.json').read_text())
    if 'web' not in config:
        raise ValueError('A Google Web application OAuth client is required.')
    redirect = os.environ['OAUTH_REDIRECT_URI']
    return Flow.from_client_config(config, scopes=SCOPES, state=state, redirect_uri=redirect, code_verifier=verifier, autogenerate_code_verifier=verifier is None)


def token_for(sid):
    if not sid:
        return None
    db, cipher = storage()
    with db:
        row = db.execute('SELECT token FROM sessions WHERE id=? AND expires>?', (sid, time.time())).fetchone()
    if not row or not row[0]:
        return None
    try:
        return json.loads(cipher.decrypt(row[0]))
    except InvalidToken:
        # Key rotation invalidates old sessions: require reconnecting, not a 500.
        db, _ = storage()
        with db:
            db.execute('UPDATE sessions SET token=NULL WHERE id=?', (sid,))
        return None


def save_token(sid, credentials):
    db, cipher = storage()
    with db:
        db.execute('UPDATE sessions SET token=? WHERE id=? AND expires>?', (cipher.encrypt(credentials.to_json().encode()), sid, time.time()))
