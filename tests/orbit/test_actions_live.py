"""Opt-in live WRITES. Run only after explicit authorization of these exact test targets.

ORBIT_LIVE_WRITES_APPROVED=calendar,gmail,slack explicitly opts into selected tests.
No target defaults: use a dedicated calendar, test recipient and authorized test channel.
"""
import os
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from backend.orbit.database import Database
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.models import NodeUpsert,ConversationCreate,MessageCreate
from backend.orbit.action_models import ActionDraft
from backend.orbit.actions import Actions

@pytest.fixture
def live_world(settings):
    if not os.getenv('ORBIT_LIVE_WRITES_APPROVED'):pytest.skip('Live writes require explicit test-target authorization.')
    db=Database(settings);db.initialize();s=GraphService(GraphRepository(db))
    s.upsert_node('bot',NodeUpsert(type='Bot',properties={'name':'Authorized smoke test'}))
    s.upsert_node('test-task',NodeUpsert(type='Task',properties={'name':'Authorized smoke test'}))
    s.create_conversation(ConversationCreate(id='test-session',bot_id='bot',title='Authorized smoke test'))
    s.create_message('test-session',MessageCreate(id='test-request',role='user',content='Execute only the explicitly authorized smoke-test payloads.'))
    yield Actions(s)
    # Retain real execution receipts, especially UNKNOWN outcomes, for later reconciliation.
    db.close()

def target(provider,key):
    if provider not in os.getenv('ORBIT_LIVE_WRITES_APPROVED','').split(','):pytest.skip('This provider has no live-write authorization.')
    value=os.getenv(key)
    if not value:pytest.skip('Configure explicit controlled target '+key)
    return value

def execute(manager,kind,payload):
    action=manager.propose(ActionDraft(kind=kind,payload=payload,reason='Explicitly authorized Phase 08 smoke test.',affected_ids=['test-task'],evidence_ids=['test-request']),'test-request')
    manager.approve(action['id'],action['digest'])
    result=manager.dispatch(action['id'],action['digest'])
    assert result['status']=='VERIFIED','Live action was not verified; inspect its saved status before any retry.'
    return result

def test_live_calendar_create_update_readback(live_world):
    calendar=target('calendar','ORBIT_TEST_CALENDAR_ID');start=datetime.now(timezone.utc)+timedelta(days=1)
    payload={'calendar_id':calendar,'changes':{'summary':'ORBIT authorized smoke test '+str(uuid4()),'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=10)).isoformat(),'attendees':[]},'send_updates':'none'}
    created=execute(live_world,'calendar_create',payload)
    payload.update(event_id=created['receipt']['id'],expected_etag=created['verification']['readback']['etag'])
    payload['changes']['summary']+=' verified update'
    execute(live_world,'calendar_update',payload)

def test_live_gmail_send_readback(live_world):
    recipient=target('gmail','ORBIT_TEST_EMAIL_TO')
    execute(live_world,'gmail_send',{'to':[recipient],'subject':'ORBIT authorized smoke test '+str(uuid4()),'body':'This is the explicitly authorized Phase 08 approval and readback test.'})

def test_live_slack_post_readback(live_world):
    channel=target('slack','ORBIT_TEST_SLACK_CHANNEL')
    execute(live_world,'slack_post',{'channel_id':channel,'text':'ORBIT explicitly authorized Phase 08 smoke test '+str(uuid4())})
