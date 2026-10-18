"""Progressive deterministic story, backed exclusively by the selected FalkorDB graph.

The scenario defines vocabulary and dependency rules, never successful actions.
User reports are not provider verification. Local task changes require approval.
"""
import json
import time
from datetime import datetime,timedelta
from .database import GraphError
from .models import NodeUpsert,ConversationCreate,MessageCreate,ClaimCreate,EntityType as E,RelationType as R,TraversalRequest
from .repository import node_view,edge_view
from .service import fingerprint
from .extraction import stable
from .actions import Actions
from .action_models import ActionDraft
from .receipts import evidence_snapshot
from .story_parse import parse
from .story_words import present

LABELS={'research':'Research Assistant','planner':'Schedule Planner','tasks':'Task Manager','communication':'Communication Assistant'}
PREFIX='story:'

class StoryEngine:
    def __init__(self,service):
        self.s=service;self.db=service.repo.db
        if not self.db.settings.graph.startswith('orbit_story_'):
            raise GraphError(403,'story_isolation','Start an isolated deterministic demo first.')

    def snapshot(self):
        nodes=[node_view(r[0]) for r in self.db.execute('MATCH (n:Entity) RETURN properties(n) ORDER BY n.created_at,n.id LIMIT 501',read=True)]
        edges=[edge_view(r[0]) for r in self.db.execute('MATCH (:Entity)-[r]->(:Entity) RETURN properties(r) ORDER BY r.created_at,r.id LIMIT 1001',read=True)]
        ids={n['id'] for n in nodes[:500]}
        return {'nodes':nodes[:500],'edges':[e for e in edges[:1000] if e['source'] in ids and e['target'] in ids],'paths':[],'truncated':len(nodes)>500 or len(edges)>1000}

    def state(self):
        rows=self.db.execute('MATCH (s:OrbitStoryState {id:"story"}) RETURN s.slots,s.revision,s.day',read=True)
        if not rows:raise GraphError(409,'story_state','The isolated workspace has no story configuration.')
        slots,revision,day=rows[0]
        return {'mode':'deterministic','slots':json.loads(slots),'graph_revision':revision,'day':day,'graph':self.snapshot()}

    def at(self,value,day):return day+'T'+value+':00+05:30'

    def turn(self,req):
        started=time.perf_counter()
        if req.bot_id!='coordinator':raise GraphError(422,'story_coordinator','Use Orbit Coordinator for the deterministic story.')
        saved=self.db.execute('MATCH (t:OrbitStoryTurn {id:$id}) RETURN t.response,t.content,t.conversation,t.source',{'id':req.id},read=True)
        if saved:
            if saved[0][1:]!=[req.content,req.conversation_id,req.source]:raise GraphError(409,'turn_conflict','Message identity was already used for different input.')
            return json.loads(saved[0][0])
        state=self.state();slots=state['slots'];day=state['day'];before=state['graph']
        parsed=parse(req.content,slots)
        self.s.upsert_node('chatbot:coordinator',NodeUpsert(type='Bot',properties={'name':'Orbit Coordinator'}))
        try:
            conversation=self.s.require(req.conversation_id,{E.Conversation})
            if conversation['properties'].get('bot_id')!='chatbot:coordinator':raise GraphError(409,'conversation_conflict','This conversation belongs to another bot.')
        except GraphError as e:
            if e.status!=404:raise
            self.s.create_conversation(ConversationCreate(id=req.conversation_id,bot_id='chatbot:coordinator',title='Family planning conversation'))
        user=self.s.create_message(req.conversation_id,MessageCreate(id=req.id,role='user',content=req.content))
        handoffs=[];evidence=[];proposal_ids=[];prior=[];decision=None;checklist=[]
        if parsed['questions']:
            response=' '.join(parsed['questions'][:2])+' I have not changed the story facts.'
        else:
            changes={k:v for k,v in parsed['facts'].items() if slots.get(k)!=v}
            old=dict(slots);slots.update(changes)
            if 'day_offset' in changes and not old.get('appointment_start'):
                day=(datetime.fromisoformat(day)+timedelta(days=int(changes['day_offset']))).date().isoformat()
                self.db.execute('MATCH (s:OrbitStoryState {id:"story"}) SET s.day=$day',{'day':day})
            if changes.get('weekday')=='Monday' and not old.get('appointment_start'):
                date=datetime.fromisoformat(day);day=(date+timedelta(days=(0-date.weekday())%7)).date().isoformat()
                self.db.execute('MATCH (s:OrbitStoryState {id:"story"}) SET s.day=$day',{'day':day})
            # Anchor observed times, never an invented travel duration.
            for key in ('appointment','cab'):
                if key+'_start' in changes and key+'_anchor' not in slots:slots[key+'_anchor']=changes[key+'_start']
            source_id=stable(req.id+':source')
            observed=datetime.fromtimestamp(user['created_at']/1000).astimezone().isoformat()
            if changes:
                self.s.upsert_node(source_id,NodeUpsert(type='Source',properties={'name':changes.get('rumor_source','User report · '+req.source),'kind':'USER_MESSAGE','observed_at':observed}))
            for name in ('aarav','ramesh','priya','meera'):
                if name in slots:self.s.upsert_node(PREFIX+name,NodeUpsert(type='Person',properties={'name':slots[name]}))
            for key,label,kind in [('appointment','Hospital appointment','Event'),('cab','Internal simulated cab arrangement','Task'),('physio','Physiotherapy','Task'),('deployment','Work deployment','Task')]:
                if key+'_start' not in slots:continue
                if key=='deployment':label=slots.get('deployment_label',label)
                props={'name':label,'starts_at':self.at(slots[key+'_start'],day)}
                if key+'_end' in slots:props['ends_at']=self.at(slots[key+'_end'],day)
                if key=='appointment':props['location']=slots.get('appointment_location','hospital')
                if kind=='Task':
                    try:existing=self.s.require(PREFIX+key)['properties']
                    except GraphError:existing={}
                    # Approved actions are authoritative. Repeated narrative facts
                    # must not overwrite an executed arrangement.
                    if existing.get('last_action_id') and key+'_start' not in changes:props.pop('starts_at',None)
                    if not existing:props['status']='OPEN'
                    if key+'_status' in changes:props['status']=slots[key+'_status']
                    if key=='cab':props['description']='Internal simulation only; no third-party cab booking or cancellation.'
                self.s.upsert_node(PREFIX+key,NodeUpsert(type=kind,properties=props))
            if slots.get('cab_start'):
                self.s.upsert_node(PREFIX+'booking',NodeUpsert(type='Booking',properties={'name':'Original cab reference · simulation only','reference':'INTERNAL-SIMULATION','starts_at':self.at(slots['cab_start'],day)}))
            if slots.get('cab_start'):
                self.s.repo.upsert_node(PREFIX+'cab',E.Task,{k:slots[k] for k in ('pickup','destination') if k in slots})
            if slots.get('destination'):
                self.s.repo.upsert_node(PREFIX+'hospital',E.Source,{'name':slots['destination'],'kind':'USER_MESSAGE','record_kind':'STORY_HOSPITAL','evidence_status':'USER_REPORTED'})
            subjects=[PREFIX+n for n in ('aarav','ramesh','priya','meera') if n in slots]+[PREFIX+k for k in ('appointment','cab','physio','deployment') if k+'_start' in slots]
            for key,value in changes.items():
                if key in ('focus','person_focus','day_offset') or not subjects:continue
                claim=stable(req.id+':fact:'+key);previous=slots.get('_claim_'+key)
                status=slots[key] if key in ('rumor','protest') else 'CONFIRMED'
                entity=key.split('_')[0]
                specific=[PREFIX+entity] if PREFIX+entity in subjects else ([PREFIX+'appointment'] if PREFIX+'appointment' in subjects else subjects)
                self.s.create_claim(ClaimCreate(id=claim,text=f'{key}: {value} (user-reported; not independently verified)',status=status,source_id=source_id,message_id=req.id,subject_ids=specific,observed_at=observed,supersedes_id=previous))
                label='Closure rumor · '+status.lower() if key=='rumor' else 'Reported '+key.replace('_',' ')+': '+value
                self.db.execute('MATCH (c:Claim {id:$id}) SET c.previous_value=$previous,c.slot=$slot,c.name=$name',{'id':claim,'previous':json.dumps(old.get(key)),'slot':key,'name':label})
                slots['_claim_'+key]=claim;evidence.append(claim)
            existing_ids={n['id'] for n in self.snapshot()['nodes']}
            def edge(a,rel,b,note='',fact=None):
                if a not in existing_ids or b not in existing_ids:return
                claim=slots.get('_claim_'+(fact or 'appointment_start'))
                props={'evidence_state':'CONFIRMED','note':note or 'User-reported scenario relationship; not independently verified'}
                if claim:props['evidence_id']=claim
                self.s.repo.upsert_edge(a,rel,b,props)
            if 'aarav' in slots:
                for parent in ('ramesh','meera'):
                    if parent in slots:edge(PREFIX+parent,R.PARENT_OF,PREFIX+'aarav',fact=parent)
                if 'priya' in slots:edge(PREFIX+'aarav',R.SIBLING_OF,PREFIX+'priya',fact='priya')
            if 'aarav' not in slots and 'priya' in slots:
                for parent in ('ramesh','meera'):
                    if parent in slots:edge(PREFIX+parent,R.PARENT_OF,PREFIX+'priya',fact=parent)
            edge(PREFIX+'appointment',R.RELATED_TO,PREFIX+'hospital','User-reported hospital destination.',fact='destination')
            edge(PREFIX+'cab',R.RELATED_TO,PREFIX+'hospital','User-reported transport destination; not a booking confirmation.',fact='destination')
            edge(PREFIX+'cab',R.DEPENDS_ON,PREFIX+'appointment','Scenario dependency: internal transport serves the hospital visit.')
            edge(PREFIX+'booking',R.DEPENDS_ON,PREFIX+'cab','Internal simulated booking follows the transport task.')
            edge(PREFIX+'physio',R.DEPENDS_ON,PREFIX+'cab','Scenario dependency: travel timing may affect later physiotherapy.')
            edge(PREFIX+'deployment',R.ASSIGNED_TO,PREFIX+'aarav',fact='deployment_start')
            edge(PREFIX+'deployment',R.RELATED_TO,PREFIX+'appointment','Same-day commitment; timing needs checking, not an established overlap.',fact='deployment_start')
            edge(PREFIX+'ramesh',R.PARTICIPATES_IN,PREFIX+'appointment')
            for person in ('meera','priya'):
                if person+'_availability' in slots or person+'_unavailable_from' in slots or person+'_escort' in slots:
                    edge(PREFIX+person,R.AVAILABLE_FOR,PREFIX+'appointment',fact=person+'_availability')
                    # Stored constraint values drive the planner, not stage numbers.
                    self.s.repo.upsert_node(PREFIX+person,E.Person,{k:slots[person+'_'+k] for k in ('availability','available_from','unavailable_from','escort') if person+'_'+k in slots})
            intents=set(parsed['intents'])
            lines=[]
            if 'family' in intents:lines.append('I’ve recorded '+', '.join(slots[n] for n in ('aarav','ramesh','priya','meera') if n in slots)+' and the family connections you introduced.')
            if 'schedule' in intents:lines.append('I’ve recorded the reported times on '+day+'. These are user reports, not provider-confirmed calendar changes.')
            if 'rumor' in intents:
                text='WAIT — the hospital closure is unverified. I will not cancel appointments or transport on that basis.' if slots['rumor']=='UNVERIFIED' else 'You reported that the closure rumor is false. Its previous claim remains in the evidence history.'
                handoffs.append(('research',text));lines.append(text)
            if slots.get('appointment_start') and (intents & {'schedule','availability','video','coordination','recall'}):
                graph=self.s.repo.traverse(TraversalRequest(root_id=PREFIX+'appointment',hops=4,relationship_types=[R.DEPENDS_ON,R.AVAILABLE_FOR,R.ASSIGNED_TO,R.PARTICIPATES_IN,R.RELATED_TO],limit=100))
                # Enumerate real dependency paths, preserving edge identity/direction.
                paths=[];queue=[(PREFIX+'appointment',[PREFIX+'appointment'],[])]
                for current,ns,es in queue:
                    if len(es)>=4:continue
                    for e in graph['edges']:
                        if e['type']=='DEPENDS_ON' and e['target']==current and e['source'] not in ns:
                            path={'entity_id':e['source'],'node_ids':ns+[e['source']],'edge_ids':es+[e['id']],'evidence_status':'USER_REPORTED'}
                            paths.append(path);queue.append((e['source'],path['node_ids'],path['edge_ids']))
                root=self.s.require(PREFIX+'appointment');when=root['properties']['starts_at'];clock=when[11:16]
                candidates=[];constraints=[]
                for n in graph['nodes']:
                    p=n['properties']
                    if n['type']=='Person' and p.get('escort')=='CONFIRMED' and p.get('available_from','00:00')<=clock and clock<p.get('unavailable_from','24:00'):candidates.append(n)
                    if n['type']=='Person' and p.get('unavailable_from','24:00')<=clock:constraints.append(n['properties']['name']+' is unavailable at the reported appointment time.')
                if slots.get('deployment_start'):
                    if slots['deployment_start']>=clock and not slots.get('appointment_end'):constraints.append('Aarav’s deployment is at '+slots['deployment_start']+'; the appointment end time is missing, so overlap cannot be ruled out.')
                    elif slots.get('appointment_end','00:00')>slots['deployment_start']:constraints.append('The appointment overlaps Aarav’s deployment.')
                reason=('Travel is no longer required for the reported video visit.' if root['properties'].get('location')=='video' else ('A reported available escort can cover the visit.' if candidates else 'An escort still needs to confirm they can accompany Ramesh.'))
                analysis={'id':stable(req.id+':decision'),'trigger_id':root['id'],'trigger_claim_id':slots.get('_claim_appointment_location') or slots['_claim_appointment_start'],'state':'ACT' if candidates or 'video' in intents else 'WAIT','reason':reason,'affected':paths,'alternatives':[],'constraints':constraints,'evidence':{id:'USER_REPORTED' for id in evidence},'truncated':graph['truncated']}
                prior_rows=self.db.execute("MATCH (a:Action)-[:PRODUCED]->(o:Outcome) WHERE a.status='VERIFIED' AND o.status='VERIFIED' RETURN DISTINCT properties(a),properties(o) LIMIT 20",read=True)
                prior=[{'id':a['id'],'outcome_id':o['id'],'name':'Verified internal task change' if a.get('tool','').startswith('action_task') else a['name'],'retrieved_from':'FalkorDB'} for a,o in prior_rows]
                recalled=self.db.execute("MATCH (d:Decision) WHERE d.record_kind='STORY_DECISION' AND d.conversation_id<>$conversation RETURN d.id,d.name ORDER BY d.created_at DESC LIMIT 3",{'conversation':req.conversation_id},read=True)
                prior.extend({'id':id,'name':name,'retrieved_from':'FalkorDB','kind':'decision'} for id,name in recalled)
                decision=analysis['id'];snapshot=evidence_snapshot(self.s,[n['id'] for n in graph['nodes']]+evidence,[e['id'] for e in graph['edges']])
                self.s.repo.upsert_node(decision,E.Decision,{'name':'Story decision · '+reason,'record_kind':'STORY_DECISION','status':analysis['state'],'analysis':json.dumps(analysis),'evidence_snapshot':json.dumps(snapshot),'message_id':req.id,'conversation_id':req.conversation_id})
                self.s.repo.upsert_edge(decision,R.MENTIONED_IN,req.id,{})
                self.s.repo.upsert_edge(decision,R.RELATED_TO,root['id'],{})
                for id in evidence+[p['id'] for p in prior]:self.s.repo.upsert_edge(decision,R.SUPPORTED_BY,id,{})
                self.db.execute('MATCH (d:Decision {id:$id}) SET d.retrieved_ids=$ids,d.retrieved_at=timestamp()',{'id':decision,'ids':json.dumps([p['id'] for p in prior])})
                route=' → '.join(self.s.require(id)['properties']['name'] for id in max(paths,key=lambda p:len(p['node_ids']))['node_ids']) if paths else 'No downstream dependency has been recorded yet.'
                handoffs.append(('planner',reason+' '+ ' '.join(constraints)+' Evidence path: '+route))
                lines.append(reason)
                if prior:lines.append(f'Retrieved {len(prior)} earlier verified outcome(s) from FalkorDB in this conversation.')
            if slots.get('email_requested') and slots.get('appointment_start'):
                from .story_words import email_draft
                subject,body=email_draft(self.s,slots)
                self.s.repo.upsert_node('story:email-draft',E.Source,{'name':subject,'description':body,'kind':'SYSTEM','record_kind':'EMAIL_DRAFT','recipient':slots.get('priya_email','Unknown'),'status':'DRAFT'})
                self.s.repo.upsert_edge('story:email-draft',R.RELATED_TO,'story:appointment',{})
            # Prepare the exact email using the existing approval contract. Never dispatch here.
            if slots.get('email_requested') and slots.get('priya_email') and slots.get('appointment_start') and 'coordination' in intents:
                from .story_words import email_draft
                subject,body=email_draft(self.s,slots)
                draft=ActionDraft(kind='gmail_send',payload={'to':[slots['priya_email']],'subject':subject,'body':body},reason='User requested an update to Priya. Reported family plan; explicit approval required.',affected_ids=['story:priya','story:appointment'],evidence_ids=[req.id]+([decision] if decision else []))
                action=Actions(self.s).propose(draft,req.id);proposal_ids.append(action['id'])
            if 'video' in intents and slots.get('appointment_start'):
                from .story_checklist import ensure_checklist
                checklist=ensure_checklist(self.s,req.id)
            # Presentation uses persisted current facts, never earlier response text.
            response,handoffs=present(self.s,slots,old,changes,intents,handoffs,proposal_ids,prior)
            self.db.execute('MATCH (s:OrbitStoryState {id:"story"}) SET s.slots=$slots',{'slots':json.dumps(slots)})
        messages=[]
        for index,(agent,text) in enumerate(handoffs):
            shared=self.db.execute("MATCH (r:Task)-[:PRODUCED]->(f:Source) WHERE r.message_id=$message AND r.status='DONE' RETURN r.id,f.id,f.description ORDER BY r.sequence",{'message':req.id},read=True)
            if decision:self.s.require(decision,{E.Decision})
            retrieved=[p['id'] for p in prior]+[row[1] for row in shared]+([decision] if decision else [])
            run=stable(req.id+':story:'+agent)
            self.s.repo.upsert_node(run,E.Task,{'name':LABELS[agent]+' handoff','record_kind':'AGENT_RUN','status':'DONE','owner':agent,'message_id':req.id,'conversation_id':req.conversation_id,'sequence':index,'retrieved_ids':json.dumps(retrieved),'retrieved_at':int(time.time()*1000)})
            if shared:self.s.repo.upsert_edge(run,R.DEPENDS_ON,shared[-1][0],{'note':'Persisted specialist findings retrieved before this handoff'})
            finding=stable(run+':finding')
            self.s.repo.upsert_node(finding,E.Source,{'name':LABELS[agent]+' finding','record_kind':'AGENT_FINDING','description':text,'kind':'SYSTEM','owner':agent,'message_id':req.id,'conversation_id':req.conversation_id})
            self.s.repo.upsert_edge(run,R.PRODUCED,finding,{})
            if decision:self.s.repo.upsert_edge(finding,R.SUPPORTED_BY,decision,{})
            for row in shared:self.s.repo.upsert_edge(finding,R.SUPPORTED_BY,row[1],{})
            for item in prior:self.s.repo.upsert_edge(finding,R.SUPPORTED_BY,item['id'],{})
            messages.append({'agent':agent,'name':LABELS[agent],'content':text,'run_id':run})
        answer=self.s.create_message(req.conversation_id,MessageCreate(id=stable(req.id+':assistant'),role='assistant',content=response))
        self.db.execute('MATCH (s:OrbitStoryState {id:"story"}) SET s.revision=s.revision+1')
        after=self.snapshot();old_nodes={n['id']:n for n in before['nodes']};old_edges={e['id']:e for e in before['edges']}
        def delta(items,old):
            return {'added':[n['id'] for n in items if n['id'] not in old],'updated':[n['id'] for n in items if n['id'] in old and n['properties']!=old[n['id']]['properties']]}
        result={'user':user,'assistant':answer,'handoffs':messages,'graph_revision':state['graph_revision']+1,'entities':delta(after['nodes'],old_nodes),'relationships':delta(after['edges'],old_edges),'evidence':evidence,'decision_id':decision,'previous':prior,'action_ids':proposal_ids,'checklist':checklist,'graph':after,'mode':'deterministic','source':req.source,'intents':parsed['intents'],'clarifications':parsed['questions'],'latency_ms':round((time.perf_counter()-started)*1000,2)}
        result['route_preview']=not parsed['questions'] and bool(parsed['facts'].get('cab_start')) and 'schedule' in parsed['intents']
        edge_ids={edge for path in analysis['affected'] for edge in path['edge_ids']} if decision else set()
        names={n['id']:n['properties'].get('name',n['id']) for n in after['nodes']}
        result['evidence_relationships']=[{'id':e['id'],'source':names[e['source']],'relationship':e['type'],'target':names[e['target']]} for e in after['edges'] if e['id'] in edge_ids]
        if 'recall' in parsed['intents']:
            root_id=PREFIX+('appointment' if slots.get('appointment_start') else 'aarav')
            if any(n['id']==root_id for n in after['nodes']):
                recalled=self.s.repo.traverse(TraversalRequest(root_id=root_id,hops=4,relationship_types=[R.PARENT_OF,R.SIBLING_OF,R.DEPENDS_ON,R.AVAILABLE_FOR,R.ASSIGNED_TO,R.PARTICIPATES_IN],limit=100))
                result['recalled_ids']=[n['id'] for n in recalled['nodes']]
        result['domain_added']=[n['id'] for n in after['nodes'] if n['id'] not in old_nodes and n['type'] in ('Person','Event','Booking','Task') and not n['properties'].get('record_kind')]
        self.db.execute('CREATE (:OrbitStoryTurn {id:$id,response:$response,content:$content,conversation:$conversation,source:$source})',{'id':req.id,'response':json.dumps(result),'content':req.content,'conversation':req.conversation_id,'source':req.source})
        self.db.execute('MATCH (m:Message {id:$id}) SET m.story=$story',{'id':answer['id'],'story':json.dumps({k:v for k,v in result.items() if k not in ('graph','user','assistant')})})
        return result
