"""Real FalkorDB dynamic decisions; no LLM responses used by the engine."""
import pytest
from backend.orbit.models import *
from backend.orbit.database import Database
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.intelligence import ImpactEngine,ImpactRequest,ImpactResult

@pytest.fixture
def world(settings):
 db=Database(settings);db.initialize();s=GraphService(GraphRepository(db))
 for id,kind,name in [('appointment','Event','Hospital appointment'),('deployment','Task','Software deployment'),('transport','Booking','Transport booking'),('aarav','Person','Aarav'),('priya','Person','Priya'),('unrelated','Task','Unrelated task')]:
  props={'name':name}
  if id in ('appointment','deployment'):props.update(starts_at='2026-10-20T10:00:00Z',ends_at='2026-10-20T11:00:00Z')
  s.upsert_node(id,NodeUpsert(type=kind,properties=props))
 s.upsert_node('source',NodeUpsert(type='Source',properties={'name':'Explicit verified test evidence','kind':'MANUAL','observed_at':'2026-10-16T10:00:00Z'}))
 s.create_claim(ClaimCreate(id='verified',text='Verified fixture constraints',status='CONFIRMED',source_id='source',subject_ids=['appointment','deployment','transport','priya','aarav'],verification_source_id='source',observed_at='2026-10-16T10:00:00Z'))
 def edge(a,t,b,status='CONFIRMED'):
  return s.upsert_relationship(RelationshipUpsert(source=a,type=t,target=b,properties={'evidence_state':status,'evidence_id':'verified'}))
 edge('appointment','ASSIGNED_TO','aarav');edge('deployment','ASSIGNED_TO','aarav')
 edge('transport','DEPENDS_ON','appointment');edge('priya','AVAILABLE_FOR','appointment')
 yield s,edge
 db.graph.delete();db.close()

def request():return ImpactRequest(root_id='appointment',trigger_claim_id='verified',scope_ids=['transport','deployment','priya','unrelated'])

def test_dynamic_availability_disruption_unrelated_and_receipt(world):
 s,edge=world;engine=ImpactEngine(s)
 a=engine.analyze(request());assert a.state=='ACT'
 assert any(x.entity_id=='priya' and x.state=='ACT' for x in a.alternatives)
 assert any(x.entity_id=='aarav' and 'deployment' in x.constraint_ids for x in a.alternatives)
 assert 'unrelated' in a.unchanged_ids
 transport=next(p for p in a.affected if p.entity_id=='transport')
 assert transport.node_ids==['appointment','transport']
 rel=s.repo.get_edge(transport.edge_ids[0]);assert rel['source']=='transport' and rel['target']=='appointment' and rel['type']=='DEPENDS_ON'
 edge('priya','AVAILABLE_FOR','appointment','REFUTED')
 b=engine.analyze(request());assert b.state=='CONFLICT';assert not b.proposed_changes
 s.create_claim(ClaimCreate(id='rumor',text='Possible disruption',status='UNVERIFIED',source_id='source',subject_ids=['appointment'],observed_at='2026-10-16T11:00:00Z'))
 c=engine.analyze(request().model_copy(update={'trigger_claim_id':'rumor'}));assert c.state=='WAIT';assert not c.proposed_changes
 stored=s.require(a.id);assert ImpactResult.model_validate_json(stored['properties']['analysis'])==a
 assert s.require('appointment')['properties']['starts_at'].replace('Z','+00:00')=='2026-10-20T10:00:00+00:00'

def test_typed_direction_cycles_and_refuted_edges(world):
 s,edge=world
 edge('transport','RELATED_TO','unrelated');edge('transport','AFFECTS','deployment')
 edge('deployment','AFFECTS','transport')
 g=ImpactEngine(s).analyze(request());ids=[p.entity_id for p in g.affected]
 assert 'deployment' in ids and len(ids)==len(set(ids));assert 'unrelated' not in ids
 edge('transport','AFFECTS','deployment','REFUTED')
 assert 'deployment' not in [p.entity_id for p in ImpactEngine(s).analyze(request()).affected]

def test_unverified_dependency_and_cancelled_prerequisite(world):
 s,edge=world;edge('transport','DEPENDS_ON','appointment','UNVERIFIED')
 assert ImpactEngine(s).analyze(request()).state=='WAIT'
 edge('transport','DEPENDS_ON','appointment')
 s.upsert_node('prereq',NodeUpsert(type='Task',properties={'name':'Required prerequisite','status':'CANCELLED'}))
 edge('appointment','DEPENDS_ON','prereq')
 result=ImpactEngine(s).analyze(request());assert result.state=='CONFLICT' and 'prereq' in result.constraints

def test_typed_api_and_no_change(world):
 from fastapi.testclient import TestClient
 from backend.orbit.api import create_app
 s,edge=world
 with TestClient(create_app(s.repo.db.settings)) as client:
  response=client.post('/api/graph/impact',json=request().model_dump(mode='json'))
  assert response.status_code==200
  receipt=response.json();assert client.get('/api/graph/impact/'+receipt['id']).json()==receipt
  assert client.post('/api/graph/impact',json={**request().model_dump(mode='json'),'hops':9}).status_code==422
 edge('deployment','ASSIGNED_TO','aarav','REFUTED')
 assert ImpactEngine(s).analyze(request()).state=='NO_CHANGE'

def test_coordinator_persists_engine_constraints_for_specialist(world,monkeypatch):
 from backend.orbit.agents import Collaboration
 from backend.orbit.chat import ChatRequest
 from backend.orbit import llm
 s,edge=world
 s.upsert_node('chatbot:coordinator',NodeUpsert(type='Bot',properties={'name':'Coordinator'}))
 s.create_conversation(ConversationCreate(id='session',bot_id='chatbot:coordinator',title='Impact'))
 s.create_message('session',MessageCreate(id='message',role='user',content='The appointment might change.'))
 s.create_claim(ClaimCreate(id='uncertain',text='Appointment might change',status='PENDING',message_id='message',source_id='source',subject_ids=['appointment'],observed_at='2026-10-16T10:00:00Z'))
 def provider(system,payload,schema=None):
  assert payload['deterministic_impacts'][0]['state']=='WAIT'
  if 'roles' in payload:return {'assignments':[{'agent':'planner','task':'Check appointment impact'}]}
  return {'summary':'Wait for confirmation','evidence_ids':['appointment'],'proposals':[],'draft':None,'handoff':None}
 monkeypatch.setattr(llm,'generate',provider)
 result=Collaboration(s).run(ChatRequest(id='message',bot_id='coordinator',name='Coordinator',conversation_id='session',content='The appointment might change.'))
 assert result['impacts'][0]['state']=='WAIT'
 assert result['activity'][0]['properties']['status']=='DONE'
 assert Collaboration(s).impacts('message')==result['impacts']
