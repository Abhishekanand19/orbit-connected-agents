from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
from fastapi.testclient import TestClient
from backend.orbit.api import create_app
from backend.orbit.config import Settings
from backend.orbit.models import TraversalRequest
from backend.orbit.seed import seed


def node(client, id, entity_type='Person', **props):
    r=client.put('/api/nodes/'+id,json={'type':entity_type,'properties':props})
    assert r.status_code==200,r.text
    return r.json()

def edge(client, source, kind, target):
    r=client.put('/api/relationships',json={'source':source,'type':kind,'target':target})
    assert r.status_code==200,r.text
    return r.json()

def post(client, path, payload):
    r=client.post(path,json=payload)
    assert r.status_code==200,r.text
    return r.json()


def test_health_upserts_edges_and_concurrent_identity(client):
    assert client.get('/api/health').json()['status']=='ok'
    a=node(client,'person',name='Before')
    b=node(client,'person',name='After')
    assert a['created_at']==b['created_at']
    assert client.get('/api/nodes/person').json()['properties']['name']=='After'
    node(client,'task','Task',name='Job')
    rel=edge(client,'task','ASSIGNED_TO','person')
    updated=client.put('/api/relationships',json={'source':'task','type':'ASSIGNED_TO','target':'person','properties':{'note':'Owner'}}).json()
    assert rel['id']==updated['id'] and rel['created_at']==updated['created_at']
    assert client.get('/api/relationships/'+rel['id']).json()['properties']['note']=='Owner'
    graph=client.get('/api/nodes/task/neighbors').json()
    assert len(graph['edges'])==1 and len(graph['nodes'])==2
    with ThreadPoolExecutor(max_workers=6) as executor:
        results=list(executor.map(lambda _:node(client,'concurrent',name='Same'),range(12)))
    assert len({n['id'] for n in results})==1
    rows=client.app.state.service.repo.db.execute('MATCH (n:Entity {id:$id}) RETURN count(n)',{'id':'concurrent'},read=True)
    assert rows==[[1]]


def test_real_relationship_mutation_changes_multihop_results(client):
    seed(client.app.state.service)
    payload={'root_id':'sample:appointment','hops':3,'relationship_types':['DEPENDS_ON','ASSIGNED_TO']}
    before=post(client,'/api/graph/traverse',payload)
    ids={n['id'] for n in before['nodes']}
    assert ids=={'sample:appointment','sample:transport','sample:priya','sample:work'}
    assert any(p['node_ids']==['sample:appointment','sample:transport','sample:priya','sample:work'] for p in before['paths'])
    link=next(e for e in before['edges'] if e['source']=='sample:transport' and e['type']=='ASSIGNED_TO')
    assert client.delete('/api/relationships/'+link['id']).status_code==200
    edge(client,'sample:transport','ASSIGNED_TO','sample:dad')
    after=post(client,'/api/graph/traverse',payload)
    after_ids={n['id'] for n in after['nodes']}
    assert after_ids=={'sample:appointment','sample:transport','sample:dad'}
    print(json.dumps({'before':sorted(ids),'after':sorted(after_ids)}))
    dependencies=client.get('/api/nodes/sample:appointment/dependencies').json()
    assert {n['id'] for n in dependencies['nodes']}=={'sample:appointment','sample:transport'}
    reverse=client.get('/api/nodes/sample:transport/dependencies?direction=incoming').json()
    assert 'sample:appointment' in {n['id'] for n in reverse['nodes']}
    path=post(client,'/api/graph/subgraph',{**payload,'target_id':'sample:dad'})
    assert path['paths'] and all(p['node_ids'][-1]=='sample:dad' for p in path['paths'])
    bounded=post(client,'/api/graph/traverse',{'root_id':'sample:appointment','limit':1})
    assert bounded['truncated'] is True
    assert 'sample:transport' in client.get('/api/nodes/sample:appointment/affected').json()['candidate_ids']


def test_claim_provenance_supersession_and_no_silent_rewrite(client):
    seed(client.app.state.service)
    now=datetime.now(timezone.utc).isoformat()
    original=client.get('/api/nodes/sample:claim').json()
    assert original['properties']['status']=='PENDING'
    post(client,'/api/conversations/sample:conversation/messages',{'id':'confirmed:message','role':'user',
        'content':'Priya confirmed she will take Dad.','mentioned_ids':['sample:priya']})
    node(client,'confirmed:source','Source',kind='USER_MESSAGE',observed_at=now)
    body={'id':'confirmed:claim','text':'Priya confirmed transport.','status':'CONFIRMED','source_id':'confirmed:source',
        'message_id':'confirmed:message','subject_ids':['sample:priya','sample:transport'],'observed_at':now,'supersedes_id':'sample:claim'}
    claim=post(client,'/api/claims',body)
    assert post(client,'/api/claims',body)==claim
    old=client.get('/api/nodes/sample:claim').json()
    assert old['properties']['status']=='SUPERSEDED' and old['properties']['text']==original['properties']['text']
    assert old['created_at']==original['created_at']
    evidence=client.get('/api/evidence/confirmed:claim').json()
    assert {'sample:claim','sample:source','confirmed:source','confirmed:message'} <= {n['id'] for n in evidence['nodes']}
    assert client.post('/api/claims',json={**body,'text':'Changed in place'}).status_code==409
    assert client.post('/api/claims',json={**body,'id':'competing:claim'}).status_code==409
    assert client.get('/api/nodes/competing:claim').status_code==404
    assert client.put('/api/nodes/confirmed:source',json={'type':'Source','properties':{'name':'Alter evidence'}}).status_code==409
    for status in ('UNVERIFIED','REFUTED'):
        created=post(client,'/api/claims',{**body,'id':status,'status':status,'supersedes_id':None})
        assert created['properties']['status']==status
    assert client.post('/api/claims',json={**body,'id':'bad','status':'CERTAIN'}).status_code==422
    assert client.post('/api/claims',json={**body,'id':'bad','status':'SUPERSEDED'}).status_code==422
    node(client,'decision','Decision',summary='A manually supplied historical decision')
    edge(client,'decision','MOTIVATED_BY','confirmed:claim')
    assert 'confirmed:source' in {n['id'] for n in client.get('/api/evidence/decision').json()['nodes']}


def test_conversation_message_context_atomicity_and_pagination(client):
    seed(client.app.state.service)
    result=post(client,'/api/conversations/sample:conversation/messages',{'id':'assistant:message','role':'assistant','content':'Explicit test fixture only.'})
    assert result['properties']['bot_id']=='sample:bot'
    context=client.get('/api/conversations/sample:conversation/context').json()
    assert {'sample:bot','sample:message','sample:appointment','sample:transport','sample:claim'} <= {n['id'] for n in context['nodes']}
    assert 'AUTHORED_BY' in {e['type'] for e in context['edges']}
    page=client.get('/api/conversations/sample:conversation/messages?limit=1').json()
    assert len(page['items'])==1 and page['next_offset']==1
    next_page=client.get('/api/conversations/sample:conversation/messages?limit=1&offset=1').json()
    assert len(next_page['items'])==1 and next_page['items'][0]['id']!=page['items'][0]['id']
    bad=client.post('/api/conversations/sample:conversation/messages',json={'id':'missing:message','role':'user','content':'x','mentioned_ids':['absent']})
    assert bad.status_code==404 and client.get('/api/nodes/missing:message').status_code==404
    assert client.post('/api/conversations/sample:conversation/messages',json={'id':'assistant:message','role':'assistant','content':'rewritten'}).status_code==409
    assert client.get('/api/conversations/sample:conversation').status_code==200
    assert client.get('/api/conversations/sample:priya').status_code==422


def test_restart_persistence_in_fresh_backend_process(client,settings):
    seed(client.app.state.service)
    code='''import sys,json
from fastapi.testclient import TestClient
from backend.orbit.api import create_app
from backend.orbit.config import Settings
with TestClient(create_app(Settings.model_validate_json(sys.argv[1]))) as c:
 r=c.get('/api/conversations/sample:conversation/context')
 assert r.status_code==200,r.text
 print(json.dumps(sorted(n['id'] for n in r.json()['nodes'])))
'''
    result=subprocess.run([sys.executable,'-c',code,settings.model_dump_json()],capture_output=True,text=True,check=True)
    assert 'sample:message' in json.loads(result.stdout)


def test_seed_is_idempotent(client):
    first=seed(client.app.state.service)
    second=seed(client.app.state.service)
    assert [n['id'] for n in first['nodes']]==[n['id'] for n in second['nodes']]
    assert [e['id'] for e in first['edges']]==[e['id'] for e in second['edges']]
    assert client.app.state.service.repo.db.execute('MATCH (n:Entity) RETURN count(n)',read=True)==[[10]]


def test_invalid_input_conflicts_missing_and_parameterization(client):
    for kind in ('Unknown','Person`) DELETE n //','Claim','Message','Conversation'):
        assert client.put('/api/nodes/x',json={'type':kind,'properties':{}}).status_code==422
    for props in ({'unknown':'value'},{'created_at':0},{'name':None},{'name':'  '}):
        assert client.put('/api/nodes/x',json={'type':'Person','properties':props}).status_code==422
    assert client.get('/api/nodes/absent').status_code==404
    text="Alice ' MATCH (n) DETACH DELETE n //"
    assert node(client,'person',name=text)['properties']['name']==text
    assert client.put('/api/nodes/person',json={'type':'Task','properties':{}}).status_code==409
    assert client.put('/api/relationships',json={'source':'person','target':'absent','type':'RELATED_TO'}).status_code==404
    assert client.put('/api/relationships',json={'source':'person','target':'person','type':'ASSIGNED_TO'}).status_code==422
    for hops in (0,5,'2'):
        assert client.post('/api/graph/traverse',json={'root_id':'person','hops':hops}).status_code==422
    assert client.put('/api/nodes/x',json={'type':'Person','properties':{}},headers={'Origin':'https://untrusted.example'}).status_code==403
    assert client.delete('/api/nodes/person').status_code==200
    assert client.get('/api/nodes/person').status_code==404


def test_database_unavailable_returns_503_and_safe_startup():
    with TestClient(create_app(Settings(port=1,connect_timeout=.1,socket_timeout=.1))) as client:
        r=client.get('/api/health')
        assert r.status_code==503 and r.json()['error']['code']=='database_unavailable'
        assert client.put('/api/nodes/x',json={'type':'Person','properties':{'name':'No fallback'}}).status_code==503

def test_competing_claim_updates_are_atomic(client):
    seed(client.app.state.service)
    now=datetime.now(timezone.utc).isoformat()
    node(client,'new:source','Source',kind='MANUAL',observed_at=now)
    base={'text':'Explicit confirmation','status':'CONFIRMED','source_id':'new:source',
        'subject_ids':['sample:priya'],'observed_at':now,'supersedes_id':'sample:claim'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda i:client.post('/api/claims',json={**base,'id':f'new:claim{i}'}),range(2)))
    assert sorted(r.status_code for r in results)==[200,409]
    winner=next(r.json()['id'] for r in results if r.status_code==200)
    assert client.get('/api/nodes/sample:claim').json()['properties']['superseded_by']==winner
    losers=[f'new:claim{i}' for i in range(2) if f'new:claim{i}'!=winner]
    assert client.get('/api/nodes/'+losers[0]).status_code==404


def test_four_hop_boundaries_and_unverified_assignments(client):
    for i in range(6):
        node(client,f'chain:{i}','Task',name=f'Task {i}')
    for i in range(5):
        edge(client,f'chain:{i}','DEPENDS_ON',f'chain:{i+1}')
    result=client.get('/api/nodes/chain:0/dependencies?hops=4').json()
    assert {n['id'] for n in result['nodes']}=={f'chain:{i}' for i in range(5)}
    assert 'chain:5' not in {n['id'] for n in result['nodes']}
    node(client,'person',name='Person')
    assigned=edge(client,'chain:0','ASSIGNED_TO','person')
    assert assigned['properties']['evidence_state']=='UNVERIFIED'
    body={'source':'chain:0','type':'ASSIGNED_TO','target':'person'}
    assert client.put('/api/relationships',json={**body,'properties':{'evidence_state':'CONFIRMED'}}).status_code==200
    patched=client.put('/api/relationships',json={**body,'properties':{'note':'Explicitly supplied confirmation'}})
    assert patched.json()['properties']['evidence_state']=='CONFIRMED'
    assert client.put('/api/relationships',json={'source':'chain:0','type':'ASSIGNED_TO','target':'person',
        'properties':{'evidence_state':'GUESS'}}).status_code==422
    assert client.delete('/api/nodes/chain:0').status_code==409

def test_entity_discovery_search_filter_pagination(client):
    seed(client.app.state.service)
    first=client.get('/api/nodes?limit=2').json()
    second=client.get('/api/nodes?limit=2&offset=2').json()
    assert first['next_offset']==2
    assert not {n['id'] for n in first['items']} & {n['id'] for n in second['items']}
    people=client.get('/api/nodes?type=Person').json()['items']
    assert {n['id'] for n in people}=={'sample:priya','sample:dad'}
    assert [n['id'] for n in client.get('/api/nodes?q=HOSPITAL&type=Event').json()['items']]==['sample:appointment']
    assert client.get('/api/nodes',params={'q':"' MATCH (n) DELETE n //"}).json()['items']==[]
    assert client.get('/api/nodes?type=Unknown').status_code==422
    assert client.get('/api/nodes?limit=501').status_code==422
    assert client.get('/api/nodes?offset=-1').status_code==422
