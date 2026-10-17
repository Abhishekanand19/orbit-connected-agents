"""Opt-in isolated story workspaces. No reset/delete and no model calls."""
import re
from uuid import uuid4
from datetime import datetime,timezone,timedelta
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .database import Database,GraphError
from .repository import GraphRepository
from .service import GraphService
from .models import ConversationCreate,NodeUpsert

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
    def state(request:Request):
        from .story import StoryEngine
        return StoryEngine(request_service(request)).state()

    @app.post('/api/story/conversations')
    def conversation(body:ConversationCreate,request:Request):
        service=request_service(request)
        if not service.repo.db.settings.graph.startswith('orbit_story_'):raise GraphError(403,'story_isolation','Story workspace required.')
        service.upsert_node('chatbot:coordinator',NodeUpsert(type='Bot',properties={'name':'Orbit Coordinator'}))
        return service.create_conversation(body)
