"""Counterfactuals run real turns and queries against disposable FalkorDB graphs."""
import json
from test_story import story,turn
from test_final_story import INTRO,TRIP,ROUTE,COMMIT,MOVE
from backend.orbit.models import RelationType as R, EntityType as E


def setup(s):
    for text in (INTRO,TRIP,ROUTE,COMMIT):turn(s,text)


def move(s,time):
    result=turn(s,f"Dad's appointment moved to {time}.")
    assert not result['clarifications']
    analysis=json.loads(s.require(result['decision_id'])['properties']['analysis'])
    content=next(h['content'] for h in result['handoffs'] if h['agent']=='planner')
    ids={e for p in analysis['affected'] for e in p['edge_ids']}
    assert ids=={e['id'] for e in result['evidence_relationships']}
    actual={e['id']:e for e in result['graph']['edges']}
    for path in analysis['affected']:
        for a,b,e in zip(path['node_ids'],path['node_ids'][1:],path['edge_ids']):
            assert {actual[e]['source'],actual[e]['target']}=={a,b}
    finding=s.repo.db.execute('MATCH (f:Source {message_id:$id,owner:"planner",record_kind:"AGENT_FINDING"}) RETURN f.description',{'id':result['user']['id']},read=True)
    assert finding[0][0]==content
    return content,analysis


def delete(s,source,kind,target):
    s.repo.db.execute(f'MATCH (a:Entity {{id:$source}})-[r:{kind}]->(b:Entity {{id:$target}}) DELETE r',{'source':source,'target':target})


def test_cab_dependency_remove_restore_and_other_dependency(story):
    setup(story)
    a,paths=move(story,'1:45 PM')
    assert '9:45 AM cab pickup needs to be revised' in a
    assert 'meeting and' in a and 'physiotherapy need a timing check' in a
    assert any(len(p['edge_ids'])==2 and p['entity_id']=='story:physio' for p in paths['affected'])
    delete(story,'story:cab','DEPENDS_ON','story:appointment')
    b,paths=move(story,'1:46 PM')
    assert story.require('story:cab')
    assert 'cab pickup needs' not in b and 'physiotherapy needs' not in b
    assert 'meeting needs a timing check' in b
    assert not any(p['entity_id'] in ('story:cab','story:physio') for p in paths['affected'])
    story.repo.upsert_edge('story:cab',R.DEPENDS_ON,'story:appointment',{'note':'Restored test dependency'})
    c,_=move(story,'1:47 PM')
    assert 'cab pickup needs to be revised' in c and 'physiotherapy need a timing check' in c
    delete(story,'story:deployment','RELATED_TO','story:appointment')
    d,paths=move(story,'1:48 PM')
    assert story.require('story:deployment') and 'meeting' not in d
    assert "physiotherapy needs a timing check" in d
    assert 'story:deployment' not in paths['timing_review']
    delete(story,'story:physio','DEPENDS_ON','story:cab')
    e,_=move(story,'1:49 PM')
    assert 'physiotherapy' not in e and 'cab pickup needs' in e


def test_known_meeting_separation_and_wrong_direction(story):
    setup(story)
    story.repo.upsert_node('story:appointment',E.Event,{'ends_at':'2026-10-26T14:00:00+05:30'})
    # Fixture Monday is October 26. A known end before the meeting removes its review.
    a,analysis=move(story,'1:45 PM')
    assert 'meeting' not in a and 'story:deployment' not in analysis['timing_review']
    delete(story,'story:cab','DEPENDS_ON','story:appointment')
    story.repo.upsert_edge('story:appointment',R.DEPENDS_ON,'story:cab',{})
    b,_=move(story,'1:46 PM')
    assert 'cab pickup needs' not in b


def test_approved_part_five_text(story):
    setup(story)
    result=turn(story,MOVE)
    text=next(h['content'] for h in result['handoffs'] if h['agent']=='planner')
    assert text=="I've checked the connected commitments. Here's what needs attention.\n\n[✅] Dad's appointment is now Monday at 1:45 PM.\n[⏳] The 9:45 AM cab pickup needs to be revised.\n[⏳] Your 2:30 PM meeting and Dad's 4:00 PM physiotherapy need a timing check.\n\nWe should confirm who can take Dad before changing the transport plan."
