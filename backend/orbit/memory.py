"""Bounded graph retrieval, shared by extraction and response generation."""
import re
from .models import TraversalRequest
from .repository import node_view

def history(service, conversation):
    rows=service.repo.db.execute('MATCH (:Conversation {id:$id})-[:HAS_MESSAGE]->(m:Message) RETURN properties(m) ORDER BY m.created_at DESC, m.id DESC LIMIT 16',{'id':conversation},read=True)
    return [node_view(r[0]) for r in reversed(rows)]

def retrieve(service, text, conversation):
    nodes,edges={},{}
    terms=list(dict.fromkeys(re.findall(r'[\w-]{3,}',text)))[:16]
    for term in terms:
        for n in service.repo.search_nodes(term,limit=4)['items']:
            if n['type'] in ('Person','Event','Task','Booking','Claim'):
                nodes[n['id']]=n
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
    selected=list(nodes.values())[:40]; ids={n['id'] for n in selected}
    return {'nodes':selected,'edges':[e for e in edges.values() if e['source'] in ids and e['target'] in ids][:90]}

def prompt_history(messages):
    return [{'role':m['properties']['role'],'content':m['properties']['content'][:1500]} for m in messages[-12:]]

def prompt_graph(graph):
    return {'nodes':[{**n,'properties':{k:(v[:600] if isinstance(v,str) else v) for k,v in n['properties'].items()}} for n in graph['nodes']], 'edges':graph['edges']}
