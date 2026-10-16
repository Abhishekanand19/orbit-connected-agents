"""Local-only typed HTTP API. No AWS imports, arbitrary Cypher or LLM calls."""
from contextlib import asynccontextmanager
import logging
from typing import Annotated, Literal
from fastapi import FastAPI, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from .config import Settings
from .database import Database, GraphError
from .models import (Id, EntityType, NodeUpsert, RelationshipUpsert, ConversationCreate, MessageCreate,
    ClaimCreate, TraversalRequest, NodeView, EdgeView, Subgraph, HealthView, StrictModel)
from .repository import GraphRepository
from .service import GraphService

class MessagePage(StrictModel):
    items: list[NodeView]
    next_offset: int | None

class AffectedView(StrictModel):
    graph: Subgraph
    candidate_ids: list[str]

class DeleteView(StrictModel):
    deleted: str

Hops = Annotated[int, Query(ge=1,le=4)]
Limit = Annotated[int, Query(ge=1,le=500)]

def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    @asynccontextmanager
    async def lifespan(app):
        db = Database(settings)
        app.state.service = GraphService(GraphRepository(db))
        try:
            try:
                await run_in_threadpool(db.initialize)
                from .actions import Actions
                await run_in_threadpool(Actions(app.state.service).recover)
            except GraphError:
                logging.getLogger(__name__).warning('FalkorDB unavailable at startup; API will return 503 until recovery.')
            yield
        finally:
            db.close()

    app = FastAPI(title='ORBIT — FalkorDB Foundation',version='0.1.0',lifespan=lifespan)
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
    from .integration_auth import mount_auth
    mount_auth(app)
    from .action_api import mount_actions
    mount_actions(app,settings)
    from .receipts import mount_receipts
    mount_receipts(app)
    from .demo import mount_demo
    mount_demo(app)
    app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins,
        allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type','X-Orbit-UI'],allow_credentials=True)

    @app.middleware('http')
    async def local_browser_guard(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in settings.allowed_origins:
            return JSONResponse({'error':{'code':'origin_denied','message':'Browser origin is not allowed.'}},status_code=403)
        return await call_next(request)

    @app.exception_handler(GraphError)
    async def graph_error(request, error):
        return JSONResponse({'error':{'code':error.code,'message':error.message}},status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse({'error':{'code':'invalid_request','message':'Request validation failed.',
            'details':[{'location':list(e['loc']),'message':e['msg']} for e in error.errors()]}},status_code=422)

    def service(request: Request):
        return request.app.state.service
    Service = Annotated[GraphService, Depends(service)]

    @app.get('/api/health',response_model=HealthView)
    def health(s: Service):
        s.repo.db.execute('RETURN 1',read=True)
        return {'status':'ok','database':'FalkorDB','graph':settings.graph}

    @app.get('/api/nodes',response_model=MessagePage)
    def search_nodes(s: Service, q: Annotated[str,Query(max_length=200)]='',
                     type: EntityType | None=None, limit: Limit=30,
                     offset: Annotated[int,Query(ge=0,le=100000)]=0):
        return s.repo.search_nodes(q.strip(),type,offset,limit)

    @app.put('/api/nodes/{node_id}',response_model=NodeView)
    def upsert_node(node_id: Id, body: NodeUpsert, s: Service):
        return s.upsert_node(node_id,body)

    @app.get('/api/nodes/{node_id}',response_model=NodeView)
    def get_node(node_id: Id,s: Service):
        return s.require(node_id)

    @app.delete('/api/nodes/{node_id}',response_model=DeleteView)
    def delete_node(node_id: Id,s: Service):
        s.delete_node(node_id)
        return {'deleted':node_id}

    @app.put('/api/relationships',response_model=EdgeView)
    def upsert_relationship(body: RelationshipUpsert,s: Service):
        return s.upsert_relationship(body)

    @app.get('/api/relationships/{edge_id}',response_model=EdgeView)
    def get_relationship(edge_id: Id,s: Service):
        return s.repo.get_edge(edge_id)

    @app.delete('/api/relationships/{edge_id}',response_model=DeleteView)
    def delete_relationship(edge_id: Id,s: Service):
        s.delete_relationship(edge_id)
        return {'deleted':edge_id}

    @app.get('/api/nodes/{node_id}/neighbors',response_model=Subgraph)
    def neighbors(node_id: Id,s: Service,limit: Limit=100):
        return s.repo.traverse(TraversalRequest(root_id=node_id,hops=1,limit=limit))

    @app.post('/api/graph/traverse',response_model=Subgraph)
    @app.post('/api/graph/subgraph',response_model=Subgraph)
    def traverse(body: TraversalRequest,s: Service):
        return s.repo.traverse(body)

    @app.get('/api/nodes/{node_id}/dependencies',response_model=Subgraph)
    def dependencies(node_id: Id,s: Service,hops: Hops=4,limit: Limit=100,
                     direction: Literal['incoming','outgoing']='outgoing'):
        return s.dependencies(node_id,hops,direction,limit)

    @app.get('/api/nodes/{node_id}/affected',response_model=AffectedView)
    def affected(node_id: Id,s: Service,hops: Hops=4,limit: Limit=100):
        return s.affected(node_id,hops,limit)

    @app.post('/api/conversations',response_model=NodeView)
    def create_conversation(body: ConversationCreate,s: Service):
        return s.create_conversation(body)

    @app.get('/api/conversations/{conversation_id}',response_model=NodeView)
    def get_conversation(conversation_id: Id,s: Service):
        from .models import EntityType
        return s.require(conversation_id,{EntityType.Conversation})

    @app.post('/api/conversations/{conversation_id}/messages',response_model=NodeView)
    def create_message(conversation_id: Id,body: MessageCreate,s: Service):
        return s.create_message(conversation_id,body)

    @app.get('/api/conversations/{conversation_id}/messages',response_model=MessagePage)
    def messages(conversation_id: Id,s: Service,limit: Limit=100,offset: Annotated[int,Query(ge=0,le=100000)]=0):
        from .models import EntityType
        s.require(conversation_id,{EntityType.Conversation})
        return s.repo.messages(conversation_id,offset,limit)

    @app.get('/api/conversations/{conversation_id}/context',response_model=Subgraph)
    def context(conversation_id: Id,s: Service,limit: Limit=100):
        return s.conversation_context(conversation_id,limit)

    @app.post('/api/claims',response_model=NodeView)
    def create_claim(body: ClaimCreate,s: Service):
        return s.create_claim(body)

    @app.get('/api/evidence/{node_id}',response_model=Subgraph)
    def evidence(node_id: Id,s: Service,limit: Limit=100):
        return s.evidence(node_id,limit)
    from .chat import ChatRequest, ChatEngine

    @app.post('/api/chat')
    def chat(body: ChatRequest, s: Service):
        return ChatEngine(s).turn(body)

    @app.get('/api/chat/bots/{bot_id}/latest')
    def latest_chat(bot_id: Id, s: Service):
        rows = s.repo.db.execute('MATCH (:Bot {id:$id})-[:HAS_CONVERSATION]->(c:Conversation) RETURN properties(c) ORDER BY c.created_at DESC, c.id DESC LIMIT 1', {'id':'chatbot:'+bot_id}, read=True)
        if not rows:
            return {'conversation_id':None,'messages':[]}
        conversation=rows[0][0]['id']
        messages=[]; offset=0
        while True:
            page=s.repo.messages(conversation,offset,500)
            messages.extend(page['items'])
            if page['next_offset'] is None:break
            offset=page['next_offset']
        return {'conversation_id':conversation,'messages':messages}

    from .records import MemoryRecord, record

    @app.post('/api/memory/records',response_model=NodeView)
    def memory_record(body: MemoryRecord,s: Service):
        return record(s,body)

    @app.get('/api/memory/search')
    def memory_search(s: Service,q: Annotated[str,Query(min_length=1,max_length=2000)],conversation_id: Id):
        from .memory import retrieve
        s.require(conversation_id,{EntityType.Conversation})
        return retrieve(s,q,conversation_id)

    @app.get('/api/chat/activity/{message_id}')
    def agent_activity(message_id: Id,s: Service):
        from .agents import Collaboration
        return {'activity':Collaboration(s).activity(message_id)}

    from .intelligence import ImpactRequest, ImpactResult, ImpactEngine

    @app.post('/api/graph/impact',response_model=ImpactResult)
    def impact(body: ImpactRequest,s: Service):
        return ImpactEngine(s).analyze(body)

    @app.get('/api/graph/impact/{decision_id}',response_model=ImpactResult)
    def impact_receipt(decision_id: Id,s: Service):
        node=s.require(decision_id,{EntityType.Decision})
        if node['properties'].get('record_kind')!='IMPACT_ANALYSIS':
            raise GraphError(404,'not_impact','This decision is not an impact analysis.')
        return ImpactResult.model_validate_json(node['properties']['analysis'])

    from .integrations import Binding, bind, ToolRunner

    @app.post('/api/integrations/bindings',response_model=NodeView)
    def integration_binding(body: Binding,s: Service):
        return bind(s,body)

    @app.get('/api/integrations/traces/{message_id}')
    def integration_traces(message_id: Id,s: Service):
        s.require(message_id,{EntityType.Message})
        return {'traces':ToolRunner(s).traces(message_id),'evidence':ToolRunner(s).evidence(message_id)}

    @app.get('/api/integrations/tools')
    async def integration_tools(s: Service):
        from .mcp_tools import session
        async with session(ToolRunner(s).server) as client:
            return (await client.list_tools()).model_dump(mode='json')

    @app.get('/api/integrations/status')
    def integration_status():
        import os
        from .integration_auth import google_auth, REDIRECT
        try:
            saved=google_auth.vault.load()
            google='connected' if saved and not saved.get('reconnect_required') else 'reconnect_required'
        except GraphError:
            google='secure_storage_unavailable'
        return {'google':google,'google_configured':bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET')),
                'google_redirect_uri':REDIRECT,'slack_configured':bool(os.getenv('SLACK_BOT_TOKEN')),
                'read_only':False,'writes_require_approval':True,'owner':'local-owner','live_verified':False}

    return app

app = create_app()
