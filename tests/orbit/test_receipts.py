"""Receipt contract tests: real FalkorDB, real MCP, no live providers or LLM."""
import json
from fastapi.testclient import TestClient
from backend.orbit.api import create_app
from backend.orbit.receipts import Receipts
from backend.orbit.intelligence import ImpactEngine
from backend.orbit.models import *
from backend.orbit.service import GraphService
from backend.orbit.repository import GraphRepository
from tests.orbit.test_intelligence import world, request
from tests.orbit.test_actions import world as action_world, draft, run


def test_actual_paths_provenance_and_api(world):
 s,_=world; decision=ImpactEngine(s).analyze(request()); r=Receipts(s).get(decision.id)
 assert r['status']=='PROPOSED' and r['trigger']=='Verified fixture constraints'
 assert any(e['type']=='VERIFIED_BY' and e['target']=='source' for e in r['graph']['edges'])
 for path in r['paths']:
  assert path['complete']
  for segment in path['segments']:
   assert segment['edge']==s.repo.get_edge(segment['edge']['id'])
 assert any(p['labels']==['Hospital appointment','Transport booking'] for p in r['paths'])
 with TestClient(create_app(s.repo.db.settings)) as client:
  assert client.get('/api/receipts/'+decision.id).json()==r
  assert decision.id in [x['id'] for x in client.get('/api/receipts').json()['receipts']]
  assert client.get('/api/receipts/appointment').status_code==404


def test_changed_evidence_changes_new_receipt_preserves_old(world):
 s,edge=world; first=ImpactEngine(s).analyze(request()); before=Receipts(s).get(first.id)
 edge('priya','AVAILABLE_FOR','appointment','REFUTED')
 second=ImpactEngine(s).analyze(request()); after=Receipts(s).get(second.id)
 assert after['status']=='WAITING' and before['status']=='PROPOSED'
 assert after['reason']!=before['reason']
 assert Receipts(s).get(first.id)==before


def test_action_receipt_waiting_verified_and_readback(action_world):
 s,manager,_=action_world; proposal=manager.propose(draft(),'request')
 before=Receipts(s).get(proposal['id']);assert before['status']=='WAITING' and not before['verification']
 run(manager,proposal)
 receipt=Receipts(s).get(proposal['id'])
 assert receipt['status']=='VERIFIED' and receipt['verification']['verified']
 assert receipt['transport']=='mcp-memory' and receipt['tool']=='action_task_update'
 assert receipt['approval'] and receipt['outcomes'] and receipt['execution']['id']=='job'


def test_failed_and_unknown_never_verified(action_world):
 s,manager,provider=action_world
 provider.mode='reject'; proposal=manager.propose(draft('slack_post'),'request');run(manager,proposal)
 r=Receipts(s).get(proposal['id']);assert r['status']=='FAILED' and r['error'] and not r['verification']
 # Defensive rendering of inconsistent legacy records.
 s.repo.db.execute("MATCH (a:Action {id:$id}) SET a.status='VERIFIED'",{'id':proposal['id']})
 assert Receipts(s).get(proposal['id'])['status']=='UNKNOWN'


def test_cross_session_actual_retrieval_and_citation(world,monkeypatch):
 from backend.orbit.agents import Collaboration
 from backend.orbit.chat import ChatRequest
 from backend.orbit import llm
 s,_=world
 s.upsert_node('bot',NodeUpsert(type='Bot',properties={'name':'Coordinator'}))
 for session in ('old-session','new-session'):
  s.create_conversation(ConversationCreate(id=session,bot_id='bot',title=session))
 s.create_message('old-session',MessageCreate(id='old-message',role='user',content='Transport booking decision'))
 s.repo.upsert_node('prior-decision',EntityType.Decision,{'name':'Transport booking decision','summary':'Transport was required','status':'PROPOSED'})
 s.repo.upsert_edge('prior-decision',RelationType.MENTIONED_IN,'old-message',{})
 s.create_message('new-session',MessageCreate(id='new-message',role='user',content='Review transport booking decision'))
 def provider(system,payload,schema=None):
  if 'roles' in payload:return {'assignments':[{'agent':'planner','task':'Review transport booking decision'}]}
  assert 'prior-decision' in [n['id'] for n in payload['graph']['nodes']]
  return {'summary':'Review earlier transport decision before changing arrangements','evidence_ids':['prior-decision'],'proposals':[]}
 monkeypatch.setattr(llm,'generate',provider)
 result=Collaboration(s).run(ChatRequest(id='new-message',bot_id='coordinator',name='Coordinator',conversation_id='new-session',content='Review transport booking decision'))
 finding=result['findings'][0]['id']
 # A fresh service reconstructs the explanation from persisted graph records.
 r=Receipts(GraphService(GraphRepository(s.repo.db))).get(finding)
 previous=next(p for p in r['previous'] if p['id']=='prior-decision')
 assert previous['retrieval']['conversation_id']=='new-session'
 assert previous['retrieval']['at'] and previous['relationship']['type']=='SUPPORTED_BY'
 assert r['agents'][0]['name']=='planner'


def test_legacy_receipt_does_not_invent_history(world):
 s,_=world;s.repo.upsert_node('legacy',EntityType.Decision,{'name':'Earlier decision','summary':'Await confirmation','status':'WAIT'})
 r=Receipts(s).get('legacy')
 assert r['status']=='WAITING' and r['paths']==[] and r['previous']==[]
 assert r['evidence_basis']=='Current graph; historical snapshot unavailable'


def test_all_action_states_reflect_persisted_status(action_world):
 s,manager,_=action_world; proposal=manager.propose(draft(),'request')
 for stored,shown in [('AWAITING_APPROVAL','WAITING'),('APPROVED','APPROVED'),('EXECUTING','EXECUTING'),('UNKNOWN','UNKNOWN'),('FAILED','FAILED'),('REJECTED','REJECTED')]:
  s.repo.db.execute('MATCH (a:Action {id:$id}) SET a.status=$status',{'id':proposal['id'],'status':stored})
  assert Receipts(s).get(proposal['id'])['status']==shown
