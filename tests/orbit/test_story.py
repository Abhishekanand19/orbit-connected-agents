import json
import time
import uuid
import pytest
from backend.orbit.config import Settings
from backend.orbit.database import Database
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.chat import ChatEngine,ChatRequest
from backend.orbit.story import StoryEngine
from backend.orbit.story_parse import parse
from backend.orbit.actions import Actions
from backend.orbit.action_providers import ActionProviders
from backend.orbit.receipts import Receipts
from backend.orbit import llm

@pytest.fixture
def story(monkeypatch):
    monkeypatch.setattr(llm,'generate',lambda *a,**k:pytest.fail('No model calls in deterministic mode'))
    monkeypatch.setattr(ActionProviders,'perform',lambda *a,**k:pytest.fail('No external writes'))
    db=Database(Settings.from_env().model_copy(update={'graph':'orbit_story_'+uuid.uuid4().hex}));db.initialize()
    db.execute('CREATE (:OrbitStoryState {id:"story",revision:0,day:"2026-10-20",slots:"{}"})')
    s=GraphService(GraphRepository(db))
    yield s
    db.graph.delete();db.close()

def turn(s,text,conversation='story:session:one',id=None,source='typed'):
    return ChatEngine(s).turn(ChatRequest(id=id or 'turn:'+uuid.uuid4().hex,bot_id='coordinator',name='Orbit Coordinator',conversation_id=conversation,content=text,source=source))

@pytest.mark.parametrize('text,intent',[
 ('I am Aarav. My father is Ramesh and my sister is Priya.','family'),
 ('Hey, Aarav here — papa Ramesh, sis Priya.','family'),
 ('Um I am Aarav, dad Ramesh and Priya is my sister!','family'),
 ('Someone says the hospital is closed due to a protest.','rumor'),
 ('There is a clinic closure rumour.','rumor'),
 ('Uh, hospital closur rumor, is this true?','rumor'),
 ('His appointment has been rescheduled to 1:45 PM.','schedule'),
 ('Dad’s follow-up shifted to one forty five pm.','schedule'),
 ('The appointmnt moved to 13:45.','schedule'),
 ('Priya confirms availability for the visit.','availability'),
 ('Priya will take dad, yes she is available.','availability'),
 ('My sister confirmed she can escort him.','availability'),
 ('The hospital offers a video consultation.','video'),
 ('His followup can be an online appointment.','video'),
 ('Dad can have a virtual visit instead.','video'),
 ('Can you summarize where we stand?','summary'),
 ('Give me a recap of the final state.','summary'),
 ('What has changed?','summary')])
def test_paraphrases(text,intent):
    result=parse(text,{'ramesh':'Ramesh','priya':'Priya','appointment_start':'11:00'})
    assert intent in result['intents'],result
    assert not result['questions'],result

def test_progressive_story_approval_and_recall(story):
    s=story;assert StoryEngine(s).state()['graph']['nodes']==[]
    first=turn(s,'I am Aarav. My father is Ramesh and my sister is Priya.',id='stage:1')
    people=[n for n in first['graph']['nodes'] if n['type']=='Person'];ids={n['id'] for n in people}
    assert len(people)==3 and len([e for e in first['graph']['edges'] if e['source'] in ids and e['target'] in ids])==2
    assert turn(s,'I am Aarav. My father is Ramesh and my sister is Priya.',id='stage:1')==first
    turn(s,'Mom Meera joins us. Dad has a hospital follow-up at 11 AM and the cab at 9:45 AM.')
    turn(s,'Meera is unavailable after 12:30 PM, Priya is free from noon, my deployment is at 2:30 PM and physiotherapy is at 4 PM.')
    rumor=turn(s,'I heard a rumour the hospital is closed because of a protest.')
    assert 'independently confirmed' in rumor['handoffs'][0]['content'] and not rumor['action_ids']
    moved=turn(s,'His hospital appointment shifted to 1:45 PM.')
    receipt=Receipts(s).get(moved['decision_id'])
    assert any(len(p['node_ids'])>=3 for p in receipt['paths'])
    assert all(p['complete'] for p in receipt['paths'])
    confirmed=turn(s,'Priya confirms she can escort dad.')
    assert {'planner','tasks','communication'}<={h['agent'] for h in confirmed['handoffs']}
    last=s.require(confirmed['handoffs'][-1]['run_id'])['properties']
    assert len(json.loads(last['retrieved_ids']))>=3
    manager=Actions(s);assert len(confirmed['action_ids'])==1
    proposal=manager.view(manager.get(confirmed['action_ids'][0]));assert proposal['status']=='AWAITING_APPROVAL'
    assert proposal['payload']['changes']['starts_at'].endswith('12:30:00+05:30')
    manager.approve(proposal['id'],proposal['digest']);assert manager.dispatch(proposal['id'],proposal['digest'])['status']=='VERIFIED'
    video=turn(s,'The hospital offers a virtual visit instead.',conversation='story:session:two',source='voice_transcript')
    assert any(p['id']==proposal['id'] for p in video['previous'])
    cancel=manager.view(manager.get(video['action_ids'][0]));assert cancel['payload']['changes']=={'status':'CANCELLED'}
    manager.approve(cancel['id'],cancel['digest']);assert manager.dispatch(cancel['id'],cancel['digest'])['status']=='VERIFIED'
    summary=turn(s,'Summarize the final state.',conversation='story:session:two')
    assert 'removed after approval and verified readback' in summary['assistant']['properties']['content']
    assert s.require('story:deployment')['properties']['status']=='OPEN'
    again=turn(s,'The hospital offers an online appointment.',conversation='story:session:two')
    assert not again['action_ids'] and len(manager.list())==2
    print('story_turn_latency_ms',json.dumps([first['latency_ms'],moved['latency_ms'],confirmed['latency_ms'],video['latency_ms'],summary['latency_ms']]))

def test_ambiguity_corrections_and_out_of_order(story):
    s=story
    result=turn(s,'His appointment moved.')
    assert 'Who' in result['assistant']['properties']['content'] and not any(n['type']=='Event' for n in result['graph']['nodes'])
    turn(s,'I am Aarav, my father Ramesh and sister Priya. Priya confirms availability from noon.')
    turn(s,'Dad has a hospital appointment at 11 AM and a taxi at 9:45 AM.')
    result=turn(s,'Actually his appointment is now at 1:45 PM.')
    assert s.require('story:appointment')['properties']['starts_at'].endswith('13:45:00+05:30')
    assert s.repo.db.execute("MATCH (c:Claim)-[:SUPERSEDES]->(old:Claim) WHERE c.slot='appointment_start' RETURN old.status",read=True)==[['SUPERSEDED']]
    before=s.require('story:appointment')['properties']
    turn(s,'Move his appointment to 2:30.')
    assert s.require('story:appointment')['properties']==before

@pytest.mark.parametrize('text,field,value',[
    ('Mum Meera is not free after 12:30 PM.','meera_unavailable_from','12:30'),
    ("Mother Meera isn't available after half past two pm.",'meera_unavailable_from','14:30'),
    ('Priya is available from midday.','priya_available_from','12:00'),
    ('My sister is free from twelve thirty pm.','priya_available_from','12:30'),
    ('Dad has a follow-up at eleven am.','appointment_start','11:00'),
    ('Papa has a hospital visit at 11:00 AM.','appointment_start','11:00'),
    ('The taxi is at quarter to ten am.','cab_start','09:45'),
    ('Transport pickup at nine forty five am.','cab_start','09:45'),
    ('Work deployment at half past two pm.','deployment_start','14:30'),
    ('My work release is at 14:30.','deployment_start','14:30'),
    ('Physio at four pm.','physio_start','16:00'),
    ('Physiotherapy begins at 16:00.','physio_start','16:00')])
def test_slots_and_spoken_times(text,field,value):
    result=parse(text,{'ramesh':'Ramesh','meera':'Meera','priya':'Priya'})
    assert not result['questions'],result
    assert result['facts'][field]==value

def test_ambiguous_identity_and_time_never_guessed():
    assert parse('My father is John.',{'ramesh':'Ramesh'})['questions']
    assert parse('The cab is at quarter to ten.',{})['questions']
    assert parse('Aarav spoke to Ramesh and he is unavailable.',{})['questions']

def test_workspace_api_isolation(client):
    a=client.post('/api/story/workspaces').json();b=client.post('/api/story/workspaces').json()
    try:
        headers={'X-Orbit-Story':a['workspace_id']}
        response=client.post('/api/chat',headers=headers,json={'id':'hello','bot_id':'coordinator','name':'Orbit Coordinator','conversation_id':'one','content':'Aarav here, dad Ramesh and sister Priya.'})
        assert response.status_code==200,response.text
        assert client.get('/api/story/state',headers={'X-Orbit-Story':b['workspace_id']}).json()['graph']['nodes']==[]
        assert client.get('/api/nodes?q=Ramesh').json()['items']==[]
        assert client.get('/api/nodes',headers={'X-Orbit-Story':'orbit_demo_family'}).status_code==400
    finally:
        for workspace in (a,b):
            db=Database(Settings.from_env().model_copy(update={'graph':workspace['graph']}));db.initialize();db.graph.delete();db.close()
