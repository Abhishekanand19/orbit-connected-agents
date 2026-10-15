"""Domain validation and record construction, separated from Cypher access."""
import hashlib
import json
from .database import GraphError
from .models import EntityType as E, RelationType as R, TraversalRequest

PROTECTED = {R.HAS_CONVERSATION,R.HAS_MESSAGE,R.AUTHORED_BY,R.SUPERSEDES}
WORK = {E.Task,E.Event,E.Booking}
RULES = {
    R.ASSIGNED_TO:(WORK,{E.Person,E.Bot}), R.DEPENDS_ON:(WORK,WORK|{E.Person}),
    R.PARTICIPATES_IN:({E.Person,E.Bot},{E.Event,E.Conversation}),
    R.MENTIONED_IN:(set(E),{E.Message}),
    R.SUPPORTED_BY:({E.Claim,E.Decision},{E.Source,E.Message,E.Claim}),
    R.MOTIVATED_BY:({E.Decision,E.Action},{E.Claim,E.Decision}),
    R.MUTATED:({E.Action},set(E)), R.PRODUCED:({E.Action},{E.Outcome}),
    R.VERIFIED_BY:({E.Outcome,E.Claim},{E.Source,E.Claim,E.Message}),
}

def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class GraphService:
    def __init__(self, repository):
        self.repo = repository

    def require(self, node_id, types=None):
        node = self.repo.get_node(node_id)
        if types and E(node['type']) not in types:
            raise GraphError(422,'wrong_entity_type',f'Entity {node_id} has an incompatible type.')
        return node

    def upsert_node(self, node_id, request):
        try:
            old = self.repo.get_node(node_id)
        except GraphError as error:
            if error.status != 404:
                raise
        else:
            if old['type'] != request.type:
                raise GraphError(409,'identity_conflict','Entity type cannot be changed.')
            # Provenance sources are immutable once referenced by a claim.
            if request.type == E.Source:
                linked = self.repo.traverse(TraversalRequest(root_id=node_id,hops=1,
                    direction='incoming',relationship_types=[R.SUPPORTED_BY],limit=1))
                if linked['edges'] and any(old['properties'].get(k)!=v for k,v in request.properties.items()):
                    raise GraphError(409,'immutable_source','Create a new source instead of changing cited evidence.')
                if linked['edges']:
                    return old
        return self.repo.upsert_node(node_id,request.type,request.properties)

    def upsert_relationship(self, request):
        if request.type in PROTECTED:
            raise GraphError(422,'managed_relationship','Use the dedicated record API for structural relationships.')
        source = self.require(request.source)
        target = self.require(request.target)
        # Claims and messages retain their original provenance/mentions.
        if source['type'] in (E.Claim,E.Message) or (request.type == R.MENTIONED_IN and target['type']==E.Message):
            raise GraphError(422,'immutable_record','Use the dedicated claim or message API to attach evidence or mentions.')
        if request.type in RULES:
            allowed_source,allowed_target = RULES[request.type]
            if E(source['type']) not in allowed_source or E(target['type']) not in allowed_target:
                raise GraphError(422,'invalid_endpoints','Relationship endpoints have incompatible entity types.')
        return self.repo.upsert_edge(request.source,request.type,request.target,
            request.properties.model_dump(mode='json',exclude_none=True,exclude_unset=True))

    def delete_relationship(self, edge_id):
        edge = self.repo.get_edge(edge_id)
        if edge['type'] in PROTECTED or edge['type'] in {R.SUPPORTED_BY,R.VERIFIED_BY,R.MENTIONED_IN}:
            raise GraphError(409,'protected_relationship','Historical evidence and structural links cannot be deleted.')
        if self.require(edge['source'])['type'] in (E.Claim,E.Message):
            raise GraphError(409,'immutable_record','Historical claim and message links cannot be deleted.')
        self.repo.delete_edge(edge_id)

    def delete_node(self, node_id):
        node = self.require(node_id)
        if node['type'] in (E.Claim,E.Message,E.Conversation):
            raise GraphError(409,'immutable_record','Historical records cannot be deleted.')
        self.repo.delete_node(node_id)

    def create_conversation(self, request):
        self.require(request.bot_id,{E.Bot})
        props = {'title':request.title,'bot_id':request.bot_id}
        return self.repo.atomic_record(request.id,E.Conversation,props,fingerprint(props),
            {request.bot_id:E.Bot},[(request.bot_id,R.HAS_CONVERSATION,request.id)])

    def create_message(self, conversation_id, request):
        conversation = self.require(conversation_id,{E.Conversation})
        bot_id = conversation['properties']['bot_id']
        refs = {conversation_id:E.Conversation,bot_id:E.Bot}
        mentions = sorted(set(request.mentioned_ids))
        for node_id in mentions:
            refs[node_id] = self.require(node_id,{E.Person,E.Task,E.Event,E.Booking})['type']
        props = {'content':request.content,'role':request.role,'conversation_id':conversation_id,'bot_id':bot_id}
        payload = {**props,'mentioned_ids':mentions}
        edges = [(conversation_id,R.HAS_MESSAGE,request.id)] + [(i,R.MENTIONED_IN,request.id) for i in mentions]
        if request.role == 'assistant':
            edges.append((request.id,R.AUTHORED_BY,bot_id))
        return self.repo.atomic_record(request.id,E.Message,props,fingerprint(payload),refs,edges)

    def create_claim(self, request):
        refs = {request.source_id:E.Source}
        source = self.require(request.source_id,{E.Source})
        if not source['properties'].get('observed_at') or not source['properties'].get('kind'):
            raise GraphError(422,'incomplete_source','Claim sources require kind and observed_at.')
        subjects = sorted(set(request.subject_ids))
        for node_id in subjects:
            refs[node_id] = self.require(node_id,{E.Person,E.Event,E.Task,E.Booking,E.Bot,E.Decision,E.Action,E.Outcome})['type']
        edges = [(request.id,R.SUPPORTED_BY,request.source_id)] + [(request.id,R.RELATED_TO,i) for i in subjects]
        if request.message_id:
            self.require(request.message_id,{E.Message})
            refs[request.message_id] = E.Message
            edges += [(request.id,R.MENTIONED_IN,request.message_id), (request.source_id,R.MENTIONED_IN,request.message_id)]
        if request.supersedes_id:
            self.require(request.supersedes_id,{E.Claim})
            refs[request.supersedes_id] = E.Claim
            edges.append((request.id,R.SUPERSEDES,request.supersedes_id))
        props = {'text':request.text,'status':request.status.value,'source_id':request.source_id,
                 'observed_at':request.observed_at.isoformat()}
        if request.message_id:
            props['message_id'] = request.message_id
        payload = request.model_dump(mode='json')
        payload['subject_ids'] = subjects
        return self.repo.atomic_record(request.id,E.Claim,props,fingerprint(payload),refs,edges,request.supersedes_id)

    def evidence(self, node_id, limit=100):
        self.require(node_id,{E.Source,E.Claim,E.Decision,E.Outcome})
        return self.repo.traverse(TraversalRequest(root_id=node_id,hops=4,limit=limit,
            relationship_types=[R.SUPPORTED_BY,R.MENTIONED_IN,R.SUPERSEDES,R.VERIFIED_BY,R.MOTIVATED_BY]))

    def conversation_context(self, conversation_id, limit=100):
        self.require(conversation_id,{E.Conversation})
        return self.repo.traverse(TraversalRequest(root_id=conversation_id,hops=4,limit=limit))

    def dependencies(self, node_id, hops, direction, limit):
        return self.repo.traverse(TraversalRequest(root_id=node_id,hops=hops,direction=direction,
            relationship_types=[R.DEPENDS_ON],limit=limit))

    def affected(self, node_id, hops, limit):
        # Returns connected candidates, not an inferred causal impact or proposed action.
        graph = self.repo.traverse(TraversalRequest(root_id=node_id,hops=hops,limit=limit,
            relationship_types=[R.DEPENDS_ON,R.ASSIGNED_TO,R.PARTICIPATES_IN,R.AFFECTS,R.RELATED_TO]))
        return {'graph':graph,'candidate_ids':[n['id'] for n in graph['nodes']
            if n['id']!=node_id and E(n['type']) in WORK|{E.Person}]}
