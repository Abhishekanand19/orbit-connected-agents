"""Real FalkorDB orchestration tests. Scripted-provider tests are explicitly labeled."""
import pytest
from backend.orbit.agents import Collaboration
from backend.orbit.chat import ChatRequest
from backend.orbit.models import *
from backend.orbit.database import Database,GraphError
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit import llm

@pytest.fixture
def agent_state(settings):
 db=Database(settings);db.initialize();s=GraphService(GraphRepository(db))
 s.upsert_node('chatbot:coordinator',NodeUpsert(type='Bot',properties={'name':'Coordinator'}))
 s.create_conversation(ConversationCreate(id='session:agents',bot_id='chatbot:coordinator',title='Agents'))
 s.create_message('session:agents',MessageCreate(id='request:agents',role='user',content='Review the workshop schedule and prepare coordination.'))
 s.upsert_node('workshop',NodeUpsert(type='Event',properties={'name':'Workshop','description':'Time is unconfirmed'}))
 req=ChatRequest(id='request:agents',bot_id='coordinator',name='Coordinator',conversation_id='session:agents',content='Check the workshop evidence, schedule and tasks, then draft a coordination message.')
 yield s,req
 db.graph.delete();db.close()

def output(text,handoff=None):return {'summary':text,'evidence_ids':['workshop'],'proposals':[],'draft':None,'handoff':handoff}

def test_scripted_shared_handoffs_failure_and_bounds(agent_state,monkeypatch):
 s,req=agent_state;calls=[]
 def provider(system,payload,schema=None):
  calls.append(payload)
  if 'roles' in payload:return {'assignments':[{'agent':'research','task':'Check workshop evidence'}]}
  task=payload['task']
  if task=='Check workshop evidence':return output('Workshop is unconfirmed',{'agent':'planner','task':'Plan workshop'})
  if task=='Plan workshop':
   assert any('unconfirmed' in n['properties']['description'] for n in payload['shared_findings'])
   return output('Keep the workshop tentative',{'agent':'tasks','task':'Review tasks'})
  if task=='Review tasks':return output('No existing assigned task found',{'agent':'communication','task':'Draft workshop message'})
  assert len(payload['shared_findings'])==3
  raise GraphError(503,'unavailable','Draft service unavailable')
 monkeypatch.setattr(llm,'generate',provider)
 result=Collaboration(s).run(req)
 assert len(calls)==5;assert len(result['findings'])==3
 assert [r['properties']['status'] for r in result['activity']]==['DONE','DONE','DONE','FAILED']
 assert all(r['properties'].get('completed_at') for r in result['activity'])
 assert len(Collaboration(s).run(req)['activity'])==4;assert len(calls)==5
 assert len(Collaboration(s).shared(req.id))==3
 edges=s.repo.db.execute("MATCH (:Task)-[r:DEPENDS_ON]->(:Task) RETURN count(r)",read=True);assert edges[0][0]==3

def test_scripted_downstream_reads_changed_finding(agent_state,monkeypatch):
 s,req=agent_state
 def provider(system,payload,schema=None):
  if 'roles' in payload:return {'assignments':[{'agent':'research','task':'Research workshop'},{'agent':'communication','task':'Draft workshop'}]}
  if payload['task']=='Research workshop':return output('Initial finding')
  shared=payload['shared_findings'];return {**output(shared[0]['properties']['description']),'draft':shared[0]['properties']['description']}
 monkeypatch.setattr(llm,'generate',provider)
 original=Collaboration.shared
 def changed(self,id):
  rows=original(self,id)
  if len(rows)==1:
   self.s.repo.db.execute('MATCH (f:Source {id:$id}) SET f.description=$text',{'id':rows[0]['id'],'text':'Updated graph finding: time requires verification'})
  return original(self,id)
 monkeypatch.setattr(Collaboration,'shared',changed)
 result=Collaboration(s).run(req)
 assert result['findings'][1]['properties']['draft']=='Updated graph finding: time requires verification'

def test_scripted_no_unnecessary_agents(agent_state,monkeypatch):
 s,req=agent_state;count=[]
 monkeypatch.setattr(llm,'generate',lambda *a:count.append(1) or {'assignments':[]})
 assert Collaboration(s).run(req)['activity']==[];assert len(count)==1

def test_live_dynamic_selection(agent_state):
 s,req=agent_state
 req.content='Only draft a short unsent message asking whether the workshop time is confirmed. Do not do any scheduling, research or task planning.'
 result=Collaboration(s).run(req)
 assert [r['properties']['owner'] for r in result['activity']]==['communication']
 assert result['activity'][0]['properties']['status']=='DONE'
 assert result['findings'][0]['properties']['draft']

def test_live_full_collaboration(agent_state):
 s,req=agent_state
 req.content='Please have Research check the workshop evidence, Planner assess schedule impacts, Task Manager inspect responsibilities, and Communication draft an unsent update. Coordinate their results.'
 result=Collaboration(s).run(req)
 assert {r['properties']['owner'] for r in result['activity']}=={'research','planner','tasks','communication'}
 assert all(r['properties']['status']=='DONE' for r in result['activity'])
 assert len(result['findings'])==4
 from backend.orbit.memory import retrieve
 # New conversation, same shared graph, no copying agent prompts/history.
 s.create_conversation(ConversationCreate(id='session:later',bot_id='chatbot:coordinator',title='Later'))
 graph=retrieve(s,'workshop','session:later')
 assert any(n['properties'].get('record_kind')=='AGENT_FINDING' for n in graph['nodes'])


def test_custom_bot_does_not_orchestrate(agent_state,monkeypatch):
 from backend.orbit.chat import ChatEngine
 from backend.orbit import extraction
 s,req=agent_state
 req.bot_id='custom-bot';req.id='custom:message';req.conversation_id='custom:session'
 monkeypatch.setattr(extraction,'extract',lambda *a:extraction.Extraction(entities=[],facts=[]))
 monkeypatch.setattr(llm,'generate',lambda *a:'A direct custom bot reply.')
 def forbidden(*a):raise AssertionError('Custom bot must not delegate')
 monkeypatch.setattr(Collaboration,'run',forbidden)
 result=ChatEngine(s).turn(req)
 assert result['activity']==[]
 assert result['assistant']['properties']['content']=='A direct custom bot reply.'
