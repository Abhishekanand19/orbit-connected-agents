import json
import pytest
from test_story import story,turn
from backend.orbit.story_parse import parse
from backend.orbit.story import StoryEngine
from backend.orbit.actions import Actions

MESSAGES=[
"Hey Orbit, I'm Aarav. My dad is Ramesh and Priya is my sister.",
"Dad has a follow-up at 11 tomorrow. Mom Meera is taking him, and the cab arrives at 9:45.",
"Mom is busy after 12:30, Priya is free from noon, my deployment is at 2:30, and Dad has physio at 4.",
"Someone forwarded a message saying the hospital is closed because of a protest. Should I cancel the cab?",
"The hospital emailed me that Dad's appointment moved from 11 to 1:45. What does that affect?",
"Priya confirmed she can take Dad. Can you organize everything and tell everyone?",
"Hey Orbit, remember Dad's appointment? The hospital says he can do it over video now. Do we still need the cab?",
"Perfect, where do things stand now?"
]
GROUPS=[
('family',[MESSAGES[0],'Aarav here; papa Ramesh and sister Priya.','Um, my name is Aarav. Father is Ramesh; Priya is my sister.','My sister is Priya, my dad is Ramesh, I am Aarav.','Hi! Aarav speaking, Ramesh is my father and Priya my sister.']),
('schedule',[MESSAGES[1],'Papa has a hospital visit at 11 AM; taxi pickup is 9:45 AM.','Mom Meera will escort dad. His appointment is at eleven am; cab at nine forty five am.','A cab at 09:45 AM for his followup at 11 AM.','Uh, hospital appointmnt at 11 am and transport at 9:45 am.']),
('schedule',[MESSAGES[2],'Meera is unavailable from 12:30 pm; Priya is free from noon. Deployment at 14:30 and physio at 16:00.','My work release is 2:30 PM, physiotherapy at 4 PM, mum is busy after 12:30 PM.','Dad has physiotherapy at four pm. Work deployment at half past two pm.','Actually, my deployment is 14:30; Priya is available from midday.']),
('rumor',[MESSAGES[3],'A forwarded rumor says the clinic is shut.','Um, heard a hospital closure rumour due to protests.','Someone says hospital closed. Should transport stay?','The hospital closur message is unverified.']),
('schedule',[MESSAGES[4],"Papa's appointment shifted to 1:45.",'Bro, received an email, Dad’s slot is now at 1:45 PM.','Hospital rescheduled the appointmnt to 13:45.','Correction: his follow-up moved from 11 AM to 1:45 PM.']),
('availability',[MESSAGES[5],'My sister confirms she can escort dad.','Priya will accompany Ramesh; please coordinate the plan.','Priya definitely can take him, tell everyone.','Um, Priya confirmed she will take papa.']),
('video',[MESSAGES[6],'Dad can have a virtual visit instead.','His follow-up can be online now.','Remember the hospital appointment? A remote consultation is offered.','Hospital says a video visit is possible, so review the cab.']),
('summary',[MESSAGES[7],'Give me a recap.','Can you summarize the final state?','Where do we stand with the family plan?','What is the latest summary, please?'])
]
@pytest.mark.parametrize('stage,intent,text',[(i,intent,text) for i,(intent,texts) in enumerate(GROUPS) for text in texts])
def test_story_paraphrase(stage,intent,text):
    slots={}
    for prior in MESSAGES[:stage]:
        result=parse(prior,slots);assert not result['questions'],result;slots.update(result['facts'])
    result=parse(text,slots)
    assert not result['questions'],result
    assert intent in result['intents'],result
    if stage==4:assert result['facts']['appointment_start']=='13:45'
    if stage==5:assert result['facts']['priya_escort']=='CONFIRMED'

def test_exact_user_story_current_facts_and_safety(story):
    s=story;results=[]
    for i,text in enumerate(MESSAGES):
        result=turn(s,text,conversation='product:two' if i>=6 else 'product:one');results.append(result)
        assert not result['clarifications'],result
        assert result['intents']
        if i==0:
            people=[n for n in result['graph']['nodes'] if n['type']=='Person'];ids={n['id'] for n in people}
            assert len(people)==3
            assert len([e for e in result['graph']['edges'] if e['source'] in ids and e['target'] in ids])==2
        if i==3:
            assert not result['action_ids'] and s.require('story:cab')['properties']['status']=='OPEN'
            assert StoryEngine(s).state()['slots']['rumor']=='UNVERIFIED'
        if i>=4:assert s.require('story:appointment')['properties']['starts_at'][11:16]=='13:45'
        if i==4:
            assert s.repo.db.execute("MATCH (c:Claim)-[:SUPERSEDES]->(old:Claim) WHERE c.slot='appointment_start' RETURN old.status,old.text",read=True)[0][0]=='SUPERSEDED'
            assert '1:45 PM' in result['assistant']['properties']['content']
        if i==5:
            assert s.require('story:priya')['properties']['escort']=='CONFIRMED'
            assert {'planner','tasks','communication'}=={h['agent'] for h in result['handoffs']}
            assert result['action_ids']
            assert all(a['status']=='AWAITING_APPROVAL' for a in Actions(s).list())
            assert not s.repo.db.execute('MATCH (o:Outcome) RETURN o.id',read=True)
        if i==6:
            assert '1:45 PM' in result['assistant']['properties']['content']
            assert 'Priya' in result['assistant']['properties']['content']
            assert s.require('story:appointment')['properties']['location']=='video'
    final=results[-1]['assistant']['properties']['content']
    assert all(t in final for t in ['1:45 PM','2:30 PM','4:00 PM','video','still requires approval'])
    assert not results[-1]['handoffs']
    before={n['id'] for n in results[-1]['graph']['nodes'] if n['type'] in ('Person','Event','Booking')}
    again=turn(s,MESSAGES[5]);after={n['id'] for n in again['graph']['nodes'] if n['type'] in ('Person','Event','Booking')}
    assert before==after

def test_negation_and_missing_slots(story):
    for text in MESSAGES[:3]:turn(story,text)
    result=turn(story,'The hospital did NOT cancel the appointment.')
    assert story.require('story:cab')['properties']['status']=='OPEN'
    assert not result['action_ids']
    result=turn(story,'The hospital changed Ramesh’s timing.')
    assert result['clarifications'] and 'time' in result['assistant']['properties']['content']
    turn(story,'Priya cannot take Dad.')
    assert story.require('story:priya')['properties']['escort']=='REFUTED'
    result=turn(story,'She can take Dad.')
    assert story.require('story:priya')['properties']['escort']=='CONFIRMED'


def test_repeated_reschedule_keeps_current_afternoon(story):
    for text in MESSAGES[:5]:turn(story,text)
    turn(story,MESSAGES[4])
    assert story.require('story:appointment')['properties']['starts_at'][11:16]=='13:45'
    turn(story,"Papa's appointment shifted to 1:45.")
    assert story.require('story:appointment')['properties']['starts_at'][11:16]=='13:45'
    result=turn(story,"Priya has not confirmed she can take Dad.")
    assert story.require('story:priya')['properties']['escort']=='PENDING'
    assert not result['action_ids']
