import time
from urllib.parse import urlparse,parse_qs
from types import SimpleNamespace
import pytest
from backend.orbit.onboarding import connector_status
from backend.orbit.integration_auth import GoogleAuth,SCOPES,WRITE_SCOPES
from backend.orbit.database import GraphError

class Vault:
    def __init__(self,value=None):self.value=value
    def load(self):return self.value
    def save(self,value):self.value=value
class Reads:
    def __init__(self,error=None):self.calls=[];self.error=error
    def get(self,provider,path,params=None):
        self.calls.append((provider,path))
        if self.error and provider==self.error[0]:raise GraphError(self.error[1],'controlled','controlled failure')
        return {'ok':True}

def test_permissions_are_individual_and_unsupported_stays_unavailable(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID','fixture');monkeypatch.setenv('GOOGLE_CLIENT_SECRET','fixture');monkeypatch.setenv('SLACK_BOT_TOKEN','fixture')
    reads=Reads();result=connector_status(SimpleNamespace(vault=Vault({'scope':SCOPES[0]})),reads)
    statuses={r['id']:r['status'] for r in result['connections']}
    assert statuses=={'gmail':'connected','calendar':'needs_permission','slack':'connected','drive':'coming_soon','tasks':'coming_soon','excel':'coming_soon','teams':'coming_soon'}
    assert ('calendar','users/me/calendarList') not in reads.calls

@pytest.mark.parametrize('code,status',[(401,'needs_permission'),(403,'needs_permission'),(429,'unavailable'),(503,'unavailable')])
def test_provider_failures_never_turn_green(monkeypatch,code,status):
    monkeypatch.setenv('SLACK_BOT_TOKEN','fixture')
    result=connector_status(SimpleNamespace(vault=Vault({'scope':' '.join(SCOPES)})),Reads(('gmail',code)))
    assert next(r for r in result['connections'] if r['id']=='gmail')['status']==status

def test_oauth_returns_to_onboarding_and_preserves_granted_writes(client,monkeypatch):
    from backend.orbit import integration_auth
    monkeypatch.setenv('GOOGLE_CLIENT_ID','fixture');monkeypatch.setenv('GOOGLE_CLIENT_SECRET','fixture')
    auth=GoogleAuth(Vault({'scope':' '.join(SCOPES+WRITE_SCOPES)}));monkeypatch.setattr(integration_auth,'google_auth',auth)
    monkeypatch.setattr(auth,'exchange',lambda form:{'access_token':'fixture','refresh_token':'fixture','scope':' '.join(SCOPES+WRITE_SCOPES),'expires_in':3600})
    response=client.get('/auth/google/connect?onboarding=true',headers={'referer':'http://127.0.0.1:5173/welcome?step=apps'},follow_redirects=False)
    assert response.status_code==303
    query=parse_qs(urlparse(response.headers['location']).query)
    assert set(WRITE_SCOPES)<=set(query['scope'][0].split())
    result=client.get('/auth/google/callback',params={'state':query['state'][0],'code':'fixture'},follow_redirects=False)
    assert result.status_code==303 and result.headers['location']=='http://127.0.0.1:5173/welcome?step=apps&oauth=connected'
    assert 'access_token' not in result.text

def test_denial_returns_safely_and_external_return_is_rejected(client,monkeypatch):
    from backend.orbit import integration_auth
    monkeypatch.setenv('GOOGLE_CLIENT_ID','fixture');monkeypatch.setenv('GOOGLE_CLIENT_SECRET','fixture')
    auth=GoogleAuth(Vault());monkeypatch.setattr(integration_auth,'google_auth',auth)
    response=client.get('/auth/google/connect?onboarding=true',headers={'referer':'http://127.0.0.1:5173/welcome'},follow_redirects=False)
    state=parse_qs(urlparse(response.headers['location']).query)['state'][0]
    result=client.get('/auth/google/callback',params={'state':state,'error':'access_denied'},follow_redirects=False)
    assert result.headers['location']=='http://127.0.0.1:5173/welcome?step=apps&oauth=failed'
    response=client.get('/auth/google/connect?onboarding=true',headers={'referer':'https://untrusted.example/welcome'},follow_redirects=False)
    assert 'orbit_onboarding_return' not in response.headers.get('set-cookie','')


def test_disconnect_requires_ui_and_clears_shared_google_only(client,monkeypatch):
    from backend.orbit import onboarding
    vault=Vault({'scope':' '.join(SCOPES)})
    vault.clear=lambda:setattr(vault,'value',None)
    auth=GoogleAuth(vault);auth.states['pending']=('controlled',)
    monkeypatch.setattr(onboarding,'google_auth',auth)
    assert client.post('/api/onboarding/google/disconnect').status_code==403
    assert vault.load()
    response=client.post('/api/onboarding/google/disconnect',headers={'X-Orbit-UI':'1'})
    assert response.json()=={'disconnected':['gmail','calendar']}
    assert vault.load() is None and not auth.states
