"""Single local workspace OAuth. Tokens live only in the OS credential vault."""
import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
import keyring
from .database import GraphError

SCOPES = (
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar.events.readonly',
    'https://www.googleapis.com/auth/calendar.calendarlist.readonly',
)
REDIRECT = 'http://127.0.0.1:8001/auth/google/callback'
WRITE_SCOPES = ('https://www.googleapis.com/auth/gmail.send','https://www.googleapis.com/auth/calendar.events')


class CallbackLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(v.split('?', 1)[0] if isinstance(v, str) and '/auth/google/callback?' in v else v for v in record.args)
        return True


class TokenVault:
    def __init__(self):
        # The OS user plus this checkout identifies the authorized local workspace.
        workspace = str(Path(__file__).resolve().parents[2])
        self.service = 'ORBIT.Google.' + hashlib.sha256(workspace.encode()).hexdigest()[:16]

    def backend(self):
        backend = keyring.get_keyring()
        if not type(backend).__module__.startswith(('keyring.backends.Windows', 'keyring.backends.macOS', 'keyring.backends.SecretService')):
            raise GraphError(503, 'secure_storage_unavailable', 'An OS credential vault is required; plaintext token storage is disabled.')
        return backend

    def load(self):
        try:
            raw = self.backend().get_password(self.service, 'local-owner')
            return json.loads(raw) if raw else None
        except GraphError:
            raise
        except Exception:
            raise GraphError(503, 'secure_storage_unavailable', 'Cannot read the OS credential vault.') from None

    def save(self, value):
        try:
            self.backend().set_password(self.service, 'local-owner', json.dumps(value))
        except GraphError:
            raise
        except Exception:
            raise GraphError(503, 'secure_storage_unavailable', 'Cannot save tokens in the OS credential vault.') from None

    def clear(self):
        if self.load() is not None:
            try:
                self.backend().delete_password(self.service, 'local-owner')
            except Exception:
                raise GraphError(503, 'secure_storage_unavailable', 'Cannot clear the OS credential vault.') from None


class GoogleAuth:
    def __init__(self, vault=None):
        self.vault = vault or TokenVault()
        self.states = {}
        self.lock = threading.RLock()

    def config(self):
        missing = [k for k in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET') if not os.getenv(k)]
        if missing:
            raise GraphError(503, 'google_unconfigured', 'Configure ' + ', '.join(missing) + ' in the backend environment.')
        redirect = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', REDIRECT)
        if redirect != REDIRECT:
            raise GraphError(503, 'google_redirect_invalid', 'GOOGLE_OAUTH_REDIRECT_URI must match the registered loopback callback.')
        return {'client_id': os.environ['GOOGLE_CLIENT_ID'], 'client_secret': os.environ['GOOGLE_CLIENT_SECRET'], 'redirect_uri': redirect}

    def begin(self, writes=False):
        config = self.config()
        state, browser, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        with self.lock:
            self.states = {k: v for k, v in self.states.items() if v[0] > time.time()}
            if len(self.states) >= 32:
                raise GraphError(429, 'oauth_busy', 'Too many pending authorization requests.')
            self.states[state] = (time.time() + 600, browser, verifier, SCOPES + WRITE_SCOPES if writes else SCOPES)
        query = dict(client_id=config['client_id'], redirect_uri=config['redirect_uri'], response_type='code',
                     scope=' '.join(SCOPES + WRITE_SCOPES if writes else SCOPES), access_type='offline', prompt='consent', state=state,
                     code_challenge=challenge, code_challenge_method='S256')
        return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(query), browser

    def exchange(self, form):
        try:
            response = httpx.post('https://oauth2.googleapis.com/token', data=form, timeout=20)
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise GraphError(502, 'google_token_unavailable', 'Google token exchange is unavailable; reconnect or retry.') from None
        if not isinstance(data,dict):
            raise GraphError(502, 'google_token_failed', 'Google returned an invalid token response.')
        if response.status_code != 200 or not data.get('access_token'):
            if data.get('error') == 'invalid_grant':
                raise GraphError(401, 'google_reconnect', 'Google authorization expired or was revoked. Reconnect Google.')
            raise GraphError(502, 'google_token_failed', 'Google token exchange failed. Check configuration and reconnect.')
        return data

    def finish(self, state, browser, code, error=None):
        with self.lock:
            pending = self.states.pop(state, None)
            if not pending or pending[0] < time.time() or not browser or not secrets.compare_digest(pending[1], browser):
                raise GraphError(400, 'oauth_state_invalid', 'Authorization state is invalid or expired. Start connecting again.')
            if error or not code:
                raise GraphError(400, 'oauth_denied', 'Google authorization was not completed.')
            data = self.exchange({**self.config(), 'code': code, 'code_verifier': pending[2], 'grant_type': 'authorization_code'})
            if not set(pending[3] if len(pending)>3 else SCOPES) <= set(data.get('scope', '').split()) or not data.get('refresh_token'):
                raise GraphError(403, 'google_scopes_missing', 'Grant all three read scopes, requested write scopes and offline access when reconnecting Google.')
            data['expires_at'] = time.time() + int(data.get('expires_in', 3600))
            data['connection_id'] = secrets.token_hex(16)
            self.vault.save(data)

    def token(self, force=False):
        with self.lock:
            data = self.vault.load()
            if not data or data.get('reconnect_required'):
                raise GraphError(401, 'google_reconnect', 'Connect Google at /auth/google/connect.')
            if not force and data.get('expires_at', 0) > time.time() + 60:
                return data['access_token']
            try:
                refreshed = self.exchange({**self.config(), 'grant_type': 'refresh_token', 'refresh_token': data['refresh_token']})
            except GraphError as exc:
                if exc.code == 'google_reconnect':
                    self.vault.save({'reconnect_required': True})
                raise
            if 'scope' in refreshed and not set(SCOPES) <= set(refreshed['scope'].split()):
                raise GraphError(403, 'google_scopes_missing', 'Reconnect Google and grant all requested read scopes.')
            data.update(refreshed)
            data['expires_at'] = time.time() + int(refreshed.get('expires_in', 3600))
            self.vault.save(data)
            return data['access_token']

    def require_scopes(self, scopes):
        data=self.vault.load() or {}
        if not set(scopes)<=set(data.get('scope','').split()):
            raise GraphError(403,'google_write_consent','Authorize Google write scopes at /auth/google/connect?write=true.')


google_auth = GoogleAuth()


def mount_auth(app):
    from fastapi import Request
    from fastapi.responses import RedirectResponse, HTMLResponse
    logger=logging.getLogger('uvicorn.access')
    if not any(isinstance(f,CallbackLogFilter) for f in logger.filters):logger.addFilter(CallbackLogFilter())

    @app.get('/auth/google/connect')
    def connect(request: Request, write: bool=False, onboarding: bool=False):
        if onboarding:
            saved=google_auth.vault.load() or {}
            write=write or any(scope in saved.get('scope','').split() for scope in WRITE_SCOPES)
        url, browser = google_auth.begin(writes=write)
        response = RedirectResponse(url, status_code=303)
        response.set_cookie('orbit_google_state', browser, httponly=True, samesite='lax', max_age=600, path='/auth/google')
        if onboarding:
            # Only allow a configured frontend origin, never an arbitrary return URL.
            from urllib.parse import urlsplit
            parsed=urlsplit(request.headers.get('referer',''))
            origin=parsed.scheme+'://'+parsed.netloc
            allowed=app.state.service.repo.db.settings.allowed_origins
            if origin in allowed:response.set_cookie('orbit_onboarding_return',origin+'/welcome?step=apps',httponly=True,samesite='lax',max_age=600,path='/auth/google')
        else:response.delete_cookie('orbit_onboarding_return',path='/auth/google')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/auth/google/callback')
    def callback(request: Request):
        target=request.cookies.get('orbit_onboarding_return','')
        allowed=app.state.service.repo.db.settings.allowed_origins
        valid_target=target in [origin+'/welcome?step=apps' for origin in allowed]
        try:
            google_auth.finish(request.query_params.get('state', ''), request.cookies.get('orbit_google_state'),
                               request.query_params.get('code'), request.query_params.get('error'))
        except GraphError:
            if not valid_target:raise
            response=RedirectResponse(target+'&oauth=failed',status_code=303)
            response.delete_cookie('orbit_google_state',path='/auth/google')
            response.delete_cookie('orbit_onboarding_return',path='/auth/google')
            response.headers.update({'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
            return response
        if valid_target:
            response=RedirectResponse(target+'&oauth=connected',status_code=303)
            response.delete_cookie('orbit_google_state',path='/auth/google')
            response.delete_cookie('orbit_onboarding_return',path='/auth/google')
            response.headers.update({'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
            return response
        response = HTMLResponse('Google connected to ORBIT. You may close this tab and return to ORBIT.')
        response.delete_cookie('orbit_google_state', path='/auth/google')
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'none'"})
        return response
