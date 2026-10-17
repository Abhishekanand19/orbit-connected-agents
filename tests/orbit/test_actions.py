"""Real MCP + FalkorDB. External HTTP is controlled; no live writes or LLM calls."""
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.orbit.actions import Actions
from backend.orbit.action_models import ActionDraft
from backend.orbit.action_providers import ActionProviders
from backend.orbit.database import Database,GraphError
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.models import NodeUpsert,ConversationCreate,MessageCreate,RelationshipUpsert,ClaimCreate
from backend.orbit.integration_auth import SCOPES,WRITE_SCOPES

class Auth:
    def __init__(self):
        self.saved={'connection_id':'fixture-owner','scope':' '.join(SCOPES+WRITE_SCOPES)}
        self.vault=self
    def load(self):return self.saved
    def token(self,force=False):return 'fixture-token'
    def require_scopes(self,scopes):
        if not set(scopes)<=set(self.saved['scope'].split()):raise GraphError(403,'missing_scope','Authorize write scopes.')

class ProviderFixture:
    def __init__(self):
        self.writes=[];self.messages={};self.slack=[];self.mode='ok';self.lock=threading.Lock()
        self.events={'existing':{'id':'existing','etag':'"v1"','summary':'Before','start':{'dateTime':'2026-10-20T10:00:00Z'},'end':{'dateTime':'2026-10-20T11:00:00Z'}}}
    def respond(self,req):
        with self.lock:return self.handle(req)
    def handle(self,req):
        path=req.url.path
        if req.method in ('POST','PATCH'):
            self.writes.append(req)
            if self.mode=='reject':return httpx.Response(429,json={'error':'controlled rate limit'})
            payload=json.loads(req.content)
            if path.endswith('/messages/send'):
                id='mail'+str(len(self.messages)+1);self.messages[id]={'id':id,'raw':payload['raw'],'labelIds':['SENT']};result={'id':id}
            elif path.endswith('/chat.postMessage'):
                message={**payload,'ts':'1792490400.'+str(len(self.slack)+1),'user':'UFIXTURE'};self.slack.append(message)
                result={'ok':True,'channel':payload['channel'],'ts':message['ts']}
            elif '/events' in path:
                id=payload.get('id') or path.rsplit('/',1)[1]
                if req.method=='PATCH' and req.headers.get('if-match')!=self.events[id]['etag']:return httpx.Response(412,json={})
                self.events[id]={**self.events.get(id,{}),**payload,'id':id,'etag':'"v2"'};result=self.events[id]
            else:raise AssertionError('Unexpected write path')
            if self.mode=='timeout':raise httpx.ReadTimeout('Controlled ambiguous timeout')
            return httpx.Response(200,json=result)
        if self.mode=='readback_failure':return httpx.Response(503,json={})
        if '/events/' in path:
            return httpx.Response(200,json=self.events.get(path.rsplit('/',1)[1],{}))
        if path.endswith('/messages'):return httpx.Response(200,json={'messages':[{'id':id} for id in self.messages]})
        if path.endswith('/profile'):return httpx.Response(200,json={'emailAddress':'fixture@example.test'})
        if '/messages/' in path:
            import base64
            from email.parser import BytesParser
            from email.policy import default
            data=dict(self.messages.get(path.rsplit('/',1)[1],{}))
            if data.get('raw'):
                raw=data['raw'];message=BytesParser(policy=default).parsebytes(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
                if not message.get('From'):message['From']='fixture@example.test'
                data['raw']=base64.urlsafe_b64encode(message.as_bytes()).decode()
            return httpx.Response(200,json=data)
        if path.endswith('/conversations.history'):
            messages=[m for m in self.slack if m['channel']==req.url.params['channel'] and (not req.url.params.get('oldest') or m['ts']==req.url.params['oldest'])]
            return httpx.Response(200,json={'ok':True,'messages':messages})
        raise AssertionError('Unexpected read path')

@pytest.fixture
def world(settings,monkeypatch):
    monkeypatch.setenv('SLACK_BOT_TOKEN','fixture-token')
    db=Database(settings);db.initialize();s=GraphService(GraphRepository(db))
    for id,kind,props in [('bot','Bot',{'name':'Bot'}),('owner','Person',{'name':'Owner'}),('other','Person',{'name':'Other'}),
        ('job','Task',{'name':'Review','status':'OPEN'}),('event','Event',{'name':'Appointment','starts_at':'2026-10-20T10:00:00Z','ends_at':'2026-10-20T11:00:00Z'})]:
        s.upsert_node(id,NodeUpsert(type=kind,properties=props))
    s.create_conversation(ConversationCreate(id='session',bot_id='bot',title='Actions'))
    s.create_message('session',MessageCreate(id='request',role='user',content='Prepare the requested changes for my review.'))
    fixture=ProviderFixture();providers=ActionProviders(auth=Auth(),transport=httpx.MockTransport(fixture.respond))
    yield s,Actions(s,providers),fixture
    db.graph.delete();db.close()

def draft(kind='task_update',**updates):
    payload={
        'task_update':{'task_id':'job','changes':{'status':'DONE'},'assignee_id':'owner'},
        'task_create':{'task_id':'new-task','changes':{'name':'Prepare report','status':'OPEN'},'assignee_id':'owner'},
        'gmail_send':{'to':['fixture@example.test'],'subject':'Review update','body':'Controlled test content.'},
        'slack_post':{'channel_id':'C0C9SH122US','text':'Controlled test content.'},
        'calendar_create':{'calendar_id':'fixture-calendar','changes':{'summary':'Controlled event','starts_at':'2026-10-20T12:00:00Z','ends_at':'2026-10-20T13:00:00Z','attendees':['fixture@example.test']}},
        'calendar_update':{'calendar_id':'fixture-calendar','event_id':'existing','expected_etag':'"v1"','changes':{'summary':'Rescheduled','starts_at':'2026-10-20T12:00:00Z','ends_at':'2026-10-20T13:00:00Z','attendees':['fixture@example.test']}}
    }[kind]
    return ActionDraft(kind=kind,payload=payload,reason='Requested change based on connected context.',affected_ids=['job','owner'],evidence_ids=['request'],**updates)

def run(manager,proposal):
    manager.approve(proposal['id'],proposal['digest'])
    return manager.dispatch(proposal['id'],proposal['digest'])

@pytest.mark.parametrize('kind',['calendar_create','calendar_update','gmail_send','slack_post','task_create','task_update'])
def test_actual_mcp_approved_execution_and_fresh_readback(world,kind):
    s,manager,fixture=world;p=manager.propose(draft(kind),'request')
    assert p['status']=='AWAITING_APPROVAL' and not fixture.writes
    with pytest.raises(Exception):manager.dispatch(p['id'],p['digest'])
    assert not fixture.writes and s.require('job')['properties']['status']=='OPEN'
    result=run(manager,p)
    assert result['status']=='VERIFIED' and result['verification']['verified']
    assert [h['status'] for h in result['history']]==['PROPOSED','AWAITING_APPROVAL','APPROVED','EXECUTING','VERIFIED']
    assert manager.get(p['id'])['properties']['transport']=='mcp-memory'
    assert manager.dispatch(p['id'],p['digest'])['status']=='VERIFIED'
    assert len(fixture.writes)==(0 if kind.startswith('task') else 1)
    assert s.repo.db.execute("MATCH (:Action {id:$id})-[:PRODUCED]->(o:Outcome) RETURN o.status",{'id':p['id']},read=True)==[['VERIFIED']]

def test_reject_and_payload_owner_tampering(world):
    s,manager,fixture=world;p=manager.propose(draft('slack_post'),'request')
    for digest,owner in [('0'*64,'local-owner'),(p['digest'],'another-user')]:
        with pytest.raises(GraphError):manager.approve(p['id'],digest,owner)
    manager.reject(p['id'],p['digest'])
    with pytest.raises(Exception):manager.dispatch(p['id'],p['digest'])
    assert not fixture.writes
    other=manager.propose(draft('gmail_send'),'request')
    manager.db.execute('MATCH (a:Action {id:$id}) SET a.spec=$spec',{'id':other['id'],'spec':json.dumps({**draft('gmail_send').model_dump(),'reason':'Tampered'})})
    with pytest.raises(GraphError,match='changed'):manager.approve(other['id'],other['digest'])

def test_stale_graph_expiry_and_changed_account(world):
    s,manager,fixture=world;p=manager.propose(draft('slack_post'),'request')
    s.upsert_relationship(RelationshipUpsert(source='job',type='ASSIGNED_TO',target='other'))
    with pytest.raises(GraphError,match='Graph evidence changed'):manager.approve(p['id'],p['digest'])
    mail=manager.propose(draft('gmail_send'),'request');manager.providers.auth.saved['connection_id']='another-account'
    with pytest.raises(GraphError,match='account changed'):manager.approve(mail['id'],mail['digest'])
    assert not fixture.writes

def test_expired_proposal_refresh_requires_new_approval(world,monkeypatch):
    import time
    s,manager,fixture=world;p=manager.propose(draft(),'request');clock=time.time()
    monkeypatch.setattr('backend.orbit.actions.time.time',lambda:clock+1801)
    with pytest.raises(GraphError,match='expired'):manager.approve(p['id'],p['digest'])
    fresh=manager.refresh(p['id'],p['digest'])
    assert fresh['id']!=p['id'] and fresh['digest']!=p['digest'] and fresh['status']=='AWAITING_APPROVAL'
    assert manager.get(p['id'])['properties']['status']=='SUPERSEDED'
    with pytest.raises(GraphError):manager.approve(fresh['id'],p['digest'])
    assert run(manager,fresh)['status']=='VERIFIED'
    assert manager.propose(draft(),'request')['id']==fresh['id']

def test_concurrent_double_approval_never_duplicates(world):
    s,manager,fixture=world;p=manager.propose(draft('slack_post'),'request')
    manager.approve(p['id'],p['digest'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:manager.dispatch(p['id'],p['digest']),range(2)))
    assert len(fixture.writes)==1
    assert manager.get(p['id'])['properties']['status']=='VERIFIED'
    assert all(r['status'] in ('EXECUTING','VERIFIED') for r in results)

@pytest.mark.parametrize('kind',['calendar_create','gmail_send','slack_post'])
def test_ambiguous_timeout_readback_recovery_without_resend(world,kind):
    s,manager,fixture=world;p=manager.propose(draft(kind),'request');fixture.mode='timeout'
    assert run(manager,p)['status']=='UNKNOWN'
    with pytest.raises(GraphError,match='cannot be replayed'):manager.retry(p['id'],p['digest'])
    fixture.mode='ok'
    assert manager.dispatch(p['id'],p['digest'],verify=True)['status']=='VERIFIED'
    assert len(fixture.writes)==1

def test_safe_retry_partial_workflow_and_readback_failure(world):
    s,manager,fixture=world;p=manager.propose(draft('gmail_send'),'request');fixture.mode='reject'
    failed=run(manager,p);assert failed['status']=='FAILED' and failed['retryable']
    fixture.mode='ok';assert manager.retry(p['id'],p['digest'])['status']=='VERIFIED'
    other=manager.propose(draft('slack_post'),'request');fixture.mode='readback_failure'
    unknown=run(manager,other);assert unknown['status']=='UNKNOWN' and unknown['receipt']['ts']
    assert manager.get(p['id'])['properties']['status']=='VERIFIED'
    fixture.mode='ok';assert manager.dispatch(other['id'],other['digest'],verify=True)['status']=='VERIFIED'
    assert len(fixture.writes)==3

def test_restart_persistence_and_cross_conversation_dedup(world):
    s,manager,fixture=world;p=manager.propose(draft('slack_post'),'request');run(manager,p)
    script="""import sys,json
from backend.orbit.config import Settings
from backend.orbit.database import Database
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.actions import Actions
db=Database(Settings.model_validate_json(sys.argv[1]));db.initialize()
print(Actions(GraphService(GraphRepository(db))).get(sys.argv[2])['properties']['status']);db.close()
"""
    assert subprocess.check_output([sys.executable,'-B','-c',script,s.repo.db.settings.model_dump_json(),p['id']],text=True).strip()=='VERIFIED'
    s.create_conversation(ConversationCreate(id='later',bot_id='bot',title='Later'))
    s.create_message('later',MessageCreate(id='later:request',role='user',content='Review the same action.'))
    again=Actions(s,manager.providers).propose(draft('slack_post'),'later:request')
    assert again['id']==p['id'] and again['status']=='VERIFIED' and len(fixture.writes)==1

def test_startup_recovers_interrupted_action_to_unknown(world):
    s,manager,fixture=world;p=manager.propose(draft('gmail_send'),'request');manager.approve(p['id'],p['digest'])
    manager.transition(p['id'],['APPROVED'],'EXECUTING')
    manager.providers.perform('gmail_send',p['payload'],p['id'])
    restarted=Actions(s,manager.providers);restarted.recover()
    assert restarted.get(p['id'])['properties']['status']=='UNKNOWN'
    assert restarted.dispatch(p['id'],p['digest'],verify=True)['status']=='VERIFIED'
    assert len(fixture.writes)==1

def test_calendar_stale_etag_and_readback_mismatch(world):
    s,manager,fixture=world;p=manager.propose(draft('calendar_update'),'request')
    fixture.events['existing']['etag']='"changed"'
    assert run(manager,p)['status']=='FAILED' and not fixture.writes
    other=manager.propose(draft('slack_post'),'request');fixture.mode='timeout';assert run(manager,other)['status']=='UNKNOWN'
    fixture.mode='ok';fixture.slack[0]['text']='different text'
    assert manager.dispatch(other['id'],other['digest'],verify=True)['status']=='UNKNOWN'

def test_graph_constraints_determine_action_proposals(world):
    from backend.orbit.intelligence import ImpactEngine,ImpactRequest
    s,manager,fixture=world
    s.upsert_node('evidence',NodeUpsert(type='Source',properties={'name':'Fixture verification','kind':'MANUAL','observed_at':'2026-10-20T09:00:00Z'}))
    s.create_claim(ClaimCreate(id='verified',text='Fixture schedule evidence',status='CONFIRMED',source_id='evidence',verification_source_id='evidence',subject_ids=['event'],observed_at='2026-10-20T09:00:00Z'))
    s.upsert_relationship(RelationshipUpsert(source='other',type='AVAILABLE_FOR',target='event',properties={'evidence_id':'verified','evidence_state':'CONFIRMED'}))
    impact=ImpactEngine(s).analyze(ImpactRequest(root_id='event',trigger_claim_id='verified'));assert impact.state=='ACT'
    d=draft('task_update',decision_id=impact.id);d.affected_ids.append('event')
    p=manager.propose(d,'request');assert p['tool']=='action_task_update'
    s.upsert_relationship(RelationshipUpsert(source='other',type='AVAILABLE_FOR',target='event',properties={'evidence_state':'REFUTED'}))
    with pytest.raises(GraphError):manager.approve(p['id'],p['digest'])
    next_impact=ImpactEngine(s).analyze(ImpactRequest(root_id='event',trigger_claim_id='verified'));assert next_impact.state=='CONFLICT'
    d.decision_id=next_impact.id
    with pytest.raises(GraphError,match='CONFLICT'):manager.propose(d,'request')
    assert not fixture.writes

def test_approval_session_http_boundary(world):
    from backend.orbit.api import create_app
    s,manager,fixture=world;p=manager.propose(draft(),'request')
    with TestClient(create_app(s.repo.db.settings)) as client:
        assert client.get('/api/actions').status_code==403
        headers={'Origin':'http://127.0.0.1:5173','X-Orbit-UI':'1'}
        assert client.get('/api/actions',headers=headers).status_code==401
        response=client.post('/api/actions/session',headers=headers,json={})
        assert response.status_code==200 and 'HttpOnly' in response.headers['set-cookie']
        assert client.post('/api/actions/'+p['id']+'/approve',json={'digest':p['digest']},headers={**headers,'Origin':'https://evil.test'}).status_code==403
        assert client.post('/api/actions/'+p['id']+'/approve',json={'digest':p['digest'],'payload':{}},headers=headers).status_code==422
        assert client.post('/api/actions/'+p['id']+'/approve',json={'digest':p['digest']},headers=headers).json()['status']=='VERIFIED'
        assert client.get('/api/actions',headers=headers).json()['actions'][0]['status']=='VERIFIED'

def test_specialist_proposes_without_executing_or_extra_llm_calls(world,monkeypatch):
    from backend.orbit.agents import Collaboration
    from backend.orbit.chat import ChatRequest
    from backend.orbit import llm
    s,manager,fixture=world;calls=[]
    def generate(system,payload,schema):
        calls.append(payload)
        if 'roles' in payload:return {'assignments':[{'agent':'tasks','task':'Update Review task'}]}
        d=draft();d.evidence_ids=['request']
        return {'summary':'Proposed completing Review','evidence_ids':['job'],'actions':[d.model_dump()]}
    monkeypatch.setattr(llm,'generate',generate)
    result=Collaboration(s).run(ChatRequest(id='request',bot_id='coordinator',name='Coordinator',conversation_id='session',content='Complete Review and assign it to Owner.'))
    assert len(calls)==2 and result['actions'][0]['status']=='AWAITING_APPROVAL'
    assert s.require('job')['properties']['status']=='OPEN' and not fixture.writes

def test_write_scopes_required_without_breaking_read_consent(world):
    s,manager,fixture=world;manager.providers.auth.saved['scope']=' '.join(SCOPES)
    p=manager.propose(draft('gmail_send'),'request')
    result=run(manager,p)
    assert result['status']=='FAILED' and result['retryable'] and not fixture.writes
