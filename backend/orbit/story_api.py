"""Opt-in isolated story workspaces. No reset/delete and no model calls."""
import re
import json
from uuid import uuid4
from datetime import datetime,timezone,timedelta
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .database import Database,GraphError
from .repository import GraphRepository
from .service import GraphService
from .models import ConversationCreate,NodeUpsert,StrictModel
from pydantic import StrictBool

class ChecklistUpdate(StrictModel):
    checked: StrictBool

def request_service(request):
    return getattr(request.state,'story_service',request.app.state.service)

def mount_story(app,settings):
    @app.middleware('http')
    async def workspace(request,call_next):
        key=request.headers.get('x-orbit-story')
        if not key:return await call_next(request)
        db=None
        try:
            if not re.fullmatch(r'[a-f0-9]{32}',key):raise GraphError(400,'story_workspace','Invalid demo workspace.')
            rows=await run_in_threadpool(request.app.state.service.repo.db.execute,'MATCH (w:OrbitStoryWorkspace {id:$id}) RETURN w.graph',{'id':key},read=True)
            if not rows:raise GraphError(404,'story_workspace','Demo workspace not found. Start a fresh demo.')
            if rows[0][0]!='orbit_story_'+key:raise GraphError(409,'story_workspace','Workspace identity mismatch.')
            db=Database(settings.model_copy(update={'graph':rows[0][0]}))
            await run_in_threadpool(db.initialize)
            request.state.story_service=GraphService(GraphRepository(db))
            return await call_next(request)
        except GraphError as e:return JSONResponse({'error':{'code':e.code,'message':e.message}},status_code=e.status)
        finally:
            if db:db.close()

    @app.post('/api/story/workspaces')
    def create(request:Request):
        key=uuid4().hex;graph='orbit_story_'+key
        db=Database(settings.model_copy(update={'graph':graph}))
        try:
            db.initialize()
            day=datetime.now(timezone(timedelta(hours=5,minutes=30))).date().isoformat()
            db.execute('CREATE (:OrbitStoryState {id:"story",revision:0,day:$day,slots:"{}"})',{'day':day})
            request.app.state.service.repo.db.execute('CREATE (:OrbitStoryWorkspace {id:$id,graph:$graph})',{'id':key,'graph':graph})
            return {'workspace_id':key,'graph':graph,'day':day,'mode':'deterministic','external_writes':False}
        finally:db.close()

    @app.get('/api/story/state')
    def state(request:Request,conversation_id:str|None=None):
        from .story import StoryEngine
        service=request_service(request)
        result=StoryEngine(service).state()
        if conversation_id is not None:
            rows=service.repo.db.execute('MATCH (t:OrbitStoryTurn) WHERE t.conversation=$id RETURN t.response',{'id':conversation_id},read=True)
            ids=set()
            for row in rows:
                turn=json.loads(row[0])
                ids.update(turn['entities']['added']+turn['entities']['updated'])
                ids.update(turn.get('recalled_ids',[]))
                edge_ids={e['id'] for e in turn.get('evidence_relationships',[])}
                for edge in turn['graph']['edges']:
                    if edge['id'] in edge_ids:ids.update([edge['source'],edge['target']])
                ids.update(p['id'] for p in turn.get('previous',[]))
            # Include the real execution outcomes of proposals in this conversation.
            for edge in result['graph']['edges']:
                if edge['source'] in ids and edge['type'] in ('PRODUCED','VERIFIED_BY'):ids.add(edge['target'])
            graph=result['graph'];graph['nodes']=[n for n in graph['nodes'] if n['id'] in ids]
            graph['edges']=[e for e in graph['edges'] if e['source'] in ids and e['target'] in ids]
            graph['paths']=[]
        return result

    @app.post('/api/story/conversations')
    def conversation(body:ConversationCreate,request:Request):
        service=request_service(request)
        if not service.repo.db.settings.graph.startswith('orbit_story_'):raise GraphError(403,'story_isolation','Story workspace required.')
        service.upsert_node('chatbot:coordinator',NodeUpsert(type='Bot',properties={'name':'Orbit Coordinator'}))
        return service.create_conversation(body)

    @app.get('/api/story/checklist')
    def get_checklist(request:Request):
        from .story import StoryEngine
        from .story_checklist import checklist
        service=request_service(request);StoryEngine(service)
        return {'tasks':checklist(service)}

    @app.post('/api/story/checklist/{key}')
    def update_checklist(key:str,body:ChecklistUpdate,request:Request):
        from .story import StoryEngine
        from .story_checklist import ITEMS,checklist
        from .models import EntityType as E
        service=request_service(request);StoryEngine(service)
        if key not in ITEMS:raise GraphError(404,'checklist_task','Unknown checklist task.')
        id='story:checklist:'+key;service.require(id,{E.Task})
        service.repo.upsert_node(id,E.Task,{'status':'DONE' if body.checked else 'OPEN','evidence_status':'USER_REPORTED' if body.checked else 'PENDING'})
        service.repo.db.execute('MATCH (s:OrbitStoryState {id:"story"}) SET s.revision=s.revision+1')
        return {'tasks':checklist(service),'external_writes':False}
