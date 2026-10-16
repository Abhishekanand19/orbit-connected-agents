"""Graph proposal -> payload-bound approval -> MCP executor -> verified outcome.

The single local owner is authenticated at the HTTP boundary. Agents only propose.
All tools reload the persisted payload and atomically consume APPROVED once.
"""
import json
import secrets
import time
from datetime import datetime,timezone
from uuid import uuid4
import anyio
from .action_models import ActionDraft,TOOLS
from .action_providers import ActionProviders,WriteFailure
from .database import GraphError
from .models import EntityType as E,RelationType as R,TraversalRequest
from .repository import node_view,edge_view,edge_id
from .service import fingerprint

OWNER='local-owner'
DOMAIN={E.Person.value,E.Event.value,E.Task.value,E.Booking.value,E.Claim.value,E.Source.value}
RELATIONS=[R.DEPENDS_ON,R.AFFECTS,R.ASSIGNED_TO,R.AVAILABLE_FOR,R.RELATED_TO,R.SUPPORTED_BY,R.VERIFIED_BY]

def timestamp():return datetime.now(timezone.utc).isoformat()

class Actions:
    def __init__(self,service,providers=None):
        self.s=service;self.db=service.repo.db;self.providers=providers or ActionProviders()

    def get(self,id):
        n=self.s.require(id,{E.Action})
        if n['properties'].get('record_kind')!='APPROVAL_ACTION':raise GraphError(404,'not_action','No executable action found.')
        return n

    def list(self):
        rows=self.db.execute("MATCH (a:Action) WHERE a.record_kind='APPROVAL_ACTION' AND a.owner=$owner RETURN properties(a) ORDER BY a.created_at DESC LIMIT 60",{'owner':OWNER},read=True)
        return [self.view(node_view(r[0])) for r in rows]

    def view(self,n):
        p=n['properties'];spec=json.loads(p['spec'])
        labels={}
        for id in spec['affected_ids']:
            try:labels[id]=self.s.require(id)['properties'].get('name',id)
            except GraphError:labels[id]=id
        return {'id':n['id'],'status':p['status'],'digest':p['digest'],'tool':p['tool'],
                'application':spec['kind'].split('_')[0],'reason':spec['reason'],'payload':spec['payload'],
                'affected_ids':spec['affected_ids'],'affected_labels':labels,'evidence_ids':spec['evidence_ids'],'decision_id':spec.get('decision_id'),
                'expires_at':p['expires_at'],'error':p.get('error',''),'retryable':p.get('retryable',False),
                'verification':json.loads(p.get('verification','{}')),'receipt':json.loads(p.get('receipt','{}')),
                'history':json.loads(p['history']),'message_id':p['message_id']}

    def context(self,spec):
        nodes={};edges={}
        frontier=set(spec['affected_ids'])
        for id in frontier:
            n=self.s.require(id);nodes[id]={'type':n['type'],'properties':n['properties']}
        # Bound unique evidence, not the combinatorial number of paths through it.
        for depth in range(4):
            if not frontier:break
            rows=self.db.execute("""MATCH (a:Entity)-[r:DEPENDS_ON|AFFECTS|ASSIGNED_TO|AVAILABLE_FOR|RELATED_TO|SUPPORTED_BY|VERIFIED_BY]-(b:Entity)
                WHERE a.id IN $ids AND a.entity_type IN $types AND b.entity_type IN $types
                AND NOT coalesce(a.record_kind,'') IN ['AGENT_RUN','MCP_INVOCATION']
                AND NOT coalesce(b.record_kind,'') IN ['AGENT_RUN','MCP_INVOCATION']
                RETURN DISTINCT properties(r),properties(b) LIMIT 301""",{'ids':sorted(frontier),'types':sorted(DOMAIN)},read=True)
            if len(rows)>300:raise GraphError(409,'context_truncated','Graph context is truncated; narrow the proposal before approval.')
            next_frontier=set()
            for props,other in rows:
                e=edge_view(props);edges[e['id']]=e;n=node_view(other)
                if n['id'] not in nodes:next_frontier.add(n['id'])
                nodes[n['id']]={'type':n['type'],'properties':n['properties']}
            if len(nodes)>100 or len(edges)>300:raise GraphError(409,'context_truncated','Graph context is truncated; narrow the proposal before approval.')
            frontier=next_frontier
        for id in spec['evidence_ids']:
            n=self.s.require(id);nodes[id]={'type':n['type'],'properties':n['properties']}
        return fingerprint({'nodes':nodes,'edges':{id:{k:e[k] for k in ('type','source','target','properties')} for id,e in edges.items() if e['source'] in nodes and e['target'] in nodes}})

    def check_constraints(self,spec):
        if spec.get('decision_id'):
            decision=self.s.require(spec['decision_id'],{E.Decision})['properties']
            if decision.get('record_kind')!='IMPACT_ANALYSIS':raise GraphError(422,'invalid_decision','Use a graph impact decision.')
            analysis=json.loads(decision['analysis'])
            if analysis['state']!='ACT' or analysis['truncated']:
                raise GraphError(409,'graph_blocks_action','Graph decision is '+analysis['state']+'; no executable proposal is allowed.')
            if analysis['trigger_id'] not in spec['affected_ids']:raise GraphError(422,'unrelated_decision','Decision must affect the proposed entity.')
            # Evidence can be revoked after the decision was recorded.
            from .intelligence import ImpactEngine,ImpactRequest
            if ImpactEngine(self.s).claim_state(analysis['trigger_claim_id'])!='VERIFIED':
                raise GraphError(409,'stale_decision','Decision evidence is no longer verified.')
            current=ImpactEngine(self.s).analyze(ImpactRequest(root_id=analysis['trigger_id'],trigger_claim_id=analysis['trigger_claim_id'],hops=4))
            if current.state!='ACT':raise GraphError(409,'stale_decision','Current graph constraints no longer support action: '+current.state)

    def propose(self,draft,message_id,previous_id=None):
        if not isinstance(draft,ActionDraft):draft=ActionDraft.model_validate(draft)
        message=self.s.require(message_id,{E.Message})
        if message['properties']['role']!='user':raise GraphError(422,'user_request_required','Actions require a user request.')
        spec=draft.model_dump(mode='json');self.check_constraints(spec)
        for id in spec['affected_ids']:self.s.require(id,{E.Person,E.Event,E.Booking,E.Task})
        for id in spec['evidence_ids']:self.s.require(id,{E.Source,E.Claim,E.Message,E.Decision,E.Action,E.Outcome})
        if spec['kind'].startswith('task'):
            p=spec['payload']
            if p.get('assignee_id'):self.s.require(p['assignee_id'],{E.Person,E.Bot})
            try:task=self.s.require(p['task_id'],{E.Task})
            except GraphError as exc:
                if exc.status!=404 or spec['kind']!='task_create':raise
                task=None
            merged={**(task['properties'] if task else {}),**p['changes']}
            if merged.get('starts_at') and merged.get('ends_at'):
                if datetime.fromisoformat(merged['ends_at'].replace('Z','+00:00'))<=datetime.fromisoformat(merged['starts_at'].replace('Z','+00:00')):
                    raise GraphError(422,'invalid_task_interval','The proposed task must end after it starts.')
            if task and task['properties'].get('record_kind'):raise GraphError(422,'internal_task','Internal journals cannot be modified as user tasks.')
            if spec['kind']=='task_update' and p['task_id'] not in spec['affected_ids']:raise GraphError(422,'unrelated_task','The changed task must appear in affected entities.')
        canonical='action:'+fingerprint({'tool':TOOLS[spec['kind']],'payload':spec['payload'],'affected':sorted(spec['affected_ids'])})[:48]
        completed=self.db.execute("MATCH (a:Action) WHERE a.canonical_key=$key AND a.status IN ['VERIFIED','EXECUTING','UNKNOWN'] RETURN properties(a) LIMIT 1",{'key':canonical},read=True)
        if completed:return self.view(node_view(completed[0][0]))
        identity=canonical+(':'+uuid4().hex[:8] if previous_id else '')
        try:return self.view(self.get(identity))
        except GraphError as exc:
            if exc.status!=404:raise
        if spec['kind']=='task_create' and task:raise GraphError(409,'task_exists','Create cannot overwrite an existing task.')
        account=self.providers.account(spec['kind'])
        context=self.context(spec);expires=int(time.time())+1800
        seal={'spec':spec,'context_hash':context,'owner':OWNER,'account':account,'expires_at':expires}
        digest=fingerprint(seal)
        props={'name':TOOLS[spec['kind']],'record_kind':'APPROVAL_ACTION','owner':OWNER,'tool':TOOLS[spec['kind']],
            'canonical_key':canonical,'previous_id':previous_id or '',
            'spec':json.dumps(spec),'context_hash':context,'account':account,'digest':digest,'expires_at':expires,
            'message_id':message_id,'status':'AWAITING_APPROVAL','history':json.dumps([{'status':'PROPOSED','at':timestamp()},{'status':'AWAITING_APPROVAL','at':timestamp()}]),
            'receipt':'{}','verification':'{}','error':'','retryable':False}
        refs={message_id:E.Message};links=[(identity,R.MENTIONED_IN,message_id)]
        for id in set(spec['affected_ids']+spec['evidence_ids']):
            refs[id]=E(self.s.require(id)['type']);links.append((identity,R.RELATED_TO if id in spec['affected_ids'] else R.SUPPORTED_BY,id))
        if spec.get('decision_id'):
            refs[spec['decision_id']]=E.Decision;links.append((identity,R.MOTIVATED_BY,spec['decision_id']))
        from .receipts import evidence_snapshot
        props['evidence_snapshot']=json.dumps(evidence_snapshot(self.s,list(refs)))
        self.s.repo.atomic_record(identity,E.Action,props,fingerprint(props),refs,links)
        return self.view(self.get(identity))

    def valid(self,n,digest,owner,fresh=True):
        p=n['properties'];spec=json.loads(p['spec'])
        seal={'spec':spec,'context_hash':p['context_hash'],'owner':p['owner'],'account':p['account'],'expires_at':p['expires_at']}
        if owner!=OWNER or p['owner']!=owner:raise GraphError(403,'wrong_owner','Only the authorized local owner may approve.')
        if not secrets.compare_digest(p['digest'],digest) or fingerprint(seal)!=digest:
            raise GraphError(409,'payload_changed','The proposal changed. Reload and review the exact proposal.')
        if fresh:
            if p['expires_at']<time.time():raise GraphError(409,'approval_expired','Proposal expired. Create and review a fresh proposal.')
            if self.context(spec)!=p['context_hash']:raise GraphError(409,'stale_graph','Graph evidence changed. Create and review a fresh proposal.')
            if self.providers.account(spec['kind'])!=p['account']:raise GraphError(409,'account_changed','Connected account changed. Create a new proposal.')
            self.check_constraints(spec)
        return spec

    def transition(self,id,states,status,extra=None):
        p=self.get(id)['properties']
        changes={'status':status,'history':json.dumps(json.loads(p['history'])+[{'status':status,'at':timestamp()}]),**(extra or {})}
        rows=self.db.execute("MATCH (a:Action {id:$id}) WHERE a.status IN $states AND a.digest=$digest SET a += $changes,a.updated_at=timestamp() RETURN properties(a)",
                             {'id':id,'states':states,'digest':p['digest'],'changes':changes})
        return bool(rows)

    def approve(self,id,digest,owner=OWNER):
        n=self.get(id);p=n['properties']
        self.valid(n,digest,owner,fresh=p['status'] in ('AWAITING_APPROVAL','APPROVED'))
        if p['status']=='AWAITING_APPROVAL':self.transition(id,['AWAITING_APPROVAL'],'APPROVED',{'approved_owner':owner,'approved_digest':digest,'approved_at':timestamp()})
        return self.view(self.get(id))

    def reject(self,id,digest,owner=OWNER):
        self.valid(self.get(id),digest,owner,fresh=False)
        self.transition(id,['AWAITING_APPROVAL','APPROVED'],'REJECTED',{'error':'Rejected by the user.'})
        return self.view(self.get(id))

    def retry(self,id,digest,owner=OWNER):
        n=self.get(id);self.valid(n,digest,owner)
        if n['properties']['status']!='FAILED' or not n['properties'].get('retryable'):
            raise GraphError(409,'unsafe_retry','This action cannot be replayed. Use readback for uncertain outcomes.')
        self.transition(id,['FAILED'],'APPROVED',{'error':'','retryable':False})
        return self.dispatch(id,digest)

    def refresh(self,id,digest,owner=OWNER):
        n=self.get(id);spec=self.valid(n,digest,owner,fresh=False);p=n['properties']
        if p['status'] not in ('AWAITING_APPROVAL','APPROVED','FAILED') or json.loads(p['receipt']):
            raise GraphError(409,'cannot_refresh','Executed or uncertain actions cannot be replaced. Use readback.')
        if not self.transition(id,[p['status']],'SUPERSEDED',{'error':'Replaced by a fresh proposal requiring a new approval.'}):
            raise GraphError(409,'action_changed','The action changed while refreshing. Reload its status.')
        return self.propose(ActionDraft.model_validate(spec),p['message_id'],previous_id=id)

    def task_write(self,spec,id):
        p=spec['payload'];target=p['task_id'];changes=p['changes'];assignee=p.get('assignee_id')
        old=None
        if spec['kind']=='task_update':old=self.s.require(target,{E.Task})
        params={'id':target,'action':id,'changes':changes,'version':old['updated_at'] if old else 0}
        prefix="MATCH (person:Entity {id:$assignee}) WHERE person.entity_type IN ['Person','Bot'] " if assignee else ''
        if spec['kind']=='task_create':
            query=prefix+"OPTIONAL MATCH (old:Entity {id:$id}) WITH "+('person,' if assignee else '')+"old WHERE old IS NULL CREATE (t:Entity:Task {id:$id,entity_type:'Task',created_at:timestamp()})"
        else:
            query=prefix+"MATCH (t:Task {id:$id}) WHERE t.updated_at=$version AND t.record_kind IS NULL"
        if assignee:
            params.update(assignee=assignee,edge=edge_id(target,'ASSIGNED_TO',assignee))
            query+=" WITH t,person OPTIONAL MATCH (t)-[previous:ASSIGNED_TO]->() DELETE previous WITH DISTINCT t,person"
            query+=" MERGE (t)-[r:ASSIGNED_TO]->(person) ON CREATE SET r.id=$edge,r.source=$id,r.target=$assignee,r.relation_type='ASSIGNED_TO',r.created_at=timestamp() SET r.updated_at=timestamp(),r.evidence_state='CONFIRMED',r.note='Explicit user-approved task action'"
        query+=" SET t += $changes,t.last_action_id=$action,t.updated_at=timestamp() RETURN t.id"
        if not self.db.execute(query,params):raise WriteFailure('Task changed before execution; create a fresh proposal.')
        return {'id':target}

    def task_verify(self,spec,id):
        p=spec['payload'];n=self.s.require(p['task_id'],{E.Task})
        good=n['properties'].get('last_action_id')==id and all(n['properties'].get(k)==v for k,v in p['changes'].items())
        if p.get('assignee_id'):
            rows=self.db.execute('MATCH (:Task {id:$id})-[:ASSIGNED_TO]->(p) RETURN p.id',{'id':p['task_id']},read=True)
            good=good and [r[0] for r in rows]==[p['assignee_id']]
        return {'verified':good,'provider_id':p['task_id'],'readback':n}

    def finish(self,id,status,verification=None,error='',retryable=False):
        extra={'verification':json.dumps(verification or {}),'error':error,'retryable':retryable,'completed_at':timestamp()}
        self.transition(id,['EXECUTING','UNKNOWN'],status,extra)
        outcome='outcome:'+str(uuid4());props={'name':status+' action outcome','summary':error or 'Fresh readback matched the approved payload.',
            'record_kind':'ACTION_OUTCOME','status':status,'action_id':id,'observed_at':timestamp(),'verification':extra['verification']}
        self.s.repo.atomic_record(outcome,E.Outcome,props,fingerprint(props),{id:E.Action},[(id,R.PRODUCED,outcome)])
        return self.view(self.get(id))

    def execute_tool(self,tool,id,digest):
        n=self.get(id);p=n['properties']
        if tool!=p['tool'] or p.get('approved_owner')!=OWNER or p.get('approved_digest')!=digest:
            raise GraphError(403,'approval_required','This exact action requires an explicit user approval.')
        if p['status']!='APPROVED':return self.view(n)
        spec=self.valid(n,digest,OWNER)
        if not self.transition(id,['APPROVED'],'EXECUTING',{'started_at':timestamp(),'transport':'mcp-memory'}):return self.view(self.get(id))
        try:
            receipt=self.task_write(spec,id) if spec['kind'].startswith('task') else self.providers.perform(spec['kind'],spec['payload'],id)
        except WriteFailure as exc:
            return self.finish(id,'UNKNOWN' if exc.uncertain else 'FAILED',error=exc.message,retryable=exc.retryable and not exc.uncertain)
        except GraphError as exc:
            return self.finish(id,'UNKNOWN',error='Execution could not be confirmed. '+exc.message,retryable=False)
        except Exception:
            return self.finish(id,'UNKNOWN',error='Execution was interrupted. Readback is required; do not replay.')
        # Persist acknowledgement BEFORE readback, so restart can reconcile without sending again.
        self.db.execute('MATCH (a:Action {id:$id}) SET a.receipt=$receipt',{'id':id,'receipt':json.dumps(receipt)})
        return self.verify_tool(id,digest)

    def verify_tool(self,id,digest):
        n=self.get(id);p=n['properties'];spec=self.valid(n,digest,OWNER,fresh=False)
        if p['status']=='VERIFIED':return self.view(n)
        if p['status'] not in ('EXECUTING','UNKNOWN'):raise GraphError(409,'not_executed','There is no uncertain execution to verify.')
        if self.providers.account(spec['kind'])!=p['account']:raise GraphError(409,'account_changed','Reconnect the original account for readback.')
        try:
            result=self.task_verify(spec,id) if spec['kind'].startswith('task') else self.providers.verify(spec['kind'],spec['payload'],id,json.loads(p['receipt']))
        except Exception:
            return self.finish(id,'UNKNOWN',error='Readback could not confirm the write. Recheck verification; do not resend.')
        return self.finish(id,'VERIFIED' if result.get('verified') else 'UNKNOWN',result,'' if result.get('verified') else 'Readback does not match the approved payload. Do not resend.')

    def recover(self):
        # Called once on single-worker startup, never while an active request is executing.
        rows=self.db.execute("MATCH (a:Action) WHERE a.record_kind='APPROVAL_ACTION' AND a.status='EXECUTING' RETURN a.id",read=True)
        for row in rows:self.finish(row[0],'UNKNOWN',error='Backend restarted during execution; verify before any further action.')

    async def dispatch_async(self,id,digest,verify=False):
        from .mcp_tools import build_server,session
        tool='action_verify' if verify else self.get(id)['properties']['tool']
        try:
            async with session(build_server(self.s,executor=self),timeout=120) as client:
                if tool not in {t.name for t in (await client.list_tools()).tools}:raise ValueError('missing tool')
                result=await client.call_tool(tool,{'action_id':id,'approval_digest':digest})
                data=result.structuredContent or json.loads(result.content[0].text)
        except Exception:
            current=self.get(id)
            if current['properties']['status']=='EXECUTING':return self.finish(id,'UNKNOWN',error='MCP transport interrupted; verify the saved action before proceeding.')
            if current['properties']['status']=='VERIFIED':return self.view(current)
            raise GraphError(503,'mcp_action_unavailable','MCP action transport failed; refresh the saved status before retrying.') from None
        if result.isError or not data.get('ok'):
            raise GraphError(409,'action_rejected',data.get('error',{}).get('message','MCP action rejected.'))
        return data['result']

    def dispatch(self,id,digest,verify=False):return anyio.run(self.dispatch_async,id,digest,verify)
