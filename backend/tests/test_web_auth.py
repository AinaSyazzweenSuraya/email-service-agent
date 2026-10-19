import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient
import app as server
import web_auth

TOKEN = {'token': 'access-one', 'refresh_token': 'refresh-one',
         'token_uri': 'https://oauth2.googleapis.com/token', 'client_id': 'client',
         'client_secret': 'secret', 'scopes': web_auth.SCOPES, 'expiry': '2099-01-01T00:00:00Z'}


class ConsentTests(unittest.TestCase):
    postgres = False
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_url = os.getenv('TEST_DATABASE_URL', '') if self.postgres else ''
        self.env = patch.dict(os.environ, {'AUTH_DATA_DIR': self.directory.name,
                              'DATABASE_URL': self.database_url, 'VERCEL': '',
                              'TOKEN_ENCRYPTION_KEY': web_auth.Fernet.generate_key().decode() if self.postgres else '',
                              'COOKIE_SECURE': 'false', 'GEMINI_API_KEY': 'test-only',
                              'OAUTH_REDIRECT_URI': 'http://localhost:8000/api/oauth/callback'})
        self.env.start()
        self.a = TestClient(server.app, base_url='http://localhost:8000')
        self.b = TestClient(server.app, base_url='http://localhost:8000')
        self.a.get('/api/status')
        self.b.get('/api/status')
        self.origin = {'origin': server.FRONTEND_ORIGIN}

    def tearDown(self):
        self.a.close()
        self.b.close()
        self.env.stop()
        self.directory.cleanup()

    def sid(self, client):
        return web_auth.digest(client.cookies.get(web_auth.COOKIE))

    def grant(self, client):
        credentials = Mock()
        credentials.to_json.return_value = json.dumps(TOKEN)
        web_auth.save_token(self.sid(client), credentials)

    def start_oauth(self):
        flow = Mock(code_verifier='verifier')
        flow.authorization_url.return_value = ('https://accounts.google.com/oauth', 'state-123')
        with patch.object(server, 'oauth_flow', return_value=flow):
            response = self.a.post('/api/authorize', json={'consent': True}, headers=self.origin)
        self.assertEqual(response.status_code, 200)
        return flow

    def test_health_works_without_ai_key(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            self.assertEqual(self.a.get('/api/health').json(), {'ok': True})

    def test_sessions_are_distinct_and_cookie_is_http_only(self):
        self.assertNotEqual(self.sid(self.a), self.sid(self.b))
        self.assertIn('HttpOnly', TestClient(server.app).get('/api/status').headers['set-cookie'])

    def test_connect_needs_explicit_consent(self):
        with patch.object(server, 'oauth_flow') as flow:
            self.assertEqual(self.a.post('/api/authorize', json={'consent': False}, headers=self.origin).status_code, 400)
            flow.assert_not_called()

    def test_cross_origin_mutation_rejected(self):
        self.assertEqual(self.a.post('/api/authorize', json={'consent': True}, headers={'origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.a.post('/api/disconnect').status_code, 403)

    def test_tokens_are_encrypted_and_isolated(self):
        self.grant(self.a)
        self.assertTrue(self.a.get('/api/status').json()['authorized'])
        self.assertFalse(self.b.get('/api/status').json()['authorized'])
        self.assertIsNone(web_auth.token_for(self.sid(self.b)))
        db, _ = web_auth.storage()
        with db:
            encrypted = db.execute('SELECT token FROM sessions WHERE id=?', (self.sid(self.a),)).fetchone()[0]
        self.assertNotIn(b'refresh-one', encrypted)

    def test_read_requires_connection_and_per_request_consent(self):
        with patch.object(server, 'run_agent') as agent:
            self.assertEqual(self.a.post('/api/run', json={'goal': 'hello', 'consent': True}, headers=self.origin).status_code, 401)
            self.grant(self.a)
            self.assertEqual(self.a.post('/api/run', json={'goal': 'hello'}, headers=self.origin).status_code, 400)
            agent.assert_not_called()

    def test_agent_receives_only_current_session_credentials(self):
        self.grant(self.a)
        with patch.object(server, 'run_agent', return_value='Your digest') as agent:
            response = self.a.post('/api/run', json={'goal': 'hello', 'consent': True}, headers=self.origin)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(agent.call_args.kwargs['credentials'].token, 'access-one')
            response = self.b.post('/api/run', json={'goal': 'hello', 'consent': True}, headers=self.origin)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(agent.call_count, 1)

    def test_callback_rejects_other_browser_and_wrong_state(self):
        self.start_oauth()
        for client, state in [(self.b, 'state-123'), (self.a, 'wrong')]:
            self.assertEqual(client.get('/api/oauth/callback', params={'state': state, 'code': 'x'}).status_code, 400)

    def test_callback_saves_only_to_initiating_session_and_prevents_replay(self):
        self.start_oauth()
        flow = Mock()
        flow.credentials.to_json.return_value = json.dumps(TOKEN)
        flow.credentials.granted_scopes = web_auth.SCOPES
        with patch.object(server, 'oauth_flow', return_value=flow):
            response = self.a.get('/api/oauth/callback?state=state-123&code=code', follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(self.a.get('/api/oauth/callback?state=state-123&code=code').status_code, 400)
        self.assertIsNotNone(web_auth.token_for(self.sid(self.a)))
        self.assertIsNone(web_auth.token_for(self.sid(self.b)))

    def test_callback_rejects_missing_gmail_scope(self):
        self.start_oauth()
        flow = Mock()
        flow.credentials.granted_scopes = ['openid']
        with patch.object(server, 'oauth_flow', return_value=flow):
            response = self.a.get('/api/oauth/callback?state=state-123&code=x')
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(web_auth.token_for(self.sid(self.a)))

    def test_real_authorization_url_uses_pkce_and_readonly_scope(self):
        from urllib.parse import urlsplit, parse_qs
        config = {'web': {'client_id': 'test-client', 'client_secret': 'test-secret',
                         'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                         'token_uri': 'https://oauth2.googleapis.com/token'}}
        with patch.dict(os.environ, {'GOOGLE_CREDENTIALS_JSON': json.dumps(config)}):
            flow = web_auth.oauth_flow()
            url, state = flow.authorization_url(access_type='offline', prompt='consent select_account')
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['scope'], web_auth.SCOPES)
        self.assertTrue(flow.code_verifier)
        self.assertTrue(state)

    def test_search_tool_forwards_session_credentials(self):
        import agent
        credentials = object()
        with patch.object(agent, 'fetch_recent_emails', return_value=[]) as fetch:
            agent.execute_search_emails('is:unread', credentials=credentials)
        self.assertIs(fetch.call_args.kwargs['credentials'], credentials)

    def test_cancel_consumes_state_without_saving_token(self):
        self.start_oauth()
        response = self.a.get('/api/oauth/callback?state=state-123&error=access_denied', follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('cancelled', response.headers['location'])
        self.assertIsNone(web_auth.token_for(self.sid(self.a)))
        self.assertEqual(self.a.get('/api/oauth/callback?state=state-123&code=x').status_code, 400)

    def test_expired_state_is_rejected(self):
        self.start_oauth()
        db, _ = web_auth.storage()
        with db:
            db.execute('UPDATE sessions SET state_expires=0')
        self.assertEqual(self.a.get('/api/oauth/callback?state=state-123&code=x').status_code, 400)

    def test_disconnect_deletes_local_access_even_if_revoke_fails(self):
        self.grant(self.a)
        self.grant(self.b)
        sid = self.sid(self.a)
        with patch.object(server.requests, 'post', side_effect=server.requests.ConnectionError):
            response = self.a.post('/api/disconnect', headers=self.origin)
        self.assertEqual(response.json(), {'disconnected': True, 'revoked': False})
        self.assertIsNone(web_auth.token_for(sid))
        self.assertIsNotNone(web_auth.token_for(self.sid(self.b)))

    def test_encryption_key_rotation_requires_reconnect_without_server_error(self):
        self.grant(self.a)
        with patch.dict(os.environ, {'TOKEN_ENCRYPTION_KEY': web_auth.Fernet.generate_key().decode()}):
            response = self.a.get('/api/status')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['authorized'])

    def test_shared_cli_token_is_never_used(self):
        with patch('gmail_auth.get_gmail_credentials', side_effect=AssertionError('shared token used')):
            response = self.b.post('/api/run', json={'goal': 'hello', 'consent': True}, headers=self.origin)
            self.assertEqual(response.status_code, 401)

    def test_api_callback_relays_to_frontend_cookie_and_exchanges_original_code(self):
        with patch.object(server, 'FRONTEND_URL', 'https://web.example'), patch.object(server, 'FRONTEND_ORIGIN', 'https://web.example'):
            with TestClient(server.app, base_url='https://web.example') as browser, TestClient(server.app, base_url='https://api.example') as api:
                browser.get('/api/status')
                flow = Mock(code_verifier='verifier')
                flow.authorization_url.return_value = ('https://accounts.google.com/oauth', 'relay-state')
                flow.credentials.to_json.return_value = json.dumps(TOKEN)
                flow.credentials.granted_scopes = web_auth.SCOPES
                with patch.dict(os.environ, {'OAUTH_REDIRECT_URI': 'https://api.example/api/oauth/callback'}), patch.object(server, 'oauth_flow', return_value=flow):
                    self.assertEqual(browser.post('/api/authorize', json={'consent': True}, headers={'origin': 'https://web.example'}).status_code, 200)
                    response = api.get('/api/oauth/callback?state=relay-state&code=google-code', follow_redirects=False)
                    self.assertEqual(response.status_code, 303)
                    self.assertTrue(response.headers['location'].startswith('https://web.example/api/oauth/callback?'))
                    self.assertEqual(browser.get(response.headers['location'], follow_redirects=False).status_code, 303)
                    flow.fetch_token.assert_called_once_with(code='google-code')
                    self.assertTrue(browser.get('/api/status').json()['authorized'])

    def test_callback_without_cookie_does_not_redirect_forever(self):
        with TestClient(server.app) as browser:
            response = browser.get('/api/oauth/callback?state=x&code=x&via_frontend=1')
        self.assertEqual(response.status_code, 400)

    def test_missing_vercel_storage_produces_safe_actionable_error(self):
        with patch.dict(os.environ, {'VERCEL': '1', 'DATABASE_URL': ''}):
            response = self.a.get('/api/status')
        self.assertEqual(response.status_code, 503)
        self.assertIn('DATABASE_URL', response.json()['detail'])

    def test_database_requires_persistent_encryption_key(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://never-connect.invalid/db', 'TOKEN_ENCRYPTION_KEY': ''}):
            response = self.a.get('/api/status')
        self.assertEqual(response.status_code, 503)
        self.assertIn('TOKEN_ENCRYPTION_KEY', response.json()['detail'])

    def test_replayed_callback_cannot_race_second_exchange(self):
        from concurrent.futures import ThreadPoolExecutor
        self.start_oauth()
        def consume():
            try:
                web_auth.consume_state(self.sid(self.a), 'state-123')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: consume(), range(2))), [False, True])


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL to a disposable Postgres database')
class PostgresConsentTests(ConsentTests):
    postgres = True


if __name__ == '__main__':
    unittest.main()
