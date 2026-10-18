import json
import pytest
from test_story import story,turn
from backend.orbit.story import StoryEngine
from backend.orbit.story_parse import parse
from backend.orbit.actions import Actions

INTRO="Hey bro, my parents and my sister are coming together this weekend for my dad's post-surgery care."
TRIP="Yeah buddy, help me make the arrangements. Dad has a hospital appointment on Monday at 11 AM. Can you book an Uber for 9:45 AM?"
ROUTE="From PES University, Bengaluru, to Manipal Hospital, Jayanagar."
COMMIT="One more thing. Mom's busy after 12:30 PM, I've got a team meeting at 2:30 PM, and Dad has physiotherapy at 4 PM."
RUMOR="Hey, I saw a WhatsApp message saying hospitals are closed because of the ongoing student protests. Can you check whether Manipal Hospital, Jayanagar is actually closed?"
MOVE="Hey, I just got an email from the hospital. Dad's Monday appointment has been moved from 11 AM to 1:45 PM. I'm a bit confused now. Can you help me figure things out?"
PRIYA="Okay, Priya said she can take Dad to the hospital on Monday. Can you update the plan and email her about the changes?"
VIDEO="Hey buddy, remember Dad's hospital appointment? The hospital now says he can attend Monday's 1:45 PM appointment over video. What changes in our plan?"

def test_final_seven_parts(story):
    s=story
    first=turn(s,INTRO,id='intro')
    assert "What would you like me to help arrange?" in first['assistant']['properties']['content']
    people=[n for n in first['graph']['nodes'] if n['type']=='Person']
    assert {n['properties']['name'] for n in people}=={'Father','Mother','Sister'}
    assert not any(n['type'] in ('Event','Booking') for n in first['graph']['nodes'])
    assert turn(s,INTRO,id='intro')==first
    trip=turn(s,TRIP);assert 'Where should the cab pick you up?' in trip['handoffs'][0]['content']
    assert not trip['route_preview']
    assert '1. Where' in trip['handoffs'][0]['content']
    assert StoryEngine(s).state()['slots']['pending_specialist']=='tasks'
    route=turn(s,ROUTE);assert 'Uber booking pending' in route['handoffs'][0]['content']
    assert s.require('story:cab')['properties']['pickup']=='PES University, Bengaluru'
    assert story.require('story:hospital')['properties']['name']=='Manipal Hospital, Jayanagar'
    assert story.require('story:appointment')['properties']['location']=='Manipal Hospital, Jayanagar'
    assert story.require('story:cab')['properties']['destination']=='Manipal Hospital, Jayanagar'
    assert route['direct_specialist']
    assert 'Got the trip details!' in route['handoffs'][0]['content']
    assert route['route_preview']
    commit=turn(s,COMMIT);assert '12:30 PM' in commit['handoffs'][0]['content']
    rumor=turn(s,RUMOR);assert 'not independently confirmed' in rumor['handoffs'][0]['content']
    assert '10924808/' in rumor['handoffs'][0]['content']
    assert story.require('story:indian-express:article')['properties']['publisher']=='The Indian Express'
    assert story.require('story:indian-express:article')['properties']['retrieval_status']=='NOT_RETRIEVED'
    sourced=[n for n in rumor['graph']['nodes'] if n['properties'].get('source_id')=='story:indian-express:article']
    assert sourced and all(n['properties']['status']=='UNVERIFIED' for n in sourced)
    assert rumor['handoffs'][0]['content'].endswith("Manipal Hospital, Jayanagar's closure remains unverified.")
    moved=turn(s,MOVE);assert s.require('story:appointment')['properties']['starts_at'][11:16]=='13:45'
    assert any(len(p['node_ids'])>=3 for p in json.loads(s.require(moved['decision_id'])['properties']['analysis'])['affected'])
    claim=s.require(StoryEngine(s).state()['slots']['_claim_appointment_start'])
    assert json.loads(claim['properties']['previous_value'])=='11:00'
    result=turn(s,PRIYA);assert not result['action_ids']
    assert "What's Priya's email address?" in result['handoffs'][1]['content']
    email=turn(s,'Her email is priya@example.com.')
    action=Actions(s).view(Actions(s).get(email['action_ids'][0]))
    assert action['payload']['to']==['priya@example.com'] and action['status']=='AWAITING_APPROVAL'
    assert action['tool']=='action_gmail_send' and '1:45 PM' in action['payload']['body']
    assert not action['receipt']
    # The final graph must still match the proposal seal when the user approves.
    Actions(s).approve(action['id'],action['digest'])
    repeat=turn(s,'Her email is priya@example.com.')
    assert repeat['action_ids']==email['action_ids']
    video=turn(s,VIDEO,conversation='session:new')
    assert video['previous'] and all(p['retrieved_from']=='FalkorDB' for p in video['previous'])
    assert len(video['checklist'])==3 and not video['action_ids']
    assert s.require('story:deployment')['properties']['starts_at'][11:16]=='14:30'
    assert s.require('story:physio')['properties']['starts_at'][11:16]=='16:00'
    intro_again=turn(s,INTRO,conversation='session:unrelated')
    assert intro_again['assistant']['properties']['content']==first['assistant']['properties']['content']
    assert not intro_again['handoffs']

@pytest.mark.parametrize('text',[
 "My parents and sister are coming to help with dad's surgery recovery.",
 "Um, my father, mother and sister are coming for post surgery care.",
 "Hey bro my parents and my sister are coming this weekend for papa's care!",
])
def test_role_introduction_variations(text):
    r=parse(text,{})
    assert 'family' in r['intents'] and not r['questions']
    assert set(r['facts'])>={'ramesh','meera','priya'}

@pytest.mark.parametrize('text', ['The appointmnt shifted to 1:45 PM.', 'Dad has an online consultation now.', 'Uh, hospital closur rumor from WhatsApp.'])
def test_natural_variations(text):
    assert not parse(text,{'ramesh':'Father','appointment_start':'11:00'})['questions']

def test_ambiguous_time_no_changes(story):
    turn(story,INTRO)
    result=turn(story,'His appointment moved to 2.')
    assert result['clarifications'] and not StoryEngine(story).state()['slots'].get('appointment_start')

@pytest.mark.parametrize('text',[PRIYA, 'Remember Dad? He has a video appointment.'])
def test_missing_appointment_is_not_presented_as_confirmed(story,text):
    turn(story,INTRO)
    result=turn(story,text)
    assert 'What day and time' in result['assistant']['properties']['content']
    assert not result['action_ids']

@pytest.mark.parametrize('name',['Manipal hospital jaynagar','Manipal Hospital Jayanagar','Manipal Hospital, Jayanagar'])
def test_canonical_hospital(name):
    result=parse('From PES University, Bengaluru, to '+name,{'awaiting_trip':'yes'})
    assert result['facts']['destination']=='Manipal Hospital, Jayanagar'


def test_pending_specialist_accepts_partial_slots(story):
    turn(story,INTRO);turn(story,TRIP)
    pickup=turn(story,'Pick us up at PES University, Bengaluru.')
    assert pickup['direct_specialist'] and not pickup['route_preview']
    assert StoryEngine(story).state()['slots']['required_slots']==['destination']
    destination=turn(story,'Destination is Manipal hospital jaynagar.')
    assert destination['direct_specialist'] and destination['route_preview']
    assert 'pending_specialist' not in StoryEngine(story).state()['slots']
    assert story.require('story:cab')['properties']['starts_at'][11:16]=='09:45'
