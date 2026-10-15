"""Execute the reviewed demo-only cut after explicit human approval."""
import json
import time
from backend.sandbox import SESSION, ROOT, probe
from backend.graph import query, literal

def apply(approver):
    if not approver.strip():
        raise ValueError('Human approver required')
    pending = json.loads((ROOT/'.aws/pending-decision.json').read_text())
    decision = pending['decision']
    assert query(f'MATCH (d:Decision {{id:{literal(decision)}, status:"awaiting_approval"}}) RETURN d.id')[1]
    iam = SESSION.client('iam')
    original = iam.get_role_policy(RoleName='pathlock-demo-app', PolicyName='DemoUnsafeRoute')['PolicyDocument']
    state = json.loads((ROOT/'.aws/sandbox.json').read_text())
    if original != {'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':'sts:AssumeRole','Resource':state['target_arn']}]}:
        raise RuntimeError('Policy changed since planning; investigate again')
    if probe('order') != {'order':'582','status':'SHIPPED'} or probe('probe').get('access') != 'granted':
        raise RuntimeError('Preconditions changed; investigate again')
    (ROOT/'.aws/rollback-policy.json').write_text(json.dumps(original))
    query(f'MATCH (d:Decision {{id:{literal(decision)}}}) CREATE (a:Approval {{person:{literal(approver)}, action:"PutRolePolicy:DemoUnsafeRoute:ExplicitDeny"}}), (d)-[:APPROVED_BY]->(a) SET d.status="applying"')
    state = json.loads((ROOT/'.aws/sandbox.json').read_text())
    iam.put_role_policy(RoleName='pathlock-demo-app', PolicyName='DemoUnsafeRoute', PolicyDocument=json.dumps({'Version':'2012-10-17','Statement':[{'Effect':'Deny','Action':'sts:AssumeRole','Resource':state['target_arn']}]}))
    for attempt in range(24):
        security = probe('probe')
        business = probe('order')
        if security.get('access') == 'denied' and business == {'order':'582','status':'SHIPPED'}:
            break
        time.sleep(5)
    else:
        query(f'MATCH (d:Decision {{id:{literal(decision)}}}) SET d.status="verification_failed"')
        raise RuntimeError('Verification failed; rollback policy retained locally')
    policy = iam.get_role_policy(RoleName='pathlock-demo-app', PolicyName='DemoUnsafeRoute')['PolicyDocument']
    assert policy['Statement'][0]['Effect'] == 'Deny'
    query('MATCH (:Identity {id:"pathlock:app-role"})-[r:CAN_ASSUME]->(:Identity {id:"pathlock:analytics"}) DELETE r')
    query(f'MATCH (d:Decision {{id:{literal(decision)}}}) CREATE (r:Remediation {{action:"ExplicitDenyAssumeRole", changes:1}}), (v:Verification {{security:"PASS", business:"PASS"}}), (d)-[:SELECTED]->(r), (r)-[:VERIFIED_BY]->(v) SET d.status="verified"')
    print('Security PASS; business PASS; outcome persisted in FalkorDB.')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--approved-by', required=True)
    apply(parser.parse_args().approved_by)
