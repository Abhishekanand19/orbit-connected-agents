"""Opt-in genuine Gemini -> approval -> local MCP task -> FalkorDB readback.

Reuses actual saved specialist findings from the isolated demo. Only a disposable
test graph is mutated; no external action is ever approved or dispatched.
"""
import json
import os
import uuid
import pytest
from backend.orbit.config import Settings
from backend.orbit.database import Database,GraphError
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.demo import Demo,GRAPH
from backend.orbit.agents import Collaboration
from backend.orbit.actions import Actions
from backend.orbit.chat import ChatRequest
from backend.orbit.models import EntityType as E,RelationType as R,ConversationCreate,MessageCreate
from backend.orbit.receipts import Receipts
from backend.orbit import memory

def test_live_model_approval_mcp_readback_and_recall():
    if os.getenv('ORBIT_LIVE_GENERATION')!='1':pytest.skip('Opt in to one real Gemini structured-generation request.')
    settings=Settings.from_env()
    source=Database(settings.model_copy(update={'graph':GRAPH}));source.initialize()
    db=Database(settings.model_copy(update={'graph':'orbit_test_demo_live_'+uuid.uuid4().hex}));db.initialize()
    try:
        s=GraphService(GraphRepository(db));demo=Demo(s);demo.seed()
        for event in ['rumor','roads','pending','confirmed','available']:demo.inject(event)
        saved=demo.inject('available')
        # These are real previously completed agents, not scripted test responses.
        original=Collaboration(GraphService(GraphRepository(source)))
        findings=original.shared(saved['message_id']);runs=original.activity(saved['message_id'])
        assert findings and all(r['properties']['status']=='DONE' for r in runs)
        for run in runs:s.repo.upsert_node(run['id'],E.Task,run['properties'])
        for finding in findings:
            s.repo.upsert_node(finding['id'],E.Source,finding['properties'])
            run=next(r for r in runs if r['properties']['owner']==finding['properties']['owner'])
            s.repo.upsert_edge(run['id'],R.PRODUCED,finding['id'],{})
        req=ChatRequest(id=saved['message_id'],bot_id='coordinator',name='Orbit Coordinator',conversation_id=saved['conversation_id'],content=s.require(saved['message_id'])['properties']['content'])
        manager=Actions(s)
        errors=Collaboration(s).compile_proposals(req,manager)
        proposals=manager.list()
        assert proposals,errors
        assert all(p['application']=='task' for p in proposals), 'External drafts are never approved by this test'
        # A single real model-produced internal task proves execution without
        # approving other drafts or writing to any external provider.
        proposal=proposals[0]
        assert proposal['status']=='AWAITING_APPROVAL'
        with pytest.raises(GraphError):manager.dispatch(proposal['id'],proposal['digest'])
        assert manager.view(manager.get(proposal['id']))['status']=='AWAITING_APPROVAL'
        manager.approve(proposal['id'],proposal['digest'])
        result=manager.dispatch(proposal['id'],proposal['digest'])
        assert result['status']=='VERIFIED' and result['verification']['verified']
        assert manager.get(proposal['id'])['properties']['transport']=='mcp-memory'
        assert Receipts(s).get(proposal['id'])['status']=='VERIFIED'
        # Replay consumes no second write, and a new session retrieves the outcome.
        assert manager.dispatch(proposal['id'],proposal['digest'])['verification']==result['verification']
        s.create_conversation(ConversationCreate(id='live-next-session',bot_id='chatbot:coordinator',title='Recall verified outcome'))
        query=proposal['payload']['changes'].get('name','')+' '+proposal['reason']
        s.create_message('live-next-session',MessageCreate(id='live-recall',role='user',content=query))
        recalled=memory.retrieve(s,query,'live-next-session')
        assert any(n['id']==proposal['id'] and n['properties']['status']=='VERIFIED' for n in recalled['nodes'])
        print(json.dumps({'model_output':'genuine Gemini','tool':proposal['tool'],'status':result['status'],'readback':True,'new_session_retrieval':True,'external_writes':0}))
    finally:
        db.graph.delete();db.close();source.close()
