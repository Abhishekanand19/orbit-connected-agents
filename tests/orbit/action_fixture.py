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
    db.close()
    uvicorn.run(create_app(settings),host='127.0.0.1',port=8002)
