"""All application Cypher lives here. Only validated enum labels and bounded ints
are interpolated; IDs, text, properties and timestamps use query parameters.
"""
from uuid import UUID, uuid5
from .database import Database, GraphError
from .models import EntityType, RelationType, TraversalRequest

EDGE_NAMESPACE = UUID('993ef884-0bba-4c06-ad71-a55e667ff5fb')

def edge_id(source, kind, target):
    return str(uuid5(EDGE_NAMESPACE, f'{source}|{kind}|{target}'))

def node_view(properties):
    p = dict(properties)
    result = {key:p.pop(key) for key in ('id','created_at','updated_at')}
    result['type'] = p.pop('entity_type')
    p.pop('fingerprint', None)
    result['properties'] = p
    return result

def edge_view(properties):
    p = dict(properties)
    result = {key:p.pop(key) for key in ('id','source','target','created_at','updated_at')}
    result['type'] = p.pop('relation_type')
    result['properties'] = p
    return result

class GraphRepository:
    def __init__(self, db: Database):
        self.db = db

    def search_nodes(self, query='', kind=None, offset=0, limit=30):
        """Read-only discovery for the graph picker; stable paginated ordering."""
        rows = self.db.execute("""MATCH (n:Entity)
            WHERE ($kind = '' OR n.entity_type=$kind) AND
                (toLower(n.id) CONTAINS $query OR
                 toLower(coalesce(n.name,n.title,n.text,n.content,'')) CONTAINS $query)
            RETURN properties(n)
            ORDER BY coalesce(n.name,n.title,n.text,n.content,n.id), n.id
            SKIP $offset LIMIT $limit""",
            {'query':query.lower(), 'kind':kind.value if kind else '',
             'offset':offset, 'limit':limit+1},read=True)
        return {'items':[node_view(r[0]) for r in rows[:limit]],
                'next_offset':offset+limit if len(rows)>limit else None}

    def get_node(self, node_id):
        rows = self.db.execute('MATCH (n:Entity {id:$id}) RETURN properties(n)', {'id':node_id}, read=True)
        if not rows:
            raise GraphError(404, 'node_not_found', f'Entity {node_id} does not exist.')
        return node_view(rows[0][0])

    def upsert_node(self, node_id, kind: EntityType, properties):
        guard = 'WITH n WHERE NOT (n)<-[:SUPPORTED_BY|VERIFIED_BY]-(:Claim)' if kind == EntityType.Source else ''
        rows = self.db.execute(f'''MERGE (n:Entity:{kind.value} {{id:$id}})
            ON CREATE SET n.created_at=timestamp(), n.entity_type=$kind
            {guard}
            SET n += $properties, n.updated_at=timestamp()
            RETURN properties(n)''', {'id':node_id,'kind':kind.value,'properties':properties})
        if not rows:
            raise GraphError(409,'immutable_source','The source is now cited by a claim.')
        return node_view(rows[0][0])

    def upsert_edge(self, source, kind: RelationType, target, properties):
        params = {'source':source, 'target':target, 'kind':kind.value,
                  'id':edge_id(source,kind.value,target), 'properties':properties}
        rows = self.db.execute(f'''MATCH (a:Entity {{id:$source}}), (b:Entity {{id:$target}})
            MERGE (a)-[r:{kind.value}]->(b)
            ON CREATE SET r.id=$id, r.created_at=timestamp(), r.source=$source,
                r.target=$target, r.relation_type=$kind, r.evidence_state="UNVERIFIED"
            SET r += $properties, r.updated_at=timestamp()
            RETURN properties(r)''', params)
        if not rows:
            raise GraphError(404,'node_not_found','One or both endpoints do not exist.')
        return edge_view(rows[0][0])

    def get_edge(self, relationship_id):
        rows = self.db.execute('MATCH ()-[r]->() WHERE r.id=$id RETURN properties(r)', {'id':relationship_id}, read=True)
        if not rows:
            raise GraphError(404,'edge_not_found','Relationship does not exist.')
        return edge_view(rows[0][0])

    def delete_edge(self, relationship_id):
        self.db.execute('MATCH ()-[r]->() WHERE r.id=$id DELETE r', {'id':relationship_id})

    def delete_node(self, node_id):
        rows = self.db.execute('''MATCH (n:Entity {id:$id}) WHERE indegree(n)=0 AND outdegree(n)=0
            DELETE n RETURN $id''', {'id':node_id})
        if not rows:
            raise GraphError(409,'node_connected','Only disconnected, mutable entities can be deleted.')

    def atomic_record(self, node_id, kind, properties, fingerprint, references, edges, supersedes=None):
        """Guard all references/identity BEFORE any write; one atomic Cypher statement.
        edges contain (source ID, validated relationship enum, target ID).
        Immutable-record retries return the original node without altering its payload.
        """
        params = {'id':node_id,'kind':kind.value,'properties':properties,'fingerprint':fingerprint}
        clauses = ['OPTIONAL MATCH (existing:Entity {id:$id})',
            'WITH existing WHERE existing IS NULL OR (existing.entity_type=$kind AND existing.fingerprint=$fingerprint)']
        variables = {node_id:'n'}
        for i, (ref_id, ref_type) in enumerate(references.items()):
            params[f'ref{i}'] = ref_id
            # ref_type comes from a validated/retrieved EntityType.
            label = EntityType(ref_type).value
            clauses.append(f'MATCH (v{i}:Entity:{label} {{id:$ref{i}}})')
            variables[ref_id] = f'v{i}'
        if supersedes:
            old = variables[supersedes]
            clauses.append(f'WITH * WHERE {old}.status <> "SUPERSEDED" OR {old}.superseded_by=$id')
        clauses.append(f'''MERGE (n:Entity:{kind.value} {{id:$id}})
            ON CREATE SET n += $properties, n.entity_type=$kind, n.fingerprint=$fingerprint,
                n.created_at=timestamp(), n.updated_at=timestamp()''')
        for i,(source,relation,target) in enumerate(edges):
            relation = RelationType(relation).value
            params[f'e{i}'] = {'id':edge_id(source,relation,target), 'source':source,
                'target':target, 'relation_type':relation}
            clauses.append(f'''MERGE ({variables[source]})-[e{i}:{relation}]->({variables[target]})
                ON CREATE SET e{i} += $e{i}, e{i}.created_at=timestamp(), e{i}.updated_at=timestamp()''')
        if supersedes:
            old = variables[supersedes]
            clauses.append(f'''SET {old}.updated_at=CASE WHEN {old}.status="SUPERSEDED" THEN {old}.updated_at ELSE timestamp() END,
                {old}.status="SUPERSEDED", {old}.superseded_by=$id''')
        clauses.append('RETURN properties(n)')
        rows = self.db.execute('\n'.join(clauses),params)
        if not rows:
            raise GraphError(409,'record_conflict','ID has different contents, a reference changed, or the claim was already superseded.')
        return node_view(rows[0][0])

    def traverse(self, request: TraversalRequest):
        root = self.get_node(request.root_id)
        if request.target_id:
            self.get_node(request.target_id)
        kinds = ':' + '|'.join(t.value for t in request.relationship_types) if request.relationship_types else ''
        edge = f'[{kinds}*1..{request.hops}]'
        pattern = {'both':f'-{edge}-', 'outgoing':f'-{edge}->', 'incoming':f'<-{edge}-'}[request.direction]
        target_filter = 'WHERE b.id=$target' if request.target_id else ''
        rows = self.db.execute(f'''MATCH p=(a:Entity {{id:$root}}){pattern}(b:Entity)
            {target_filter}
            RETURN [n IN nodes(p) | properties(n)], [r IN relationships(p) | properties(r)]
            LIMIT $limit''', {'root':request.root_id,'target':request.target_id,'limit':request.limit+1}, read=True)
        nodes = {root['id']:root}
        edges, paths = {}, []
        for ns, es in rows[:request.limit]:
            for n in ns:
                nodes[n['id']] = node_view(n)
            for e in es:
                edges[e['id']] = edge_view(e)
            paths.append({'node_ids':[n['id'] for n in ns], 'edge_ids':[e['id'] for e in es]})
        return {'nodes':sorted(nodes.values(),key=lambda n:n['id']),
            'edges':sorted(edges.values(),key=lambda e:e['id']), 'paths':paths,
            'truncated':len(rows)>request.limit}

    def messages(self, conversation_id, offset, limit):
        rows = self.db.execute('''MATCH (:Conversation {id:$id})-[:HAS_MESSAGE]->(m:Message)
            RETURN properties(m) ORDER BY m.created_at, m.id SKIP $offset LIMIT $limit''',
            {'id':conversation_id,'offset':offset,'limit':limit+1},read=True)
        return {'items':[node_view(r[0]) for r in rows[:limit]],
                'next_offset':offset+limit if len(rows)>limit else None}
