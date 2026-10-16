"""Bounded graph retrieval, shared by extraction and response generation."""
import re
from .models import TraversalRequest
from .repository import node_view

def history(service, conversation):
    rows=service.repo.db.execute('MATCH (:Conversation {id:$id})-[:HAS_MESSAGE]->(m:Message) RETURN properties(m) ORDER BY m.created_at DESC, m.id DESC LIMIT 16',{'id':conversation},read=True)
    return [node_view(r[0]) for r in reversed(rows)]

def retrieve(service, text, conversation):
    nodes,edges={},{}
    stop={'what','when','where','who','does','did','the','and','that','this','with','have','about','tell','remember','please','was','are'}
    terms=list(dict.fromkeys(t.casefold() for t in re.findall(r'[\w-]{3,}',text) if t.casefold() not in stop))[:16]
    # Rank in FalkorDB before limiting, so unrelated message matches cannot
    # crowd out durable facts. Superseded claims remain in graph history.
    rows=service.repo.db.execute("""MATCH (n:Entity)
        WHERE n.entity_type IN ['Person','Event','Task','Booking','Claim','Decision','Action','Outcome'] OR n.record_kind IN ['AGENT_FINDING','EXTERNAL_EVIDENCE']
        WITH n, size([term IN $terms WHERE toLower(coalesce(n.name,'')+' '+coalesce(n.text,'')+' '+coalesce(n.summary,'')+' '+coalesce(n.description,'')) CONTAINS term]) AS relevance
        WHERE relevance > 0
        RETURN properties(n), relevance
        ORDER BY relevance DESC, CASE WHEN n.status='SUPERSEDED' THEN 0 WHEN n.status='CONFIRMED' THEN 3 ELSE 1 END DESC, n.id
        LIMIT 12""",{'terms':terms},read=True)
    for row in rows:
        n=node_view(row[0]);nodes[n['id']]=n
    seeds=list(nodes)[:6]
    for root in seeds:
        g=service.repo.traverse(TraversalRequest(root_id=root,hops=2,limit=12))
        for n in g['nodes']:nodes[n['id']]=n
        for e in g['edges']:edges[e['id']]=e
    # Recent evidence resolves follow-ups such as "she confirmed" without global scans.
    for m in history(service,conversation)[-4:]:
        g=service.repo.traverse(TraversalRequest(root_id=m['id'],hops=2,limit=8))
        for n in g['nodes']:nodes[n['id']]=n
        for e in g['edges']:edges[e['id']]=e
    # Follow explicit supersession even if the new wording no longer matches.
    for n in list(nodes.values()):
        replacement=n['properties'].get('superseded_by')
        if replacement:
            g=service.repo.traverse(TraversalRequest(root_id=replacement,hops=1,limit=12))
            for item in g['nodes']:nodes[item['id']]=item
            for item in g['edges']:edges[item['id']]=item
    selected=sorted(nodes.values(),key=lambda n:(n['properties'].get('status')=='SUPERSEDED',n['type'] in ('Message','Conversation','Bot'),n['properties'].get('status')!='CONFIRMED'))[:40]; ids={n['id'] for n in selected}
    return {'nodes':selected,'edges':[e for e in edges.values() if e['source'] in ids and e['target'] in ids][:90]}

def prompt_history(messages):
    return [{'role':m['properties']['role'],'content':m['properties']['content'][:1500]} for m in messages[-12:]]

def prompt_graph(graph):
    return {'nodes':[{**n,'properties':{k:(v[:600] if isinstance(v,str) else v) for k,v in n['properties'].items()}} for n in graph['nodes']], 'edges':graph['edges']}
