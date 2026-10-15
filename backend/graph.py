import json
import redis
from backend.sandbox import SESSION, ROOT

CLIENT = redis.Redis(host='localhost', port=6379, decode_responses=True)

def query(statement):
    return CLIENT.execute_command('GRAPH.QUERY', 'pathlock', statement)

def literal(value):
    return json.dumps(value)

def sync():
    state = json.loads((ROOT/'.aws/sandbox.json').read_text())
    iam = SESSION.client('iam')
    role = iam.get_role(RoleName=state['target_role'])['Role']
    trust = role['AssumeRolePolicyDocument']
    unsafe = iam.get_role_policy(RoleName=state['app_role'], PolicyName='DemoUnsafeRoute')['PolicyDocument']
    orders = iam.get_role_policy(RoleName=state['app_role'], PolicyName='OrderLookup')['PolicyDocument']
    secret = iam.get_role_policy(RoleName=state['target_role'], PolicyName='DemoSecretRead')['PolicyDocument']
    function = SESSION.client('lambda').get_function_configuration(FunctionName=state['function'])
    assert function['Role'] == state['app_arn']
    assert unsafe['Statement'][0]['Resource'] == state['target_arn']
    assert trust['Statement'][0]['Principal']['AWS'] == state['app_arn']
    assert orders['Statement'][0]['Resource'] == state['table_arn']
    assert secret['Statement'][0]['Resource'] == state['secret_arn']
    nodes = [('project','Project','PathLock'),('team','Team','Commerce / Platform'),('app','Application','Order App'),('app-role','Identity','Order Access'),('analytics','Identity','Analytics Access'),('orders','CloudResource','Orders Database'),('secret','SensitiveResource','Private Secret'),('lookup','BusinessCapability','Order Lookup')]
    for key, label, name in nodes:
        query(f'MERGE (n:{label} {{id:{literal("pathlock:"+key)}}}) SET n.name={literal(name)}')
    query('MATCH (:Identity {id:"pathlock:app-role"})-[r:CAN_ASSUME]->() DELETE r')
    edges = [('team','OWNS','project'),('project','CONTAINS','app'),('app','RUNS_AS','app-role'),('analytics','CAN_ACCESS','secret'),('app-role','CAN_ACCESS','orders'),('lookup','REQUIRES','orders'),('project','MUST_PRESERVE','lookup')]
    if unsafe['Statement'][0]['Effect'] == 'Allow':
        edges.append(('app-role','CAN_ASSUME','analytics'))
    if state.get('scenario') == 2:
        query('MATCH (n:Identity {id:"pathlock:analytics"}) SET n.name="Reporting Access"')
    for source, kind, target in edges:
        query(f'MATCH (a {{id:{literal("pathlock:"+source)}}}), (b {{id:{literal("pathlock:"+target)}}}) MERGE (a)-[:{kind}]->(b)')
    return query('MATCH p=(a:Application {id:"pathlock:app"})-[:RUNS_AS|CAN_ASSUME|CAN_ACCESS*1..6]->(s:SensitiveResource) RETURN [n IN nodes(p) | n.name]')

if __name__ == '__main__':
    result = sync()
    assert len(result[1]) == 1, 'Expected exactly one observed dangerous route'
    assert result[1][0][0] == '[Order App, Order Access, Analytics Access, Private Secret]'
    print('Phase 2 PASS: FalkorDB found the observed four-node permission path.')
