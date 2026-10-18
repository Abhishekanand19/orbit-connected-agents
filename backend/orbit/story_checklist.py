"""User-reported local checklist. Never dispatches external provider operations."""
from .models import EntityType as E,RelationType as R
from .database import GraphError
ITEMS={
 'joining': 'Confirm video joining details with the hospital.',
 'travel': 'Review and cancel an actual Uber booking if one exists.',
 'notify': 'Tell Priya that she no longer needs to travel.',
}
def checklist(service):
    result=[]
    for key in ITEMS:
        try:n=service.require('story:checklist:'+key,{E.Task})
        except GraphError as e:
            if e.status==404:continue
            raise
        p=n['properties'];result.append({'id':n['id'],'label':p['name'],'checked':p['status']=='DONE','evidence_status':p.get('evidence_status','PENDING')})
    return result

def ensure_checklist(service,message):
    for key,label in ITEMS.items():
        id='story:checklist:'+key
        try:service.require(id,{E.Task})
        except GraphError as e:
            if e.status!=404:raise
            service.repo.upsert_node(id,E.Task,{'name':label,'status':'OPEN','evidence_status':'PENDING','record_kind':'STORY_CHECKLIST'})
            service.repo.upsert_edge(id,R.RELATED_TO,'story:appointment',{})
            service.repo.upsert_edge(id,R.MENTIONED_IN,message,{})
    return checklist(service)
