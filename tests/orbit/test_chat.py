import os
import pytest
from backend.orbit.chat import ChatEngine,ChatRequest
from backend.orbit.service import GraphService
from backend.orbit.repository import GraphRepository
from backend.orbit.database import Database,GraphError
from backend.orbit import llm

def test_missing_key(monkeypatch):
 monkeypatch.delenv('GEMINI_API_KEY',raising=False);monkeypatch.delenv('GOOGLE_API_KEY',raising=False)
 with pytest.raises(GraphError) as e:llm.generate('hello',{})
 assert e.value.code=='llm_unconfigured'

def test_live_chat_memory(settings):
 db=Database(settings);db.initialize();s=GraphService(GraphRepository(db));engine=ChatEngine(s)
 def turn(i,content,bot='test-planner',conversation='chat:test-one'):
  return engine.turn(ChatRequest(id='turn:'+str(i),bot_id=bot,name=bot,instructions='Be concise and helpful.',conversation_id=conversation,content=content))
 try:
  first=turn(1,'Mira is my sister. She might take my father Arun to the clinic tomorrow.')
  assert first['assistant']['properties']['content']
  claims=s.repo.search_nodes(kind=__import__('backend.orbit.models',fromlist=['EntityType']).EntityType.Claim,limit=100)['items']
  assert any(c['properties']['status']=='PENDING' for c in claims)
  assert any(c['properties']['status']=='CONFIRMED' for c in claims)
  people=s.repo.search_nodes('Mira')['items'];mira=[n for n in people if n['type']=='Person'];assert len(mira)==1
  repeat=turn(1,'Mira is my sister. She might take my father Arun to the clinic tomorrow.')
  assert repeat['assistant']['id']==first['assistant']['id']
  second=turn(2,"Mira confirmed she will take Arun to the clinic tomorrow.")
  assert second['assistant']['properties']['content']
  assert len([n for n in s.repo.search_nodes('Mira')['items'] if n['type']=='Person'])==1
  claims=s.repo.search_nodes(kind=__import__('backend.orbit.models',fromlist=['EntityType']).EntityType.Claim,limit=100)['items']
  assert any(c['properties']['status']=='SUPERSEDED' for c in claims)
  # A new engine and bot have no in-process conversational state.
  engine=ChatEngine(GraphService(GraphRepository(db)))
  count_before=len(claims)
  recalled=turn(3,'Who is Mira and what did she confirm about Arun?',bot='test-research',conversation='chat:test-two')
  assert len(s.repo.search_nodes(kind=__import__('backend.orbit.models',fromlist=['EntityType']).EntityType.Claim,limit=100)['items'])==count_before
  reply=recalled['assistant']['properties']['content'].lower();assert 'mira' in reply and ('clinic' in reply or 'take' in reply)
  hypothetical=turn(4,'Hypothetically, what if Mira were a pilot? This is not a fact.',conversation='chat:test-three')
  assert hypothetical['assistant']['properties']['content']
  assert len(s.repo.search_nodes(kind=__import__('backend.orbit.models',fromlist=['EntityType']).EntityType.Claim,limit=100)['items'])==count_before
  from backend.orbit.models import TraversalRequest
  graph=s.repo.traverse(TraversalRequest(root_id=mira[0]['id'],hops=2,limit=100))
  assert any(n['type']=='Claim' for n in graph['nodes']);assert graph['edges']
 finally:db.graph.delete();db.close()

@pytest.mark.parametrize('status,expected',[(429,429),(503,502),(401,502)])
def test_provider_errors(monkeypatch,status,expected):
 import httpx
 monkeypatch.setenv('GEMINI_API_KEY','test-only-not-real')
 monkeypatch.setattr(httpx,'post',lambda *a,**kw:httpx.Response(status))
 with pytest.raises(GraphError) as error:llm.generate('test',{})
 assert error.value.status==expected

def test_provider_timeout(monkeypatch):
 import httpx
 monkeypatch.setenv('GEMINI_API_KEY','test-only-not-real')
 def timeout(*a,**kw):raise httpx.ReadTimeout('test timeout')
 monkeypatch.setattr(httpx,'post',timeout)
 with pytest.raises(GraphError) as error:llm.generate('test',{})
 assert error.value.code=='llm_timeout'
