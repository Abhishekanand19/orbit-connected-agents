"""User-supplied citations, kept separate from retrieved/verified evidence."""
from .models import EntityType as E, ClaimCreate
from .extraction import stable

ARTICLE='https://indianexpress.com/article/cities/bangalore/bengaluru-cjp-protest-march-police-permission-freedom-park-10924808/'
TOPIC='https://indianexpress.com/about/cjp-protest/'

def record_references(service,message_id,observed,subjects):
    for key,url in [('article',ARTICLE),('topic',TOPIC)]:
        service.repo.upsert_node('story:indian-express:'+key,E.Source,{
            'name':'The Indian Express · '+('Bengaluru protest report' if key=='article' else 'CJP protest topic'),
            'uri':url,'publisher':'The Indian Express','kind':'MANUAL','observed_at':observed,
            'provenance':'User-supplied scenario reference; article content not retrieved',
            'retrieval_status':'NOT_RETRIEVED','reported_event_date':'2026-10-16',
            'evidence_status':'UNVERIFIED',
        })
    claim=stable(message_id+':protest-reference')
    service.create_claim(ClaimCreate(id=claim,
        text='User-supplied article description reports a protest-related rally/march in Bengaluru on October 16, 2026. Article content has not been independently retrieved. It provides no verified hospital-closure evidence.',
        status='UNVERIFIED',source_id='story:indian-express:article',message_id=message_id,
        subject_ids=subjects,observed_at=observed))
    return claim
