"""Real MCP transport and FalkorDB; HTTP fixtures are controlled, not live providers."""
import base64
import json
import logging
import time
from urllib.parse import parse_qs, urlparse
import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.orbit.database import Database, GraphError
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.models import NodeUpsert, ConversationCreate, MessageCreate, RelationshipUpsert
from backend.orbit.chat import ChatRequest
from backend.orbit.integration_auth import GoogleAuth, TokenVault, SCOPES, REDIRECT, CallbackLogFilter
from backend.orbit.integration_providers import Providers
from backend.orbit.integrations import Binding, bind, select, ToolRunner, ReadCall
from backend.orbit.mcp_tools import build_server, session


class Vault:
    def __init__(self):self.value=None
    def load(self):return self.value
    def save(self,value):self.value=dict(value)


class Auth:
    def __init__(self):self.refreshes=[]
    def token(self,force=False):self.refreshes.append(force);return 'fixture-token'


@pytest.fixture
def world(settings):
    db=Database(settings);db.initialize();s=GraphService(GraphRepository(db))
    s.upsert_node('chatbot:coordinator',NodeUpsert(type='Bot',properties={'name':'Coordinator'}))
    s.create_conversation(ConversationCreate(id='integration:session',bot_id='chatbot:coordinator',title='Integrations'))
    for id,kind in [('Launch','Task'),('Meeting','Event')]:
        s.upsert_node(id,NodeUpsert(type=kind,properties={'name':id,'starts_at':'2026-10-20T10:00:00Z','ends_at':'2026-10-20T11:00:00Z'}))
    yield s
    db.graph.delete();db.close()


def request(s, content='Check latest updates for Launch.', id='integration:message'):
    s.create_message('integration:session',MessageCreate(id=id,role='user',content=content))
    return ChatRequest(id=id,bot_id='coordinator',name='Coordinator',conversation_id='integration:session',content=content)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('SLACK_BOT_TOKEN','fixture-token')
    calls=[]
    event={'id':'ev1','summary':'Launch meeting','start':{'dateTime':'2026-10-20T10:30:00Z'},'end':{'dateTime':'2026-10-20T11:30:00Z'},'attendees':[{'email':'fixture@example.test'}]}
    def respond(req):
        calls.append(req)
        assert req.method=='GET'
        path=req.url.path
        if path.endswith('/messages/m1'):
            data={'id':'m1','internalDate':'1792490400000','payload':{'mimeType':'text/plain','headers':[{'name':'From','value':'fixture@example.test'},{'name':'Subject','value':'Launch confirmation'}],'body':{'data':base64.urlsafe_b64encode(b'Launch timing is tentative.').decode()}}}
        elif path.endswith('/messages'):data={'messages':[{'id':'m1'}]}
        elif path.endswith('/calendarList'):data={'items':[{'id':'primary','summary':'Fixture','timeZone':'UTC'}]}
        elif path.endswith('/events/ev1'):data=event
        elif path.endswith('/events'):data={'timeZone':'UTC','items':[event]}
        elif path.endswith('/conversations.list'):data={'ok':True,'channels':[{'id':'C0C9SH122US','name':'orbit-demo','is_member':True},{'id':'COTHER00','name':'other','is_member':False}]}
        elif path.endswith('/conversations.history'):data={'ok':True,'messages':[{'ts':'1792490400.0001','user':'UFIXTURE','text':'Launch handoff is tentative.'}]}
        else:raise AssertionError('Unexpected HTTP path')
        return httpx.Response(200,json=data)
    return Providers(auth=Auth(),transport=httpx.MockTransport(respond)),calls


def test_real_mcp_discovery_and_all_read_tools(world,provider):
    adapter,calls=provider
    async def check():
        async with session(build_server(world,adapter)) as client:
            tools=(await client.list_tools()).tools
            assert len(tools)==9 and all(t.annotations.readOnlyHint for t in tools)
            cases=[('gmail_search',{'query':'Launch'}),('gmail_read',{'message_id':'m1'}),('calendar_list',{}),
                   ('calendar_events',{'calendar_id':'primary','start':'2026-10-20T10:00:00Z','end':'2026-10-20T11:00:00Z'}),
                   ('calendar_event',{'calendar_id':'primary','event_id':'ev1'}),
                   ('calendar_conflicts',{'calendar_id':'primary','start':'2026-10-20T10:00:00Z','end':'2026-10-20T11:00:00Z'}),
                   ('slack_channels',{}),('slack_messages',{'channel_id':'C0C9SH122US'}),('graph_dependencies',{'entity_id':'Launch'})]
            results={}
            for name,args in cases:
                response=await client.call_tool(name,args)
                assert not response.isError
                data=response.structuredContent or json.loads(response.content[0].text)
                assert data['ok'], (name,data)
                results[name]=data['result']
            assert results['gmail_read']['sender']=='fixture@example.test'
            assert results['gmail_read']['content']=='Launch timing is tentative.'
            assert results['calendar_conflicts']['overlapping_event_ids']==['ev1']
            assert results['calendar_conflicts']['state']=='WAIT'
            assert len(results['slack_channels']['items'])==1
            assert results['slack_messages']['items'][0]['timestamp']
            assert results['graph_dependencies']['nodes'][0]['id']=='Launch'
            for name,args in [('slack_messages',{'channel_id':'DPRIVATE'}),('gmail_search',{'query':'x','limit':500}),('gmail_send',{})]:
                assert (await client.call_tool(name,args)).isError
    anyio.run(check)
    assert len(calls)==8


def test_relationship_changes_actual_mcp_selection_and_evidence(world,provider):
    adapter,calls=provider
    slack=bind(world,Binding(entity_id='Launch',provider='slack',resource_id='C0C9SH122US'))
    calendar=bind(world,Binding(entity_id='Meeting',provider='calendar',resource_id='primary'))
    runner=ToolRunner(world,adapter)
    first=runner.run(request(world))
    assert [t['properties']['tool'] for t in first['traces']]==['slack_messages']
    edges=world.repo.traverse(__import__('backend.orbit.models',fromlist=['TraversalRequest']).TraversalRequest(root_id='Launch'))['edges']
    world.delete_relationship(next(e['id'] for e in edges if e['target']==slack['id']))
    world.upsert_relationship(RelationshipUpsert(source='Launch',type='RELATED_TO',target=calendar['id']))
    second=runner.run(request(world,id='integration:second'))
    assert [t['properties']['tool'] for t in second['traces']]==['calendar_conflicts']
    evidence=second['evidence'][0]
    assert evidence['properties']['evidence_state']=='UNVERIFIED'
    assert evidence['properties']['observed_at']
    assert json.loads(evidence['properties']['result'])['overlapping_event_ids']==['ev1']
    assert second['traces'][0]['properties']['transport']=='mcp-memory'
    assert second['traces'][0]['properties']['completed_at']
    # A new runner reloads persisted completed invocations; retry does not read again.
    before=len(calls)
    ToolRunner(world,adapter).run(request(world,id='integration:second'))
    assert len(calls)==before
    assert len(ToolRunner(world).traces('integration:second'))==1


def test_no_unnecessary_tools_and_explicit_provider_restriction(world,provider):
    adapter,calls=provider
    bind(world,Binding(entity_id='Launch',provider='slack',resource_id='C0C9SH122US'))
    bind(world,Binding(entity_id='Launch',provider='calendar',resource_id='primary'))
    assert not ToolRunner(world,adapter).run(request(world,'Hello, Launch!',id='hello'))['traces']
    assert not calls
    result=ToolRunner(world,adapter).run(request(world,'Read Slack updates for Launch.',id='slack-only'))
    assert {t['properties']['tool'] for t in result['traces']}=={'slack_messages'}
    before=len(calls)
    result=ToolRunner(world,adapter).run(request(world,'Show Launch dependencies using graph-only context.',id='graph-only'))
    assert {t['properties']['tool'] for t in result['traces']}=={'graph_dependencies'}
    assert len(calls)==before


def test_gmail_search_read_provenance_and_cross_bot_retrieval(world,provider):
    adapter,calls=provider
    bind(world,Binding(entity_id='Launch',provider='gmail',resource_id='subject:Launch'))
    result=ToolRunner(world,adapter).run(request(world,'Find email updates for Launch.'))
    assert {t['properties']['tool'] for t in result['traces']}=={'gmail_search','gmail_read'}
    assert all(t['properties']['status']=='DONE' for t in result['traces'])
    world.create_conversation(ConversationCreate(id='second:session',bot_id='chatbot:coordinator',title='Later'))
    from backend.orbit.memory import retrieve
    assert any(n['properties'].get('record_kind')=='EXTERNAL_EVIDENCE' for n in retrieve(world,'Launch','second:session')['nodes'])
    assert not world.repo.search_nodes(kind=__import__('backend.orbit.models',fromlist=['EntityType']).EntityType.Claim)['items']
    with pytest.raises(GraphError,match='immutable snapshots'):
        world.upsert_node(result['evidence'][0]['id'],NodeUpsert(type='Source',properties={'description':'Changed evidence'}))
    assert 'fixture-token' not in json.dumps(result)


def test_calendar_observation_constrains_existing_impact_engine(world,provider):
    from backend.orbit.models import ClaimCreate
    from backend.orbit.intelligence import ImpactEngine,ImpactRequest
    adapter,_=provider
    for id in ('A','B'):world.upsert_node(id,NodeUpsert(type='Person',properties={'name':id}))
    world.upsert_node('manual',NodeUpsert(type='Source',properties={'name':'Explicit fixture verification','kind':'MANUAL','observed_at':'2026-10-20T09:00:00Z'}))
    world.create_claim(ClaimCreate(id='verified',text='Verified fixture schedule',status='CONFIRMED',source_id='manual',verification_source_id='manual',subject_ids=['Launch','Meeting'],observed_at='2026-10-20T09:00:00Z'))
    for a,kind,b in [('Launch','ASSIGNED_TO','A'),('Meeting','ASSIGNED_TO','A'),('B','AVAILABLE_FOR','Launch')]:
        world.upsert_relationship(RelationshipUpsert(source=a,type=kind,target=b,properties={'evidence_id':'verified','evidence_state':'CONFIRMED'}))
    req=ImpactRequest(root_id='Launch',trigger_claim_id='verified')
    assert ImpactEngine(world).analyze(req).state=='ACT'
    bind(world,Binding(entity_id='Launch',provider='calendar',resource_id='primary'))
    result=ToolRunner(world,adapter).run(request(world,'Check calendar schedule for Launch.'))
    observations=[{'id':n['id'],'result':json.loads(n['properties']['result'])} for n in result['evidence']]
    constrained=ImpactEngine(world).analyze(req,observations)
    assert constrained.state=='WAIT' and not constrained.proposed_changes
    assert observations[0]['id'] in constrained.constraints
    assert all(a.state!='ACT' for a in constrained.alternatives)


def test_listing_intent_and_negative_requests(world,provider):
    adapter,calls=provider
    runner=ToolRunner(world,adapter)
    for i,text in enumerate(['Do not read Slack.', 'Only draft a Slack update.', 'Check Launch using graph-only context.']):
        assert not runner.run(request(world,text,id='negative:'+str(i)))['traces']
    assert not calls
    calendars=runner.run(request(world,'List available calendars.',id='list:calendars'))
    assert calendars['traces'][0]['properties']['tool']=='calendar_list'
    channels=runner.run(request(world,'List Slack channels.',id='list:channels'))
    assert channels['traces'][0]['properties']['tool']=='slack_channels'


def test_read_budget_and_failed_attempt_history(world,provider,monkeypatch):
    adapter,calls=provider
    for provider_name,resource in [('gmail','subject:Launch'),('calendar','primary'),('slack','C0C9SH122US')]:
        bind(world,Binding(entity_id='Launch',provider=provider_name,resource_id=resource))
    result=ToolRunner(world,adapter).run(request(world))
    assert len(calls)==4 and len(result['traces'])==4
    monkeypatch.delenv('SLACK_BOT_TOKEN',raising=False)
    req=request(world,'Read Slack.',id='retry:failed')
    runner=ToolRunner(world,adapter)
    assert runner.run(req)['traces'][0]['properties']['status']=='FAILED'
    monkeypatch.setenv('SLACK_BOT_TOKEN','fixture-token')
    retried=runner.run(req)
    assert {t['properties']['status'] for t in retried['traces']}=={'FAILED','DONE'}


def test_shared_specialists_receive_mcp_observations(world,provider,monkeypatch):
    from backend.orbit import agents,llm
    adapter,_=provider
    bind(world,Binding(entity_id='Launch',provider='slack',resource_id='C0C9SH122US'))
    original=ToolRunner.__init__
    monkeypatch.setattr(ToolRunner,'__init__',lambda self,s,providers=None:original(self,s,adapter))
    seen=[]
    def generate(system,payload,schema):
        assert payload['external_evidence'] and payload['tool_traces'][0]['status']=='DONE'
        if 'roles' in payload:return {'assignments':[{'agent':'research','task':'Review Launch evidence'},{'agent':'communication','task':'Draft an unsent Launch update'}]}
        seen.append(payload)
        return {'summary':'Tentative handoff observed','evidence_ids':[payload['external_evidence'][0]['id']],'proposals':[],'draft':None,'handoff':None}
    monkeypatch.setattr(llm,'generate',generate)
    result=agents.Collaboration(world).run(request(world))
    assert len(seen)==2 and len(result['findings'])==2
    assert seen[1]['shared_findings']


@pytest.mark.parametrize('status,code',[(401,'provider_authorization'),(403,'provider_authorization'),(429,'provider_rate_limit'),(500,'provider_failed')])
def test_safe_provider_http_failures(status,code):
    provider=Providers(auth=Auth(),transport=httpx.MockTransport(lambda req:httpx.Response(status,json={'error':'SECRET MUST NOT ESCAPE'})))
    with pytest.raises(GraphError) as caught:provider.gmail_search('x')
    assert caught.value.code==code and 'SECRET' not in str(caught.value)


def test_missing_credentials_and_failed_invocation_journal(world,monkeypatch):
    monkeypatch.delenv('SLACK_BOT_TOKEN',raising=False)
    result=ToolRunner(world,Providers(auth=Auth())).run(request(world,'Read Slack updates.'))
    trace=result['traces'][0]['properties']
    assert trace['status']=='FAILED' and 'SLACK_BOT_TOKEN' in trace['error']
    assert not result['evidence']
    auth=GoogleAuth(Vault())
    with pytest.raises(GraphError,match='Connect Google'):auth.token()


def test_revoked_slack_and_google_401_refresh(monkeypatch):
    monkeypatch.setenv('SLACK_BOT_TOKEN','fixture')
    p=Providers(auth=Auth(),transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'ok':False,'error':'token_revoked'})))
    with pytest.raises(GraphError,match='token_revoked'):p.slack_messages('C0C9SH122US')
    calls=[];auth=Auth()
    def response(req):
        calls.append(1);return httpx.Response(401 if len(calls)==1 else 200,json={'messages':[]})
    assert Providers(auth=auth,transport=httpx.MockTransport(response)).gmail_search('x')['items']==[]
    assert auth.refreshes==[False,True]


def test_calendar_all_day_transparency_incomplete_and_invalid_intervals():
    from backend.orbit.intelligence import calendar_constraints
    events={'time_zone':'UTC','truncated':True,'items':[{'id':'all-day','start':{'date':'2026-10-20'},'end':{'date':'2026-10-21'}},
        {'id':'free','transparency':'transparent'},{'id':'cancelled','status':'cancelled'},{'id':'bad','start':None}]}
    result=calendar_constraints(events,'2026-10-20T10:00:00Z','2026-10-20T11:00:00Z')
    assert result['overlapping_event_ids']==['all-day'] and result['incomplete'] and result['state']=='WAIT'
    with pytest.raises(GraphError):Providers(auth=Auth()).calendar_events('primary','2026-10-20','2026-10-21')


@pytest.fixture
def oauth(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID','fixture-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET','fixture-secret')
    monkeypatch.setenv('GOOGLE_OAUTH_REDIRECT_URI',REDIRECT)
    return GoogleAuth(Vault())


def test_oauth_state_browser_binding_replay_and_pkce(oauth,monkeypatch):
    forms=[]
    def post(url,data,timeout):
        forms.append(data)
        return httpx.Response(200,json={'access_token':'fixture-access','refresh_token':'fixture-refresh','scope':' '.join(SCOPES),'expires_in':3600})
    monkeypatch.setattr(httpx,'post',post)
    url,browser=oauth.begin();q=parse_qs(urlparse(url).query)
    assert q['redirect_uri']==[REDIRECT] and q['access_type']==['offline']
    assert set(q['scope'][0].split())==set(SCOPES) and q['code_challenge_method']==['S256']
    state=q['state'][0]
    with pytest.raises(GraphError,match='state'):oauth.finish(state,'wrong-browser','code')
    assert not forms
    url,browser=oauth.begin();state=parse_qs(urlparse(url).query)['state'][0]
    oauth.finish(state,browser,'code')
    assert forms[0]['code_verifier'] and oauth.token()=='fixture-access'
    with pytest.raises(GraphError,match='state'):oauth.finish(state,browser,'code')


def test_oauth_expired_denied_partial_scope_and_refresh(oauth,monkeypatch):
    url,browser=oauth.begin();state=parse_qs(urlparse(url).query)['state'][0]
    oauth.states[state]=(time.time()-1,browser,'v')
    with pytest.raises(GraphError,match='expired'):oauth.finish(state,browser,'code')
    url,browser=oauth.begin();state=parse_qs(urlparse(url).query)['state'][0]
    with pytest.raises(GraphError,match='not completed'):oauth.finish(state,browser,None,'access_denied')
    monkeypatch.setattr(oauth,'exchange',lambda form:{'access_token':'x','refresh_token':'r','scope':SCOPES[0]})
    url,browser=oauth.begin();state=parse_qs(urlparse(url).query)['state'][0]
    with pytest.raises(GraphError,match='three read scopes'):oauth.finish(state,browser,'code')
    assert oauth.vault.load() is None
    oauth.vault.save({'access_token':'old','refresh_token':'refresh','expires_at':0,'connection_id':'owner'})
    monkeypatch.setattr(oauth,'exchange',lambda form:{'access_token':'new','expires_in':3600})
    assert oauth.token()=='new' and oauth.vault.load()['refresh_token']=='refresh'
    def revoked(form):raise GraphError(401,'google_reconnect','Reconnect Google.')
    monkeypatch.setattr(oauth,'exchange',revoked)
    with pytest.raises(GraphError):oauth.token(force=True)
    assert oauth.vault.load()=={'reconnect_required':True}


def test_vault_rejects_insecure_backend(monkeypatch):
    import keyring
    monkeypatch.setattr(keyring,'get_keyring',lambda:object())
    with pytest.raises(GraphError,match='OS credential vault'):TokenVault().load()


def test_oauth_routes_local_boundary_and_trace_api(world,oauth,monkeypatch):
    from backend.orbit import integration_auth
    from backend.orbit.api import create_app
    monkeypatch.setattr(integration_auth,'google_auth',oauth)
    monkeypatch.setattr(oauth,'exchange',lambda form:{'access_token':'secret-access','refresh_token':'secret-refresh','scope':' '.join(SCOPES)})
    with TestClient(create_app(world.repo.db.settings)) as client:
        response=client.get('/auth/google/connect',follow_redirects=False)
        state=parse_qs(urlparse(response.headers['location']).query)['state'][0]
        assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=lax' in response.headers['set-cookie']
        result=client.get('/auth/google/callback',params={'state':state,'code':'fixture-code'})
        assert result.status_code==200 and 'secret' not in result.text
        assert client.get('/api/integrations/status').json()['google']=='connected'
        assert len(client.get('/api/integrations/tools').json()['tools'])==9
        assert client.get('/api/integrations/status',headers={'host':'evil.example'}).status_code==400
        assert client.post('/api/integrations/bindings',headers={'origin':'https://evil.example'},json={}).status_code==403
        assert client.get('/auth/google/callback',params={'state':state,'code':'fixture-code'}).status_code==400
        req=request(world)
        assert client.get('/api/integrations/traces/'+req.id).json()=={'traces':[],'evidence':[]}
    rec=logging.LogRecord('uvicorn.access',20,'',0,'%s %s',('GET','/auth/google/callback?code=SECRET&state=PRIVATE'),None)
    CallbackLogFilter().filter(rec)
    assert 'SECRET' not in rec.getMessage()
