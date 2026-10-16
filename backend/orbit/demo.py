"""Isolated simulated inputs. Decisions and actions come from existing engines.
Run: python -m backend.orbit.demo --reset --serve
Uses orbit_demo_family only, backend port 8001; stop the existing backend first.
"""
import argparse
import json
from fastapi import Request
from .models import NodeUpsert,ConversationCreate,MessageCreate,ClaimCreate,RelationshipUpsert
from .database import Database,GraphError
from .repository import GraphRepository,node_view
from .service import GraphService
from .config import Settings
from .intelligence import ImpactEngine,ImpactRequest
from .agents import Collaboration
from .chat import ChatRequest

GRAPH='orbit_demo_family'
PREFIX='family:'
DAY='2026-10-20'
def at(time):return DAY+'T'+time+':00+05:30'

# Inputs only: no decisions, proposals, provider acknowledgements or tool traces.
EVENTS=[
 {'id':'rumor','session':1,'status':'UNVERIFIED','source':'Family message (simulated)','text':'A family message claims the hospital is closed. Check evidence; do not cancel anything.'},
 {'id':'roads','session':1,'status':'PENDING','source':'Cab operator notice (simulated)','text':'Transport warns of protest-related road restrictions. Travel duration needs confirmation; this is not a cancellation.'},
 {'id':'pending','session':1,'status':'PENDING','source':'Hospital email (simulated, not Gmail)','text':'The hospital says morning appointments may move. No new time is confirmed.'},
 {'id':'confirmed','session':1,'status':'CONFIRMED','source':'Hospital confirmation (simulated, not Gmail)','text':'The hospital confirms the follow-up at 1:45 PM, ending at 3 PM. Recheck escort, cab timing, work conflict and physiotherapy; request missing confirmations.','changes':{'starts_at':at('13:45'),'ends_at':at('15:00')}},
 {'id':'available','session':1,'status':'CONFIRMED','source':'Priya and transport confirmations (simulated)','text':'Priya confirms she can escort Ramesh for the full afternoon. Transport confirms the proposed travel window is feasible. Physiotherapy remains at 4 PM; evaluate whether it needs changing. Propose exact internal task changes for approval only.','availability':'CONFIRMED'},
 {'id':'unavailable','session':1,'status':'CONFIRMED','source':'Priya correction (simulated)','text':'Priya is now unavailable. Rerun the same analysis; do not invent another available escort.','availability':'REFUTED'},
 {'id':'video','session':2,'status':'CONFIRMED','source':'Hospital video confirmation (simulated, not Gmail)','text':'The hospital confirms the follow-up can happen by video at the same time. Retrieve earlier cab decisions and verified outcomes from saved memory. Review only necessary changes to internal transport tasks; preserve completed physiotherapy and Aarav’s work. No medical decisions.','changes':{'location':'video'}}
]

class Demo:
 def __init__(self,s):
  self.s=s;self.db=s.repo.db
  if self.db.settings.graph!=GRAPH and not self.db.settings.graph.startswith('orbit_test_demo_'):
   raise GraphError(403,'demo_isolation','Demo controls require the isolated demo graph.')
 def seed(self):
  if self.db.execute('MATCH (d:OrbitDemo {id:$id}) RETURN d.id',{'id':GRAPH},read=True):return self.state()
  def node(id,type,name,**props):self.s.upsert_node(PREFIX+id,NodeUpsert(type=type,properties={'name':name,**props}))
  node('aarav','Person','Aarav',description='Software engineer coordinating his father’s care')
  node('priya','Person','Priya',description='Aarav’s sister; availability requires confirmation')
  node('ramesh','Person','Ramesh',description='Recovering from surgery; follow clinician instructions only')
  node('appointment','Event','Ramesh hospital follow-up',starts_at=at('11:00'),ends_at=at('12:00'),location='hospital')
  node('cab','Task','Internal demo cab arrangement',starts_at=at('09:45'),ends_at=at('10:45'),status='OPEN',description='Simulated booking record only. No third-party cab booking exists.')
  node('booking','Booking','Cab booking — internal demo only',starts_at=at('09:45'),ends_at=at('10:45'),status='CONFIRMED',reference='SIMULATED-ONLY')
  node('physio','Task','Home physiotherapy arrangement',starts_at=at('16:00'),ends_at=at('17:00'),status='OPEN')
  node('deployment','Task','Aarav software deployment',starts_at=at('14:30'),ends_at=at('15:30'),status='OPEN')
  self.s.upsert_node('chatbot:coordinator',NodeUpsert(type='Bot',properties={'name':'Orbit Coordinator'}))
  node('baseline-source','Source','Simulated demo baseline',kind='MANUAL',observed_at=at('08:00'))
  self.s.create_claim(ClaimCreate(id=PREFIX+'baseline',text='Simulated established commitments and dependencies',status='CONFIRMED',source_id=PREFIX+'baseline-source',verification_source_id=PREFIX+'baseline-source',subject_ids=[PREFIX+x for x in ['appointment','cab','physio','deployment']],observed_at=at('08:00')))
  for a,t,b in [('cab','DEPENDS_ON','appointment'),('booking','DEPENDS_ON','cab'),('physio','DEPENDS_ON','cab'),('appointment','ASSIGNED_TO','aarav'),('deployment','ASSIGNED_TO','aarav'),('ramesh','PARTICIPATES_IN','appointment')]:
   props={'evidence_state':'CONFIRMED','evidence_id':PREFIX+'baseline'}
   if a=='cab' and b=='appointment':props['required_location']='hospital'
   self.s.upsert_relationship(RelationshipUpsert(source=PREFIX+a,type=t,target=PREFIX+b,properties=props))
  self.s.upsert_relationship(RelationshipUpsert(source=PREFIX+'priya',type='AVAILABLE_FOR',target=PREFIX+'appointment',properties={'evidence_state':'PENDING','evidence_id':PREFIX+'baseline'}))
  self.db.execute('CREATE (:OrbitDemo {id:$id})',{'id':GRAPH})
  return self.state()
 def state(self):
  rows=self.db.execute('MATCH (e:OrbitDemoEvent) RETURN e.event,e.decision,e.message,e.conversation ORDER BY e.sequence',read=True)
  return {'enabled':True,'graph':self.db.settings.graph,'simulated':True,'events':EVENTS,'received':[{'event':r[0],'decision_id':r[1],'message_id':r[2],'conversation_id':r[3]} for r in rows]}
 def inject(self,key):
  event=next((e for e in EVENTS if e['id']==key),None)
  if not event:raise GraphError(404,'demo_event','Unknown demo input.')
  self.seed();existing=next((r for r in self.state()['received'] if r['event']==key),None)
  if existing:return existing
  earlier={r['event'] for r in self.state()['received']}
  required={'roads':'rumor','pending':'roads','confirmed':'pending','available':'confirmed','unavailable':'available','video':'available'}.get(key)
  if required and required not in earlier:raise GraphError(409,'demo_order','Introduce '+required+' first.')
  conversation=PREFIX+'session:'+str(event['session']);message=PREFIX+'message:'+key
  self.s.create_conversation(ConversationCreate(id=conversation,bot_id='chatbot:coordinator',title='Family domino demo — session '+str(event['session'])))
  self.s.create_message(conversation,MessageCreate(id=message,role='user',content='[SIMULATED INPUT] '+event['text']))
  source=PREFIX+'source:'+key;claim=PREFIX+'claim:'+key
  self.s.upsert_node(source,NodeUpsert(type='Source',properties={'name':event['source'],'kind':'MANUAL','observed_at':at('08:30')}))
  self.s.create_claim(ClaimCreate(id=claim,text=event['text'],status=event['status'],source_id=source,message_id=message,subject_ids=[PREFIX+'appointment'],verification_source_id=source if event['status']=='CONFIRMED' else None,observed_at=at('08:30')))
  if event.get('changes'):self.s.upsert_node(PREFIX+'appointment',NodeUpsert(type='Event',properties=event['changes']))
  if event.get('availability'):self.s.upsert_relationship(RelationshipUpsert(source=PREFIX+'priya',type='AVAILABLE_FOR',target=PREFIX+'appointment',properties={'evidence_state':event['availability'],'evidence_id':claim}))
  decision=ImpactEngine(self.s).analyze(ImpactRequest(root_id=PREFIX+'appointment',trigger_claim_id=claim,hops=4,scope_ids=[PREFIX+x for x in ['cab','booking','physio','deployment']]))
  from .models import RelationType
  self.s.repo.upsert_edge(decision.id,RelationType.MENTIONED_IN,message,{})
  self.db.execute('CREATE (:OrbitDemoEvent {event:$event,decision:$decision,message:$message,conversation:$conversation,sequence:$sequence})',{'event':key,'decision':decision.id,'message':message,'conversation':conversation,'sequence':len(earlier)})
  return {'event':key,'decision_id':decision.id,'message_id':message,'conversation_id':conversation}
 def analyze(self,key):
  saved=next((r for r in self.state()['received'] if r['event']==key),None)
  if not saved:raise GraphError(409,'demo_input_required','Introduce the event first.')
  content=self.s.require(saved['message_id'])['properties']['content']
  return Collaboration(self.s).run(ChatRequest(id=saved['message_id'],bot_id='coordinator',name='Orbit Coordinator',conversation_id=saved['conversation_id'],content=content))


def mount_demo(app):
 @app.get('/api/demo')
 def state(request:Request):
  if request.app.state.service.repo.db.settings.graph!=GRAPH and not request.app.state.service.repo.db.settings.graph.startswith('orbit_test_demo_'):return {'enabled':False}
  return Demo(request.app.state.service).state()
 @app.post('/api/demo/{event}')
 def inject(event:str,request:Request):return Demo(request.app.state.service).inject(event)
 @app.post('/api/demo/{event}/analyze')
 def analyze(event:str,request:Request):return Demo(request.app.state.service).analyze(event)


def reset_demo(db):
 # The caller must explicitly select the reserved dataset, never the default graph.
 Demo(GraphService(GraphRepository(db)))
 settings=db.settings
 db.graph.delete();db.close()
 fresh=Database(settings);fresh.initialize()
 return fresh

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reset',action='store_true');parser.add_argument('--serve',action='store_true');parser.add_argument('--event',choices=[e['id'] for e in EVENTS]);args=parser.parse_args()
 settings=Settings.from_env().model_copy(update={'graph':GRAPH});db=Database(settings);db.initialize()
 if args.reset:
  # Exact, constant graph name; never selected from personal runtime configuration.
  assert db.settings.graph==GRAPH
  db=reset_demo(db)
 demo=Demo(GraphService(GraphRepository(db)));demo.seed()
 if args.event:print(json.dumps(demo.inject(args.event)))
 else:print('Isolated simulated dataset ready: '+GRAPH)
 db.close()
 if args.serve:
  import uvicorn
  from .api import create_app
  uvicorn.run(create_app(settings),host='127.0.0.1',port=8001)
if __name__=='__main__':main()
