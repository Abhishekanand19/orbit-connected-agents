"""Isolated approval UI fixture. Only local test tasks; no external calls or LLM."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uvicorn
from backend.orbit.api import create_app
from backend.orbit.config import Settings
from backend.orbit.database import Database
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.models import NodeUpsert,ConversationCreate,MessageCreate
from backend.orbit.action_models import ActionDraft
from backend.orbit.actions import Actions

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--graph',required=True);args=parser.parse_args()
    if not args.graph.startswith('orbit_test_visuals_'):parser.error('Use an isolated browser test graph.')
    settings=Settings.from_env().model_copy(update={'graph':args.graph,'allowed_origins':['http://127.0.0.1:5174']})
    db=Database(settings);db.initialize();s=GraphService(GraphRepository(db))
    s.upsert_node('chatbot:coordinator',NodeUpsert(type='Bot',properties={'name':'Coordinator'}))
    s.create_conversation(ConversationCreate(id='approval:session',bot_id='chatbot:coordinator',title='Review'))
    s.create_message('approval:session',MessageCreate(id='approval:request',role='user',content='Please prepare these test task changes for review.'))
    for id,name in [('approve-task','Prepare the launch notes'),('reject-task','Review the checklist')]:
        s.upsert_node(id,NodeUpsert(type='Task',properties={'name':name,'status':'OPEN'}))
        Actions(s).propose(ActionDraft(kind='task_update',payload={'task_id':id,'changes':{'status':'DONE'}},
            reason='Mark '+name+' complete after your review.',affected_ids=[id],evidence_ids=['approval:request']),'approval:request')
    from backend.orbit.models import ClaimCreate,RelationshipUpsert
    from backend.orbit.intelligence import ImpactEngine,ImpactRequest
    s.upsert_node('receipt-event',NodeUpsert(type='Event',properties={'name':'Planning appointment'}))
    s.upsert_node('receipt-booking',NodeUpsert(type='Booking',properties={'name':'Connected transport'}))
    s.upsert_node('receipt-source',NodeUpsert(type='Source',properties={'name':'Confirmed schedule','kind':'MANUAL','observed_at':'2026-10-16T10:00:00Z'}))
    s.create_claim(ClaimCreate(id='receipt-claim',text='The planning appointment changed',status='CONFIRMED',source_id='receipt-source',verification_source_id='receipt-source',subject_ids=['receipt-event'],observed_at='2026-10-16T10:00:00Z'))
    s.upsert_relationship(RelationshipUpsert(source='receipt-booking',type='DEPENDS_ON',target='receipt-event',properties={'evidence_state':'CONFIRMED','evidence_id':'receipt-claim'}))
    ImpactEngine(s).analyze(ImpactRequest(root_id='receipt-event',trigger_claim_id='receipt-claim'))
    db.close()
    uvicorn.run(create_app(settings),host='127.0.0.1',port=8002)
