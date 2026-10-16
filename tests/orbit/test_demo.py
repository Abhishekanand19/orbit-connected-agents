"""Controlled end-to-end demo: actual DB/MCP, scripted model boundary only.
No external provider writes or live model calls. Production demo uses Collaboration.
"""
import json
import uuid
import pytest
from datetime import datetime,timedelta
from backend.orbit.demo import Demo,reset_demo,PREFIX
from backend.orbit.database import Database,GraphError
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.models import *
from backend.orbit.intelligence import ImpactEngine,ImpactRequest
from backend.orbit.actions import Actions
from backend.orbit.action_models import ActionDraft
from backend.orbit.receipts import Receipts
from backend.orbit import memory,llm

@pytest.fixture
def demo(settings):
 settings=settings.model_copy(update={'graph':'orbit_test_demo_'+uuid.uuid4().hex})
 db=Database(settings);db.initialize();d=Demo(GraphService(GraphRepository(db)));d.seed()
 yield d
 d.db.graph.delete();d.db.close()

def advance(d):
 for key in ['rumor','roads','pending','confirmed','available']:d.inject(key)

def analysis(d,key):
 id=d.inject(key)['decision_id'];return json.loads(d.s.require(id)['properties']['analysis'])

def test_seed_reset_and_isolation(demo,settings):
 d=demo;before=d.db.execute('MATCH (n) RETURN count(n)',read=True)
 d.seed();assert d.db.execute('MATCH (n) RETURN count(n)',read=True)==before
 other=Database(settings);other.initialize();other.execute("CREATE (:Sentinel {name:'preserve'})")
 try:
  with pytest.raises(GraphError):Demo(GraphService(GraphRepository(other)))
  d.inject('rumor');fresh=reset_demo(d.db);d.db=fresh;d.s=GraphService(GraphRepository(fresh));d.seed()
  assert d.state()['received']==[] and other.execute('MATCH (s:Sentinel) RETURN s.name',read=True)==[['preserve']]
  assert d.db.execute('MATCH (n) RETURN count(n)',read=True)==before
 finally:other.graph.delete();other.close()

def test_conflicting_inputs_and_graph_variation(demo):
 d=demo
 for key in ['rumor','roads','pending']:
  assert analysis(d,key)['state']=='WAIT'
  assert Actions(d.s).list()==[]
 confirmed=analysis(d,'confirmed');assert confirmed['state']=='WAIT'
 assert any('family:deployment' in a['constraint_ids'] for a in confirmed['alternatives'])
 assert any(p['node_ids']==['family:appointment','family:cab','family:physio'] for p in confirmed['affected'])
 available=analysis(d,'available');assert available['state']=='ACT'
 unavailable=analysis(d,'unavailable');assert unavailable['state']=='CONFLICT'
 assert available['proposed_changes']!=unavailable['proposed_changes']
 assert ImpactEngine(d.s).analyze(ImpactRequest(root_id='family:appointment',trigger_claim_id='family:claim:available',hops=4)).state=='CONFLICT'
 assert d.s.require('family:deployment')['properties']['starts_at'].startswith('2026-10-20T14:30')


def test_handoff_approval_mcp_new_session_selective_changes(demo,monkeypatch):
 d=demo;advance(d)
 # Controlled model adapter asserts graph facts and returns decisions derived from
 # the real deterministic engine. It is not installed in the demo/runtime.
 def provider(system,payload,schema=None):
  if 'roles' in payload:return {'assignments':[{'agent':'planner','task':'Review Internal demo cab arrangement'}]}
  impact=payload['deterministic_impacts'][0]
  if 'Analyze graph events' in system:
   return {'summary':impact['reason'],'evidence_ids':['family:appointment'],'handoff':{'agent':'tasks','task':'Review Internal demo cab arrangement'}}
  assert payload['shared_findings']
  if not payload.get('proposal_compilation'):
   return {'summary':impact['reason'],'evidence_ids':[payload['request_id']], 'proposals':['Review the connected transport task for the confirmed change.']}
  nodes={n['id']:n for n in payload['graph']['nodes']}
  assert 'family:cab' in nodes
  prior=[n for n in nodes.values() if n['type']=='Action' and n['properties'].get('status')=='VERIFIED']
  evidence=[payload['request_id']]+[n['id'] for n in prior[:1]]
  changes={'status':'CANCELLED'} if 'family:cab' in impact['unnecessary_ids'] else {'status':'IN_PROGRESS','starts_at':(datetime.fromisoformat(nodes['family:appointment']['properties']['starts_at'])-timedelta(minutes=75)).isoformat(),'ends_at':(datetime.fromisoformat(nodes['family:appointment']['properties']['starts_at'])-timedelta(minutes=15)).isoformat()}
  return {'missing_details':[],'actions':[{'kind':'task_update','payload':{'task_id':'family:cab','changes':changes},'reason':impact['reason'],'affected_ids':['family:cab','family:appointment'],'evidence_ids':evidence,'decision_id':impact['id']}]}
 monkeypatch.setattr(llm,'generate',provider)
 first=d.analyze('available');assert [r['properties']['owner'] for r in first['activity']]==['planner','tasks']
 assert all(r['properties']['status']=='DONE' for r in first['activity'])
 assert first['actions'],first['proposal_errors']
 proposal=first['actions'][0];manager=Actions(d.s)
 assert proposal['status']=='AWAITING_APPROVAL'
 manager.approve(proposal['id'],proposal['digest']);outcome=manager.dispatch(proposal['id'],proposal['digest'])
 assert outcome['status']=='VERIFIED'
 # Completed unrelated work must not be proposed again.
 d.s.upsert_node('family:physio',NodeUpsert(type='Task',properties={'status':'DONE'}))
 video=d.inject('video');assert video['conversation_id']!='family:session:1'
 assert len(memory.history(d.s,video['conversation_id']))==1
 result=analysis(d,'video');assert result['unnecessary_ids']==['family:cab']
 second=d.analyze('video');assert second['actions'],second['proposal_errors']
 cancel=second['actions'][0];assert cancel['payload']['changes']=={'status':'CANCELLED'}
 assert proposal['id'] in cancel['evidence_ids']
 receipt=Receipts(d.s).get(cancel['id'])
 assert any(p['id']==proposal['id'] and p['retrieval'] for p in receipt['previous'])
 assert d.s.require('family:physio')['properties']['status']=='DONE'
 assert d.s.require('family:deployment')['properties']['status']=='OPEN'
 manager.approve(cancel['id'],cancel['digest']);assert manager.dispatch(cancel['id'],cancel['digest'])['status']=='VERIFIED'
 monkeypatch.setattr(llm,'generate',lambda *a,**k:pytest.fail('Completed analysis must not call the model again'))
 assert d.analyze('video')['actions'][0]['id']==cancel['id']
 # New analysis cannot propose cancelling an already cancelled task.
 rerun=ImpactEngine(d.s).analyze(ImpactRequest(root_id='family:appointment',trigger_claim_id='family:claim:video'))
 assert 'family:cab' not in rerun.unnecessary_ids


def test_receipt_and_graph_match(demo):
 d=demo;advance(d);receipt=Receipts(d.s).get(d.inject('available')['decision_id'])
 assert receipt['status']=='PROPOSED'
 for path in receipt['paths']:
  assert path['complete']
  for edge in path['segments']:assert edge['edge']==d.s.repo.get_edge(edge['edge']['id'])
 assert d.inject('available')==d.inject('available')

@pytest.mark.parametrize('mode',['missing','unretrieved','invalid','waiting'])
def test_text_proposal_handoff_fails_closed(demo,monkeypatch,mode):
 from backend.orbit.agents import Collaboration
 from backend.orbit.chat import ChatRequest
 d=demo;advance(d)
 if mode=='waiting':d.inject('unavailable')
 key='unavailable' if mode=='waiting' else 'available'
 saved=d.inject(key);collab=Collaboration(d.s)
 req=ChatRequest(id=saved['message_id'],bot_id='coordinator',name='Orbit Coordinator',conversation_id=saved['conversation_id'],content='Propose connected internal task changes.')
 monkeypatch.setattr(collab,'shared',lambda _: [{'id':'saved-finding','properties':{'owner':'tasks','proposals':'["Change the task"]'}}])
 calls=[]
 def provider(*args):
  calls.append(1)
  if mode=='waiting':pytest.fail('Blocked graph must not call the model')
  if mode=='missing':return {'actions':[],'missing_details':['Exact new time is missing.']}
  return {'actions':[{'kind':'task_update','payload':{'task_id':'family:cab','changes':{'status':'BAD' if mode=='invalid' else 'DONE'}},'reason':'Change','affected_ids':['outside-graph'],'evidence_ids':[req.id],'decision_id':saved['decision_id']}],'missing_details':[]}
 monkeypatch.setattr(llm,'generate',provider)
 errors=collab.compile_proposals(req,Actions(d.s))
 assert Actions(d.s).list()==[]
 assert bool(errors)==(mode!='waiting')
 assert collab.compile_proposals(req,Actions(d.s))==errors
 assert len(calls)==(0 if mode=='waiting' else 1)

def test_saved_responsibility_becomes_exact_task_approval(demo,monkeypatch):
 from backend.orbit.agents import Collaboration
 from backend.orbit.chat import ChatRequest
 d=demo;advance(d);saved=d.inject('available');collab=Collaboration(d.s)
 req=ChatRequest(id=saved['message_id'],bot_id='coordinator',name='Orbit Coordinator',conversation_id=saved['conversation_id'],content='Propose an internal responsibility for the confirmed available person.')
 monkeypatch.setattr(collab,'shared',lambda _: [{'id':'saved-finding','properties':{'owner':'tasks','proposals':'["Create a responsibility for the available person"]'}}])
 def provider(system,payload,schema):
  nodes={n['id']:n for n in payload['graph']['nodes']};event=nodes['family:appointment']['properties']
  return {'missing_details':[], 'actions':[{'kind':'task_create','payload':{'task_id':payload['new_task_ids'][0],'changes':{'name':'Escort responsibility','starts_at':event['starts_at'],'ends_at':event['ends_at'],'status':'OPEN'},'assignee_id':'family:priya'},'reason':'Confirmed availability for the linked event.','affected_ids':['family:appointment'],'evidence_ids':[req.id],'decision_id':saved['decision_id']}]}
 monkeypatch.setattr(llm,'generate',provider)
 manager=Actions(d.s);assert collab.compile_proposals(req,manager)==[]
 p=manager.list()[0];assert p['tool']=='action_task_create' and p['status']=='AWAITING_APPROVAL'
 with pytest.raises(GraphError):d.s.require(p['payload']['task_id'])
 manager.approve(p['id'],p['digest']);assert manager.dispatch(p['id'],p['digest'])['status']=='VERIFIED'
 assert collab.compile_proposals(req,manager)==[] and len(manager.list())==1
