"""Deterministic evidence tools for the Investigator and Remediator."""
import json
import uuid
from backend.graph import query, literal
from backend.sandbox import ROOT

def investigate():
    paths = query('MATCH p=(a:Application {id:"pathlock:app"})-[:RUNS_AS|CAN_ASSUME|CAN_ACCESS*1..6]->(s:SensitiveResource {id:"pathlock:secret"}) RETURN [r IN relationships(p) | type(r)]')[1]
    if not paths:
        raise RuntimeError('No dangerous route observed')
    finding = 'finding:' + str(uuid.uuid4())
    query(f'MATCH (a:Application {{id:"pathlock:app"}}) CREATE (f:Finding {{id:{literal(finding)}, evidence:{literal(json.dumps(paths))}, agent:"Investigator"}}), (a)-[:FOUND]->(f)')
    return finding

def plan(finding):
    assert query(f'MATCH (f:Finding {{id:{literal(finding)}}}) RETURN f.id')[1]
    constraints = query('MATCH (:Project {id:"pathlock:project"})-[:MUST_PRESERVE]->(:BusinessCapability)-[:REQUIRES]->(r) RETURN r.id')[1]
    assert constraints, 'No protected business capability available'
    edges = query('MATCH (a)-[r:RUNS_AS|CAN_ASSUME|CAN_ACCESS]->(b) WHERE a.id STARTS WITH "pathlock:" AND b.id STARTS WITH "pathlock:" RETURN a.id, type(r), b.id')[1]
    def reaches(target, cut):
        visited = set()
        todo = ['pathlock:app']
        while todo:
            node = todo.pop()
            if node == target:
                return True
            if node in visited:
                continue
            visited.add(node)
            todo.extend(b for a, kind, b in edges if a == node and (a,kind,b) not in cut)
        return False
    alternatives = []
    cuts = [('Disable application', {tuple(e) for e in edges if e[0]=='pathlock:app'}), ('Remove all application permissions', {tuple(e) for e in edges if e[0]=='pathlock:app-role'}), ('Deny only elevated role assumption', {('pathlock:app-role','CAN_ASSUME','pathlock:analytics')})]
    for name, cut in cuts:
        alternatives.append({'name':name, 'secure':not reaches('pathlock:secret',cut), 'business':all(reaches(row[0],cut) for row in constraints), 'changes':len(cut)})
    valid = [a for a in alternatives if a['secure'] and a['business']]
    assert valid, 'No safe intervention'
    selected = min(valid, key=lambda a:a['changes'])
    decision = 'decision:' + str(uuid.uuid4())
    query(f'MATCH (f:Finding {{id:{literal(finding)}}}), (c:BusinessCapability {{id:"pathlock:lookup"}}) CREATE (d:Decision {{id:{literal(decision)}, alternatives:{literal(json.dumps(alternatives))}, selected:{literal(selected["name"])}, status:"awaiting_approval", agent:"Remediator"}}), (f)-[:CAUSED]->(d), (d)-[:MUST_PRESERVE]->(c)')
    result = {'finding':finding,'decision':decision,'alternatives':alternatives,'selected':selected,'action':{'role':'pathlock-demo-app','policy':'DemoUnsafeRoute','operation':'PutRolePolicy:ExplicitDeny'}}
    (ROOT/'.aws/pending-decision.json').write_text(json.dumps(result,indent=2))
    return result

if __name__ == '__main__':
    result = plan(investigate())
    assert result['selected']['changes']==1
    assert [a['business'] for a in result['alternatives']]==[False,False,True]
    print('Phase 3 PASS: Investigator finding persisted and loaded by Remediator.')
    print('Phase 4 PASS: three cuts evaluated; only narrow cut preserves Order Lookup.')
    print('Pending human approval: delete DemoUnsafeRoute from pathlock-demo-app.')
