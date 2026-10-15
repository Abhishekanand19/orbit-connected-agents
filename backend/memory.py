import json
import time
import uuid
from backend.sandbox import SESSION, ROOT, policy, probe, TAGS
from backend.graph import query, literal, sync
from backend.agents import investigate, plan

def recall():
    return {
        'protected':query('MATCH (:Project {id:"pathlock:project"})-[:MUST_PRESERVE]->(c) RETURN c.name')[1],
        'owner':query('MATCH (t)-[:OWNS]->(:Project {id:"pathlock:project"}) RETURN t.name')[1],
        'verified':query('MATCH (d:Decision)-[:SELECTED]->(:Remediation)-[:VERIFIED_BY]->(v:Verification) WHERE d.status="verified" RETURN d.id, v.security, v.business')[1]
    }

def new_session():
    memory=recall()
    if not memory['verified']:
        raise RuntimeError('Complete first verification before starting session two')
    state=json.loads((ROOT/'.aws/sandbox.json').read_text())
    if state.get('scenario') == 2:
        raise RuntimeError('Reporting scenario already exists; use Analyze Cloud')
    iam=SESSION.client('iam')
    name='pathlock-demo-reporting'
    trust={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'AWS':state['app_arn']},'Action':'sts:AssumeRole'}]}
    role=iam.create_role(RoleName=name,AssumeRolePolicyDocument=json.dumps(trust),Tags=TAGS)['Role']['Arn']
    iam.put_role_policy(RoleName=name,PolicyName='DemoSecretRead',PolicyDocument=policy('secretsmanager:GetSecretValue',state['secret_arn']))
    iam.put_role_policy(RoleName=state['app_role'],PolicyName='DemoUnsafeRoute',PolicyDocument=policy('sts:AssumeRole',role))
    # Retain the first containment when introducing a distinct reporting route.
    iam.put_role_policy(RoleName=state['app_role'],PolicyName='PreviousAnalyticsContainment',PolicyDocument=json.dumps({'Version':'2012-10-17','Statement':[{'Effect':'Deny','Action':'sts:AssumeRole','Resource':state['target_arn']}]}))
    state.update(target_role=name,target_arn=role,scenario=2)
    SESSION.client('lambda').update_function_configuration(FunctionName=state['function'],Environment={'Variables':{'TARGET_ROLE':role,'SECRET_ARN':state['secret_arn'],'ORDERS_TABLE':'pathlock-demo-orders'}})
    SESSION.client('lambda').get_waiter('function_updated_v2').wait(FunctionName=state['function'])
    (ROOT/'.aws/sandbox.json').write_text(json.dumps(state,indent=2))
    session='session:'+str(uuid.uuid4())
    query(f'CREATE (s:Session {{id:{literal(session)}, scenario:2}})')
    for previous in memory['verified']:
        query(f'MATCH (s:Session {{id:{literal(session)}}}),(d:Decision {{id:{literal(previous[0])}}}) MERGE (s)-[:PREVIOUS_DECISION]->(d)')
    for attempt in range(24):
        try:
            if probe('probe').get('access')=='granted':break
        except RuntimeError:
            if attempt == 23:raise
        time.sleep(5)
    else:raise RuntimeError('Reporting exposure did not become available')
    sync()
    decision=plan(investigate())
    assert decision['selected']['business'] and recall()['verified']
    return {'memory':memory,'decision':decision}

if __name__=='__main__':
    result=new_session()
    print('Phase 6 PASS: real reporting route; previous verification and protected capability loaded; shared finding planned.')
