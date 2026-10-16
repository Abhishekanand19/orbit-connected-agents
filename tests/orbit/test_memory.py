"""Real FalkorDB lifecycle tests; extraction inputs are deterministic, no mocked provider claims."""
import json,subprocess,sys
import pytest
from backend.orbit.models import *
from backend.orbit.database import Database,GraphError
from backend.orbit.service import GraphService
from backend.orbit.repository import GraphRepository
from backend.orbit.extraction import Extraction,apply,stable
from backend.orbit.memory import retrieve
from backend.orbit.records import MemoryRecord,record

@pytest.fixture
def memory(settings):
 db=Database(settings);db.initialize();s=GraphService(GraphRepository(db))
 for bot in ['planner','tasks']:
  s.upsert_node(bot,NodeUpsert(type='Bot',properties={'name':bot}))
  s.create_conversation(ConversationCreate(id='session:'+bot,bot_id=bot,title=bot))
 yield s,settings
 db.graph.delete();db.close()

def write(s,id,text,status='CONFIRMED',supersedes=None,distinct=False):
 m=s.create_message('session:planner',MessageCreate(id=id,role='user',content=text))
 plan=Extraction.model_validate({'entities':[{'key':'p','name':'Nora','type':'Person','distinct':distinct}], 'facts':[{'text':text,'quote':text,'subjects':['p'],'status':status,'supersedes_id':supersedes}]})
 return apply(s,plan,m,'2026-10-16T10:00:00+00:00')

def test_restart_shared_memory_and_duplicates(memory):
 s,settings=memory;write(s,'m:1','Nora prefers quiet morning appointments.')
 before=s.repo.db.execute('MATCH (n) RETURN count(n)',read=True)
 write(s,'m:1','Nora prefers quiet morning appointments.')
 assert s.repo.db.execute('MATCH (n) RETURN count(n)',read=True)==before
 for i in range(20):s.create_message('session:planner',MessageCreate(id=f'filler:{i}',role='user',content='Unrelated note'))
 # New backend interpreter, separate from this process and its client state.
 code="""import json,sys
from backend.orbit.config import Settings
from backend.orbit.database import Database
from backend.orbit.service import GraphService
from backend.orbit.repository import GraphRepository
from backend.orbit.memory import retrieve
db=Database(Settings.model_validate(json.loads(sys.argv[1])));db.initialize()
print(json.dumps(retrieve(GraphService(GraphRepository(db)),'quiet appointments','session:tasks')))
db.close()
"""
 graph=json.loads(subprocess.check_output([sys.executable,'-c',code,settings.model_dump_json()],text=True))
 assert any('quiet morning' in n['properties'].get('text','') for n in graph['nodes'])
 assert {n['id'] for n in graph['nodes'] if n['type']=='Claim'}=={n['id'] for n in retrieve(s,'quiet appointments','session:tasks')['nodes'] if n['type']=='Claim'}

def test_correction_weak_evidence_and_distinct_people(memory):
 s,_=memory;write(s,'m:1','Nora confirmed the appointment.')
 old=stable('m:1:claim:0')
 write(s,'m:2','Nora might cancel the appointment.','UNVERIFIED',old)
 assert s.require(old)['properties']['status']=='CONFIRMED'
 write(s,'m:3','Nora cancelled the appointment.','CONFIRMED',old)
 assert s.require(old)['properties']['status']=='SUPERSEDED'
 g=retrieve(s,'appointment','session:tasks');claims=[n for n in g['nodes'] if n['type']=='Claim']
 assert claims[0]['properties']['status']!='SUPERSEDED'
 assert any(n['id']==old for n in claims)
 write(s,'m:4','Another Nora prefers evenings.',distinct=True)
 assert len([n for n in s.repo.search_nodes('Nora')['items'] if n['type']=='Person'])==2

def test_record_chain_and_topology(memory):
 s,_=memory;person=write(s,'m:1','Nora reported moving the appointment.')[0]
 common=dict(summary='Appointment change',reason='User reported a timing conflict',observed_at='2026-10-16T10:00:00Z',conversation_id='session:planner',message_id='m:1',evidence_ids=[stable('m:1:claim:0')],affected_ids=[person])
 for id,kind,previous in [('decision:1','Decision',None),('action:1','Action','decision:1'),('outcome:1','Outcome','action:1')]:
  req=MemoryRecord(id=id,type=kind,previous_id=previous,**common);assert record(s,req)==record(s,req)
 graph=retrieve(s,'appointment','session:tasks')
 assert {'Decision','Action','Outcome'} <= {n['type'] for n in graph['nodes']}
 s.upsert_node('other',NodeUpsert(type='Task',properties={'name':'Unrelated task'}))
 edge=s.upsert_relationship(RelationshipUpsert(source=person,target='other',type='RELATED_TO'))
 graph=retrieve(s,'Nora','session:tasks');assert edge['id'] in {e['id'] for e in graph['edges']}
 s.delete_relationship(edge['id'])
 assert edge['id'] not in {e['id'] for e in retrieve(s,'Nora','session:tasks')['edges']}
