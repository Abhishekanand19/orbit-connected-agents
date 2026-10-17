from .story_api import request_service
"""Read-only receipts from durable graph records; no model-generated reasoning."""
import json
from fastapi import Request
from .database import GraphError
from .repository import node_view, edge_view


def evidence_snapshot(service, ids, edge_ids=()):
    nodes = {}
    edges = {}
    for id in set(ids):
        try:
            nodes[id] = service.require(id)
        except GraphError as error:
            if error.status != 404: raise
    for id in set(edge_ids):
        try:
            e = service.repo.get_edge(id)
            edges[id] = e
            for endpoint in (e['source'], e['target']):
                nodes[endpoint] = service.require(endpoint)
        except GraphError as error:
            if error.status != 404: raise
    # Include actual claim/source provenance, with a strict bound.
    rows = service.repo.db.execute('''MATCH (n:Entity)-[r:SUPPORTED_BY|VERIFIED_BY|MENTIONED_IN]->(s:Entity)
        WHERE n.id IN $ids RETURN properties(r),properties(s) LIMIT 100''', {'ids': list(nodes)}, read=True)
    for rel, props in rows:
        e = edge_view(rel); n = node_view(props)
        edges[e['id']] = e; nodes[n['id']] = n
    # Do not recursively embed older receipts inside every new snapshot.
    for n in nodes.values():
        n['properties'].pop('evidence_snapshot', None)
    return {'nodes': list(nodes.values()), 'edges': list(edges.values())}


def impact_snapshot(service, result):
    ids = [result.trigger_id, result.trigger_claim_id, *result.constraints]
    edges = list(result.constraint_edge_ids)
    for path in result.affected:
        ids.extend(path.node_ids); edges.extend(path.edge_ids)
    for alternative in result.alternatives:
        ids.extend([alternative.entity_id, *alternative.constraint_ids]); edges.extend(alternative.edge_ids)
    return evidence_snapshot(service, ids, edges)


def label(n):
    p = n['properties']
    return p.get('name') or p.get('text') or p.get('summary') or p.get('content') or n['id']


class Receipts:
    def __init__(self, service):
        self.s = service; self.db = service.repo.db

    def list(self):
        rows = self.db.execute("""MATCH (n:Entity) WHERE n.entity_type='Decision' OR n.record_kind='AGENT_FINDING'
            RETURN properties(n) ORDER BY n.created_at DESC LIMIT 40""", read=True)
        return [{'id': n['id'], 'title': label(n), 'status': self.status(n['properties'])}
                for n in map(lambda r: node_view(r[0]), rows)]

    @staticmethod
    def status(p):
        raw = p.get('status', 'PROPOSED')
        status = {'ACT': 'PROPOSED', 'WAIT': 'WAITING', 'CONFLICT': 'WAITING',
                  'NO_CHANGE': 'WAITING', 'AWAITING_APPROVAL': 'WAITING'}.get(raw, raw)
        if status == 'VERIFIED' and not json.loads(p.get('verification', '{}')).get('verified'):
            return 'UNKNOWN'
        return status

    def get(self, id):
        n = self.s.require(id); p = n['properties']
        if n['type'] not in ('Decision', 'Action') and p.get('record_kind') != 'AGENT_FINDING':
            raise GraphError(404, 'receipt_not_found', 'No decision receipt exists for this record.')
        analysis = json.loads(p.get('analysis', '{}'))
        spec = json.loads(p.get('spec', '{}'))
        decision = self.s.require(spec['decision_id']) if spec.get('decision_id') else None
        if decision:
            analysis = json.loads(decision['properties'].get('analysis', '{}'))
        linked = self.db.execute('''MATCH (a:Entity {id:$id})-[r]-(b:Entity)
            RETURN properties(r),properties(b) LIMIT 100''', {'id': id}, read=True)
        neighbors = [node_view(row[1]) for row in linked]
        relationships = [edge_view(row[0]) for row in linked]
        message_id = p.get('message_id') or next((e['target'] for e in relationships
            if e['source'] == id and e['type'] == 'MENTIONED_IN'), '')
        snapshot = json.loads(p.get('evidence_snapshot', 'null'))
        graph = snapshot or evidence_snapshot(self.s,
            [x['id'] for x in neighbors] + [i for path in analysis.get('affected', []) for i in path['node_ids']],
            [i for path in analysis.get('affected', []) for i in path['edge_ids']])
        by_id = {x['id']: x for x in graph['nodes']}
        by_edge = {x['id']: x for x in graph['edges']}
        if decision:
            earlier = json.loads(decision['properties'].get('evidence_snapshot', 'null'))
            if earlier:
                by_id.update({x['id']: x for x in earlier['nodes']})
                by_edge.update({x['id']: x for x in earlier['edges']})
                graph = {'nodes': list(by_id.values()), 'edges': list(by_edge.values())}
        paths = []
        for path in analysis.get('affected', []):
            segments = []
            for index, edge_id in enumerate(path['edge_ids']):
                edge = by_edge.get(edge_id)
                pair = path['node_ids'][index:index+2]
                if edge and len(pair) == 2 and set(pair) == {edge['source'], edge['target']}:
                    segments.append({'edge': edge, 'from': pair[0], 'to': pair[1]})
            paths.append({**path, 'labels': [label(by_id[i]) if i in by_id else i for i in path['node_ids']],
                          'segments': segments, 'complete': len(segments) == len(path['edge_ids'])})
        # Cited prior memory is distinct from merely neighboring a decision.
        prior = []
        for edge, other in zip(relationships, neighbors):
            if edge['source'] == id and edge['type'] in ('SUPPORTED_BY', 'MOTIVATED_BY') and other['type'] in ('Decision', 'Action', 'Outcome'):
                prior.append({'id': other['id'], 'title': label(other), 'relationship': edge,
                              'retrieval': None})
        agents = []
        runs = self.db.execute('''MATCH (r:Task)-[:PRODUCED]->(f:Source)
            WHERE f.id=$id OR (f.message_id=$message AND $message<>'')
            RETURN properties(r),properties(f) LIMIT 20''',
            {'id': id, 'message': message_id}, read=True)
        for run, finding in runs:
            agents.append({'name': run.get('owner'), 'status': run.get('status'), 'run_id': run['id']})
            retrieved = json.loads(run.get('retrieved_ids', '[]'))
            for item in prior:
                if item['id'] in retrieved:
                    item['retrieval'] = {'run_id': run['id'], 'at': run.get('retrieved_at'), 'conversation_id': run.get('conversation_id')}
        plans = self.db.execute('MATCH (p:OrbitActionPlan {message_id:$message}) RETURN properties(p)', {'message': message_id}, read=True)
        for (plan,) in plans:
            for item in prior:
                if item['id'] in json.loads(plan.get('retrieved_ids', '[]')):
                    item['retrieval'] = {'run_id': plan['id'], 'at': plan['created_at'], 'conversation_id': plan['conversation_id']}
        trigger_id = analysis.get('trigger_claim_id') or message_id
        trigger = by_id.get(trigger_id)
        if not trigger and trigger_id:
            try: trigger = self.s.require(trigger_id)
            except GraphError as error:
                if error.status != 404: raise
        reason = p.get('error') or analysis.get('reason') or spec.get('reason') or p.get('description') or p.get('summary') or 'No rationale was recorded.'
        return {'id': id, 'title': label(n), 'status': self.status(p), 'recorded_status': p.get('status'),
                'created_at': n['created_at'], 'reason': reason, 'trigger': label(trigger) if trigger else None,
                'proposal_reason': spec.get('reason'), 'proposed_payload': spec.get('payload'),
                'graph': graph, 'evidence_basis': 'Recorded at decision time' if snapshot else 'Current graph; historical snapshot unavailable',
                'paths': paths, 'alternatives': analysis.get('alternatives', []), 'evidence_status': analysis.get('evidence', {}),
                'agents': agents, 'previous': prior, 'relationships': relationships,
                'tool': p.get('tool'), 'approval': p.get('approved_at'), 'history': json.loads(p.get('history', '[]')),
                'execution': json.loads(p.get('receipt', '{}')), 'verification': json.loads(p.get('verification', '{}')),
                'transport': p.get('transport'), 'error': p.get('error'),
                'decision_id': spec.get('decision_id'),
                'outcomes': [x for x in neighbors if x['type'] == 'Outcome']}


def mount_receipts(app):
    @app.get('/api/receipts')
    def list_receipts(request: Request):
        return {'receipts': Receipts(request_service(request)).list()}

    @app.get('/api/receipts/{record_id}')
    def receipt(record_id: str, request: Request):
        return Receipts(request_service(request)).get(record_id)
