"""Onboarding connection checks. Only authenticated provider reads; no action dispatch."""
import os
from fastapi import Request
from concurrent.futures import ThreadPoolExecutor
from fastapi.responses import JSONResponse
from .database import GraphError
from .integration_auth import google_auth,SCOPES
from .integration_providers import Providers


def connector_status(auth=None,providers=None):
    auth=auth or google_auth;providers=providers or Providers(auth=auth)
    try:saved=auth.vault.load() or {};vault_error=False
    except GraphError:saved={};vault_error=True
    scopes=set(saved.get('scope','').split())
    configured=bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'))
    def check(service):
        row={'id':service,'status':'disconnected','can_connect':configured if service!='slack' else False,'detail':''}
        if service=='slack':
            if not os.getenv('SLACK_BOT_TOKEN'):
                row['detail']='Set SLACK_BOT_TOKEN in the backend to connect this workspace.';return row
        else:
            if vault_error:
                row.update(status='unavailable',detail='Secure credential storage is unavailable. Check the backend.');return row
            if not saved:
                row['detail']='Connect your Google account.' if configured else 'Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the backend.';return row
            needed=[SCOPES[0]] if service=='gmail' else [SCOPES[1],SCOPES[2]]
            if saved.get('reconnect_required') or not set(needed)<=scopes:
                row.update(status='needs_permission',detail='Reconnect Google to grant the required '+service+' read permissions.');return row
        try:
            if service=='gmail':providers.get('gmail','profile')
            elif service=='calendar':providers.get('calendar','users/me/calendarList',{'maxResults':1})
            else:providers.get('slack','auth.test')
            row.update(status='connected',detail='Authorization checked with the provider.')
        except GraphError as exc:
            authorization=exc.status in (401,403)
            row.update(status='needs_permission' if authorization else 'unavailable',detail=('Reconnect Google to restore access.' if service!='slack' else 'Check the Slack bot token and its permissions.') if authorization else 'Connection could not be verified. Retry when the provider is available.')
        return row
    with ThreadPoolExecutor(max_workers=3) as executor:rows=list(executor.map(check,['gmail','calendar','slack']))
    rows += [{'id':id,'status':'coming_soon','can_connect':False,'detail':'This integration is not available yet.'} for id in ['drive','tasks','excel','teams']]
    return {'connections':rows,'writes_performed':False}


def mount_onboarding(app):
    @app.post('/api/onboarding/google/disconnect')
    def disconnect(request: Request):
        if request.headers.get('X-Orbit-UI')!='1':
            raise GraphError(403,'ui_required','Disconnect requires the local Orbit UI.')
        with google_auth.lock:
            google_auth.vault.clear()
            google_auth.states.clear()
        return {'disconnected':['gmail','calendar']}

    @app.get('/api/onboarding/connections')
    def connections():
        return JSONResponse(connector_status(),headers={'Cache-Control':'no-store'})
