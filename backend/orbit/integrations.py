"""Graph-directed read selection, MCP invocation journal and evidence persistence."""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4
import anyio
from pydantic import Field
from .database import GraphError
from .models import StrictModel, Id, EntityType as E, RelationType as R, TraversalRequest
from .repository import node_view
from .service import fingerprint
from .integration_providers import now
from .mcp_tools import build_server, session


class Binding(StrictModel):
    entity_id: Id
    provider: Literal['gmail', 'calendar', 'slack']
    resource_id: str = Field(min_length=1, max_length=320)


def bind(service, request):
    service.require(request.entity_id, {E.Person, E.Event, E.Task, E.Booking})
    if request.provider == 'slack' and not re.fullmatch(r'C[A-Z0-9]{5,30}', request.resource_id):
        raise GraphError(422, 'invalid_channel', 'Use a public Slack channel ID.')
    identity = 'binding:' + fingerprint(request.model_dump())[:40]
    service.repo.upsert_node(identity, E.Source, {'name': request.provider + ' context for ' + request.entity_id,
        'kind': 'SYSTEM', 'record_kind': 'INTEGRATION_BINDING', 'provider': request.provider,
        'resource_id': request.resource_id, 'owner': 'local-owner', 'observed_at': now()})
    service.repo.upsert_edge(request.entity_id, R.RELATED_TO, identity, {'note': 'Explicit local-owner integration context; not factual verification'})
    return service.require(identity)


class ReadCall(StrictModel):
    tool: str
    arguments: dict = Field(default_factory=dict)
    entity_ids: list[str] = Field(default_factory=list)
    reason: str


def select(service, request, discovered):
    """Only explicit read intent or reachable configured sources selects external tools.

    Resource bindings are local-owner configuration, never taken from external message content.
    The same request can route differently when a graph relationship is changed.
    """
    text = request.content.casefold()
    if re.search(r'\bwithout (?:external |using )?tools\b',text):return []
    graph_only=bool(re.search(r'\b(graph[- ]only|only (?:use |the )?graph|no external)\b',text))
    # Negative clauses and requests solely to draft do not authorize new external reads.
    if re.match(r'\s*(?:only )?(?:draft|write|compose)\b',text) and not re.search(r'\b(read|fetch|search|retrieve|look up)\b',text):return []
    text=re.sub(r"\b(?:do not|don't|never)\b[^.!?;]*",'',text)
    if not re.search(r'\b(check|read|find|search|look|fetch|retrieve|show|list|review|updates?|conflicts?|schedule|calendars?|emails?|gmail|slack|handoff|dependencies)\b', text):
        return []
    roots = []
    # Discover only named entities, rather than allowing a recent unrelated source to select tools.
    for term in list(dict.fromkeys(re.findall(r'[\w-]{3,}', text)))[:24]:
        for n in service.repo.search_nodes(term, limit=15)['items']:
            name = n['properties'].get('name', '').casefold()
            if n['type'] in ('Person', 'Event', 'Task', 'Booking') and name and name in text and n['id'] not in {r['id'] for r in roots}:
                roots.append(n)
    roots = roots[:3]
    requested = set()
    if re.search(r'\b(email|emails|gmail|mail)\b', text):requested.add('gmail')
    if re.search(r'\b(calendars?|schedule|scheduling)\b', text):requested.add('calendar')
    if re.search(r'\b(slack|handoff)\b', text):requested.add('slack')
    external_allowed=not graph_only and not ('dependencies' in text and not requested)
    bindings = []
    for root in roots:
        graph = service.repo.traverse(TraversalRequest(root_id=root['id'], hops=3, limit=40,
            relationship_types=[R.RELATED_TO, R.DEPENDS_ON, R.AFFECTS, R.ASSIGNED_TO]))
        for n in graph['nodes']:
            p = n['properties']
            if external_allowed and p.get('record_kind') == 'INTEGRATION_BINDING' and p.get('owner') == 'local-owner' and (not requested or p.get('provider') in requested):
                bindings.append((p['provider'], p['resource_id'], root))
    if external_allowed and 'gmail' in requested and not any(b[0] == 'gmail' for b in bindings):
        bindings.append(('gmail', request.content[:500], roots[0] if roots else None))
    if external_allowed and 'calendar' in requested and not any(b[0] == 'calendar' for b in bindings):
        bindings.append(('calendar', 'primary', roots[0] if roots else None))
    if external_allowed and 'slack' in requested and not any(b[0] == 'slack' for b in bindings):
        bindings.append(('slack', os.getenv('SLACK_CHANNEL_ID', 'C0C9SH122US'), roots[0] if roots else None))
    calls = []
    for provider, resource, root in bindings:
        if provider == 'gmail':
            tool, arguments = 'gmail_search', {'query': resource, 'limit': 5}
        elif provider == 'slack':
            tool, arguments = 'slack_messages', {'channel_id': resource, 'limit': 15}
        else:
            p = root['properties'] if root else {}
            start = p.get('starts_at') or datetime.now(timezone.utc).isoformat()
            end = p.get('ends_at') or (datetime.fromisoformat(start.replace('Z', '+00:00')) + timedelta(days=7)).isoformat()
            tool = 'calendar_conflicts' if p.get('starts_at') and p.get('ends_at') else 'calendar_events'
            arguments = {'calendar_id': resource, 'start': start, 'end': end}
        if provider=='calendar' and re.search(r'\b(list|show)\b.*\bcalendars\b',text):
            tool,arguments='calendar_list',{}
        if provider=='slack' and re.search(r'\b(list|show)\b.*\bchannels\b',text):
            tool,arguments='slack_channels',{}
        reason = 'Reachable integration binding for ' + root['id'] if root else 'Explicit user read request'
        if tool in discovered and not any(c.tool == tool and c.arguments == arguments for c in calls):
            calls.append(ReadCall(tool=tool, arguments=arguments, entity_ids=[root['id']] if root else [], reason=reason))
    if 'dependencies' in text and roots and 'graph_dependencies' in discovered:
        calls.insert(0, ReadCall(tool='graph_dependencies', arguments={'entity_id': roots[0]['id']}, entity_ids=[roots[0]['id']], reason='User requested graph dependency analysis'))
    return calls[:3]


class ToolRunner:
    def __init__(self, service, providers=None):
        self.s = service
        self.server = build_server(service, providers)

    def traces(self, message_id):
        rows = self.s.repo.db.execute("MATCH (t:Task) WHERE t.record_kind='MCP_INVOCATION' AND t.message_id=$id RETURN properties(t) ORDER BY t.created_at,t.id LIMIT 100", {'id': message_id}, read=True)
        return [node_view(r[0]) for r in rows]

    def evidence(self, message_id):
        rows = self.s.repo.db.execute("MATCH (s:Source)-[:MENTIONED_IN]->(:Message {id:$id}) WHERE s.record_kind='EXTERNAL_EVIDENCE' RETURN properties(s) ORDER BY s.created_at LIMIT 8", {'id': message_id}, read=True)
        return [node_view(r[0]) for r in rows]

    async def invoke(self, client, request, call):
        self.s.require(request.id, {E.Message})
        call_key = fingerprint({'message': request.id, 'tool': call.tool, 'arguments': call.arguments})
        existing = next((t for t in self.traces(request.id) if t['properties'].get('call_key') == call_key and t['properties'].get('status') == 'DONE'), None)
        if existing:
            return json.loads(existing['properties']['result'])
        identity = 'mcp:' + str(uuid4())
        source = call.tool.split('_')[0]
        props = {'name': call.tool, 'record_kind': 'MCP_INVOCATION', 'message_id': request.id,
                 'owner': 'local-owner', 'tool': call.tool, 'source': source, 'transport': 'mcp-memory',
                 'selected_at': now(), 'selection_reason': call.reason, 'arguments': json.dumps(call.arguments),
                 'call_key':call_key, 'agent_capability':{'gmail':'research','calendar':'planner','slack':'tasks','graph':'planner'}.get(source,'research'),
                 'status': 'IN_PROGRESS', 'error': '', 'result': ''}
        self.s.repo.upsert_node(identity, E.Task, props)
        self.s.repo.upsert_edge(identity, R.MENTIONED_IN, request.id, {})
        try:
            response = await client.call_tool(call.tool, call.arguments)
            if response.isError:
                raise GraphError(502, 'mcp_call_failed', 'MCP rejected the tool call or its arguments.')
            data = response.structuredContent
            if data is None:
                data = json.loads(response.content[0].text)
            if not data.get('ok'):
                error = data.get('error', {})
                raise GraphError(502, error.get('code', 'tool_failed'), error.get('message', 'Read failed.'))
            result = data['result']
            # Persist a bounded snapshot rather than unbounded raw provider bodies.
            encoded = json.dumps(result, ensure_ascii=False)
            if len(encoded) > 100000:
                raise GraphError(502, 'tool_result_large', 'Tool result exceeds the evidence storage limit.')
            evidence_id = 'external:' + str(uuid4())
            evidence = {'name': call.tool + ' observation', 'kind': 'SYSTEM', 'record_kind': 'EXTERNAL_EVIDENCE',
                'provider': source, 'owner': 'local-owner', 'observed_at': result.get('observed_at', now()),
                'evidence_state': 'UNVERIFIED', 'description': encoded[:4000], 'result': encoded,
                'tool': call.tool, 'message_id': request.id}
            refs = {request.id: E.Message, identity: E.Task}
            links = [(evidence_id, R.MENTIONED_IN, request.id), (identity, R.PRODUCED, evidence_id)]
            for id in call.entity_ids:
                refs[id] = E(self.s.require(id)['type']); links.append((evidence_id, R.RELATED_TO, id))
            self.s.repo.atomic_record(evidence_id, E.Source, evidence, fingerprint(evidence), refs, links)
            self.s.repo.upsert_node(identity, E.Task, {'status': 'DONE', 'completed_at': now(), 'result': encoded, 'evidence_id': evidence_id})
            return result
        except Exception as exc:
            error = exc.code + ': ' + exc.message if isinstance(exc, GraphError) else 'mcp_transport_failed: Read failed.'
            self.s.repo.upsert_node(identity, E.Task, {'status': 'FAILED', 'completed_at': now(), 'error': error})
            return {'error': error}

    async def run_async(self, request):
        async with session(self.server) as client:
            discovered = (await client.list_tools()).tools
            rows=self.s.repo.db.execute('MATCH (p:OrbitToolPlan {id:$id}) RETURN p.plan',{'id':request.id},read=True)
            if rows:
                calls=[ReadCall.model_validate(c) for c in json.loads(rows[0][0])]
            else:
                calls = select(self.s, request, {t.name for t in discovered})
                self.s.repo.db.execute('MERGE (p:OrbitToolPlan {id:$id}) ON CREATE SET p.plan=$plan,p.discovered=$discovered,p.selected_at=$at',
                    {'id':request.id,'plan':json.dumps([c.model_dump() for c in calls]),'discovered':json.dumps([t.name for t in discovered]),'at':now()})
            count = 0
            for call in calls:
                result = await self.invoke(client, request, call); count += 1
                # Read selected search results through MCP too; total budget is four calls.
                if call.tool == 'gmail_search' and result.get('items') and count < 4:
                    await self.invoke(client, request, ReadCall(tool='gmail_read', arguments={'message_id': result['items'][0]['id']}, entity_ids=call.entity_ids, reason='Read first result of the selected Gmail search'))
                    count += 1
                if count >= 4:
                    break
        return {'traces': self.traces(request.id), 'evidence': self.evidence(request.id)}

    def run(self, request):
        return anyio.run(self.run_async, request)
