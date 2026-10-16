"""Explicit historical decision/action/outcome records, never execution."""
from typing import Literal
from pydantic import Field
from .models import StrictModel,Id,Text,AwareDatetime,EntityType as E,RelationType as R
from .service import fingerprint
from .database import GraphError

class MemoryRecord(StrictModel):
    id:Id
    type:Literal['Decision','Action','Outcome']
    summary:Text
    reason:Text|None=None
    status:Literal['REPORTED','PENDING','CONFIRMED','REFUTED','CANCELLED']='REPORTED'
    verification_status:Literal['UNVERIFIED','VERIFIED','FAILED']='UNVERIFIED'
    observed_at:AwareDatetime
    conversation_id:Id
    message_id:Id
    evidence_ids:list[Id]=Field(min_length=1,max_length=16)
    affected_ids:list[Id]=Field(default_factory=list,max_length=16)
    previous_id:Id|None=None

def record(service,request):
    refs={request.conversation_id:E.Conversation,request.message_id:E.Message}
    service.require(request.conversation_id,{E.Conversation})
    message=service.require(request.message_id,{E.Message})
    if message['properties']['conversation_id']!=request.conversation_id:
        raise GraphError(422,'wrong_session','Message does not belong to the specified conversation.')
    if message['properties']['role']!='user':
        raise GraphError(422,'unsupported_evidence','Historical records require an explicit user report.')
    edges=[(request.id,R.MENTIONED_IN,request.message_id)]
    for id in set(request.evidence_ids):
        refs[id]=service.require(id,{E.Claim,E.Source,E.Message})['type']
        edges.append((request.id,R.VERIFIED_BY if request.verification_status=='VERIFIED' else R.SUPPORTED_BY,id))
    for id in set(request.affected_ids):
        refs[id]=service.require(id)['type'];edges.append((request.id,R.RELATED_TO,id))
    if request.previous_id:
        required={'Action':E.Decision,'Outcome':E.Action}.get(request.type)
        if not required:raise GraphError(422,'invalid_chain','Only actions and outcomes have a previous record.')
        refs[request.previous_id]=service.require(request.previous_id,{required})['type']
        edges.append((request.id,R.MOTIVATED_BY,request.previous_id) if request.type=='Action' else (request.previous_id,R.PRODUCED,request.id))
    props=request.model_dump(mode='json',exclude={'id','type','evidence_ids','affected_ids','previous_id'},exclude_none=True)
    return service.repo.atomic_record(request.id,E(request.type),props,fingerprint(request.model_dump(mode='json')),refs,edges)
