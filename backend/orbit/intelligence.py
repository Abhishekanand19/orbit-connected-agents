"""Deterministic bounded impact analysis. Produces proposals, never mutations to arrangements."""
import json
from datetime import datetime
from typing import Literal
from uuid import uuid4
from pydantic import Field,model_validator
from .models import StrictModel,Id,AwareDatetime,EntityType as E,RelationType as R
from .repository import node_view,edge_view
from .service import fingerprint
from .database import GraphError

def calendar_constraints(result, start, end):
 """Read observations never promote a claim or authorize an action."""
 from zoneinfo import ZoneInfo
 from .integration_providers import interval
 a,b=interval(start,end);conflicts=[];unknown=bool(result.get('truncated'))
 for event in result.get('items',[]):
  if event.get('status')=='cancelled' or event.get('transparency')=='transparent':continue
  try:
   def instant(value):
    if not isinstance(value,dict):raise ValueError()
    if value.get('dateTime'):
     dt=datetime.fromisoformat(value['dateTime'].replace('Z','+00:00'))
     return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo(value.get('timeZone') or result['time_zone']))
    return datetime.fromisoformat(value['date']).replace(tzinfo=ZoneInfo(result['time_zone']))
   x,y=instant(event['start']),instant(event['end'])
   if y<=x:raise ValueError()
   if x<b and a<y:conflicts.append(event['id'])
  except (KeyError,TypeError,ValueError):unknown=True
 return {'overlapping_event_ids':conflicts,'incomplete':unknown,'state':'WAIT',
         'reason':'External schedule observations require interpretation and verification; no arrangement changed.'}

class ImpactRequest(StrictModel):
 root_id:Id
 trigger_claim_id:Id
 starts_at:AwareDatetime|None=None
 ends_at:AwareDatetime|None=None
 hops:int=Field(default=3,ge=1,le=4)
 scope_ids:list[Id]=Field(default_factory=list,max_length=100)
 @model_validator(mode='after')
 def interval(self):
  if bool(self.starts_at)!=bool(self.ends_at) or (self.starts_at and self.ends_at<=self.starts_at):raise ValueError('Provide a positive start/end interval together')
  return self
class ImpactPath(StrictModel):
 entity_id:str
 node_ids:list[str]
 edge_ids:list[str]
 evidence_status:str
class Alternative(StrictModel):
 entity_id:str
 state:Literal['ACT','WAIT','CONFLICT','NO_CHANGE']
 reason:str
 edge_ids:list[str]=Field(default_factory=list)
 constraint_ids:list[str]=Field(default_factory=list)
class ImpactResult(StrictModel):
 id:str
 trigger_id:str
 trigger_claim_id:str
 state:Literal['ACT','WAIT','CONFLICT','NO_CHANGE']
 reason:str
 affected:list[ImpactPath]
 unnecessary_ids:list[str]=Field(default_factory=list)
 unchanged_ids:list[str]
 alternatives:list[Alternative]
 constraints:list[str]
 constraint_edge_ids:list[str]=Field(default_factory=list)
 proposed_changes:list[str]
 evidence:dict[str,str]
 truncated:bool

class ImpactEngine:
 def __init__(self,service):self.s=service;self.db=service.repo.db
 def claim_state(self,id):
  claim=self.s.require(id,{E.Claim})
  status=claim['properties']['status']
  if status!='CONFIRMED':return status
  # Confirmation alone is user-reported; ACT requires explicit verification provenance.
  rows=self.db.execute("MATCH (:Claim {id:$id})-[:VERIFIED_BY]->(s:Source) WHERE s.kind IN ['MANUAL','DOCUMENT'] RETURN s.id LIMIT 1",{'id':id},read=True)
  return 'VERIFIED' if rows else 'CONFIRMED'
 def edge_state(self,e):
  state=e['properties'].get('evidence_state','UNVERIFIED')
  if state in ('REFUTED','SUPERSEDED'):return state
  evidence=e['properties'].get('evidence_id')
  if not evidence or state!='CONFIRMED':return state if state!='CONFIRMED' else 'UNVERIFIED'
  try:return self.claim_state(evidence)
  except GraphError:return 'UNVERIFIED'
 def neighbors(self,id):
  rows=self.db.execute("""MATCH (a:Entity)-[r]->(b:Entity)
   WHERE (b.id=$id AND type(r)='DEPENDS_ON') OR (a.id=$id AND type(r) IN ['AFFECTS','ASSIGNED_TO'])
   RETURN properties(a),properties(r),properties(b) ORDER BY r.id LIMIT 101""",{'id':id},read=True)
  return rows
 def busy(self,person,root,start,end):
  rows=self.db.execute("""MATCH (w:Entity)-[r:ASSIGNED_TO]->(:Entity {id:$id})
   WHERE w.id<>$root RETURN properties(w),properties(r) ORDER BY w.id LIMIT 101""",{'id':person,'root':root},read=True)
  conflicts=[];unknown=len(rows)>100
  if not start or not end:return [],True
  for props,rel in rows[:100]:
   n=node_view(props);e=edge_view(rel)
   self.constraint_edges[e['id']]=self.edge_state(e)
   if n['properties'].get('status') in ('CANCELLED','DONE') or self.edge_state(e) in ('REFUTED','SUPERSEDED'):continue
   try:
    a=datetime.fromisoformat(n['properties']['starts_at'].replace('Z','+00:00'));b=datetime.fromisoformat(n['properties']['ends_at'].replace('Z','+00:00'))
    if a.tzinfo is None or b.tzinfo is None or b<=a:raise ValueError()
   except (KeyError,ValueError):unknown=True;continue
   if a<end and start<b:
    if self.edge_state(e)=='VERIFIED':conflicts.append(n['id'])
    else:unknown=True
  return conflicts,unknown
 def analyze(self,req,external_observations=None):
  self.constraint_edges={}
  root=self.s.require(req.root_id)
  for id in req.scope_ids:self.s.require(id)
  trigger=self.claim_state(req.trigger_claim_id)
  links=self.db.execute("MATCH (:Claim {id:$claim})-[:RELATED_TO]->(:Entity {id:$root}) RETURN 1",{'claim':req.trigger_claim_id,'root':req.root_id},read=True)
  if not links:raise GraphError(422,'unrelated_trigger','Trigger claim must cite the changed entity.')
  evidence={req.trigger_claim_id:trigger};seen={req.root_id};queue=[(req.root_id,[req.root_id],[],True)];affected=[];truncated=False;constraints=[];uncertain_prerequisite=False
  for current,nodes,edges,verified in queue:
   if len(edges)>=req.hops:continue
   rows=self.neighbors(current);truncated|=len(rows)>100
   for a,r,b in rows[:100]:
    e=edge_view(r);state=self.edge_state(e);evidence[e['id']]=state
    if state in ('REFUTED','SUPERSEDED'):continue
    next_id=a['id'] if e['type']=='DEPENDS_ON' else b['id']
    if next_id in seen:continue
    seen.add(next_id);path=ImpactPath(entity_id=next_id,node_ids=nodes+[next_id],edge_ids=edges+[e['id']],evidence_status='VERIFIED' if verified and state=='VERIFIED' else 'UNVERIFIED')
    affected.append(path)
    if len(seen)>=100:truncated=True;break
    if e['type']!='ASSIGNED_TO':queue.append((next_id,path.node_ids,path.edge_ids,path.evidence_status=='VERIFIED'))
   if len(seen)>=100:break
  # Validate prerequisites of affected work, independently of incoming impact direction.
  for id in list(seen):
   rows=self.db.execute("MATCH (:Entity {id:$id})-[r:DEPENDS_ON]->(p:Entity) RETURN properties(p),properties(r) LIMIT 101",{'id':id},read=True)
   truncated|=len(rows)>100
   for props,rel in rows[:100]:
    e=edge_view(rel);state=self.edge_state(e);evidence[e['id']]=state
    if state in ('PENDING','UNVERIFIED','CONFIRMED'):uncertain_prerequisite=True
    if state=='VERIFIED' and props.get('status')=='CANCELLED':constraints.append(props['id'])
  # A conditional dependency is obsolete only when verified current facts no longer
  # satisfy its declared requirement. This is domain-neutral, not a demo branch.
  unnecessary=[]
  for path in affected:
   target=self.s.require(path.entity_id)
   if target['type']!='Task' or target['properties'].get('status') in ('DONE','CANCELLED'):continue
   for edge_id in path.edge_ids:
    rel=self.s.repo.get_edge(edge_id)
    required=rel['properties'].get('required_location')
    if rel['type']=='DEPENDS_ON' and rel['target']==req.root_id and rel['source']==path.entity_id and required and self.edge_state(rel)=='VERIFIED':
     prerequisite=self.s.require(rel['target'])
     actual=prerequisite['properties'].get('location')
     if actual and actual!=required and trigger=='VERIFIED' and path.evidence_status=='VERIFIED':
      unnecessary.append(path.entity_id);break
  start=req.starts_at;end=req.ends_at
  if not start:
   try:start=datetime.fromisoformat(root['properties']['starts_at'].replace('Z','+00:00'));end=datetime.fromisoformat(root['properties']['ends_at'].replace('Z','+00:00'))
   except (KeyError,ValueError):start=end=None
  rows=self.db.execute("""MATCH (a:Entity)-[r]->(b:Entity) WHERE
   (a.id=$root AND type(r)='ASSIGNED_TO') OR (b.id=$root AND type(r)='AVAILABLE_FOR')
   RETURN properties(a),properties(r),properties(b) ORDER BY r.id LIMIT 101""",{'root':req.root_id},read=True)
  truncated|=len(rows)>100;alternatives=[]
  for a,r,b in rows[:100]:
   e=edge_view(r);person=b['id'] if e['type']=='ASSIGNED_TO' else a['id'];confidence=self.edge_state(e);evidence[e['id']]=confidence
   conflicts,unknown=self.busy(person,req.root_id,start,end)
   if confidence in ('REFUTED','SUPERSEDED') or conflicts:state='CONFLICT';reason='Unavailable evidence or overlapping verified responsibility.'
   elif trigger!='VERIFIED' or confidence!='VERIFIED' or unknown or truncated or uncertain_prerequisite:state='WAIT';reason='Trigger, availability, schedule completeness or assignment evidence needs verification.'
   elif constraints:state='CONFLICT';reason='A required prerequisite is cancelled.'
   else:state='NO_CHANGE' if e['type']=='ASSIGNED_TO' else 'ACT';reason='No conflict in the bounded stored schedule; verified evidence supports this proposal.'
   alternatives.append(Alternative(entity_id=person,state=state,reason=reason,edge_ids=[e['id']],constraint_ids=conflicts))
  if trigger in ('REFUTED','SUPERSEDED'):state='NO_CHANGE';reason='Trigger is refuted or superseded; do not change arrangements.'
  elif trigger!='VERIFIED' or truncated:state='WAIT';reason='Verified current trigger and complete bounded context are required.'
  elif constraints:state='CONFLICT';reason='A verified prerequisite is cancelled.'
  elif uncertain_prerequisite:state='WAIT';reason='Prerequisite evidence is not verified.'
  elif unnecessary:state='ACT';reason='Verified current context no longer satisfies a conditional dependency; review only the active dependent tasks.'
  elif any(a.state=='NO_CHANGE' for a in alternatives):state='NO_CHANGE';reason='An existing assignment remains feasible in stored constraints.'
  elif any(p.evidence_status!='VERIFIED' for p in affected):state='WAIT';reason='Dependency evidence requires verification.'
  elif any(a.state=='ACT' for a in alternatives):state='ACT';reason='A verified graph-linked alternative is feasible; proposal only.'
  elif any(a.state=='WAIT' for a in alternatives) or any(p.evidence_status!='VERIFIED' for p in affected):state='WAIT';reason='Relevant confirmation or schedule information is missing.'
  elif alternatives:state='CONFLICT';reason='All stored candidates violate current constraints.'
  elif affected:state='WAIT';reason='Dependencies are affected but no verified alternative is recorded.'
  else:state='NO_CHANGE';reason='No active impact path found within the requested scope and depth.'
  for observation in external_observations or []:
   data=observation['result'];source_id=observation['id']
   evidence[source_id]='UNVERIFIED'
   if data.get('overlapping_event_ids') or data.get('incomplete'):
    constraints.append(source_id)
    if state not in ('CONFLICT',) and trigger not in ('REFUTED','SUPERSEDED'):
     state='WAIT';reason='External calendar observations contain overlaps or incomplete results; verify before changing arrangements.'
    for alternative in alternatives:
     if alternative.state=='ACT':
      alternative.state='WAIT';alternative.reason='External calendar constraints require verification.'
  changes=[f'Propose assigning {req.root_id} to {a.entity_id}; no external action executed.' for a in alternatives if a.state=='ACT'] if state=='ACT' else []
  if state=='ACT':changes.extend(f'Propose cancelling internal task {id}; its verified dependency condition no longer holds. No action executed.' for id in unnecessary)
  evidence.update(self.constraint_edges)
  considered=seen|{a.entity_id for a in alternatives}|{id for a in alternatives for id in a.constraint_ids}|set(constraints)
  result=ImpactResult(id='impact:'+str(uuid4()),trigger_id=req.root_id,trigger_claim_id=req.trigger_claim_id,state=state,reason=reason,affected=affected,unnecessary_ids=unnecessary,unchanged_ids=[id for id in req.scope_ids if id not in considered],alternatives=alternatives,constraints=constraints,constraint_edge_ids=list(self.constraint_edges),proposed_changes=changes,evidence=evidence,truncated=truncated)
  refs={req.root_id:E(root['type']),req.trigger_claim_id:E.Claim};links=[(result.id,R.RELATED_TO,req.root_id),(result.id,R.SUPPORTED_BY,req.trigger_claim_id)]
  for observation in external_observations or []:
   refs[observation['id']]=E.Source;links.append((result.id,R.SUPPORTED_BY,observation['id']))
  props={'name':'Impact proposal: '+state,'summary':reason,'status':state,'record_kind':'IMPACT_ANALYSIS','executed':False,'analysis':result.model_dump_json()}
  from .receipts import impact_snapshot
  props['evidence_snapshot']=json.dumps(impact_snapshot(self.s,result))
  self.s.repo.atomic_record(result.id,E.Decision,props,fingerprint(result.model_dump()),refs,links)
  return result
