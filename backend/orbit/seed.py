"""Optional test fixture. Never imported by normal application startup."""
import argparse
from datetime import datetime, timezone
import json
from .config import Settings
from .database import Database
from .repository import GraphRepository
from .service import GraphService
from .models import NodeUpsert, RelationshipUpsert, ConversationCreate, MessageCreate, ClaimCreate, TraversalRequest


def seed(service):
    nodes = [('sample:priya','Person','Priya'),('sample:dad','Person','Dad'),
        ('sample:appointment','Event','Hospital appointment'),
        ('sample:transport','Booking','Transport booking'),('sample:work','Task','Work commitment'),
        ('sample:bot','Bot','Orbit Coordinator')]
    for node_id,kind,name in nodes:
        service.upsert_node(node_id,NodeUpsert(type=kind,properties={'name':name}))
    for source,kind,target in [
        ('sample:appointment','DEPENDS_ON','sample:transport'),
        ('sample:transport','ASSIGNED_TO','sample:priya'),
        ('sample:work','ASSIGNED_TO','sample:priya'),
        ('sample:dad','PARTICIPATES_IN','sample:appointment')]:
        service.upsert_relationship(RelationshipUpsert(source=source,type=kind,target=target))
    service.create_conversation(ConversationCreate(id='sample:conversation',bot_id='sample:bot',title='Optional graph fixture'))
    service.create_message('sample:conversation',MessageCreate(id='sample:message',role='user',
        content='Priya might take Dad to the hospital.',mentioned_ids=['sample:priya','sample:appointment']))
    try:
        source = service.require('sample:source')
        observed_at = source['properties']['observed_at']
    except Exception as error:
        from .database import GraphError
        if not isinstance(error,GraphError) or error.status != 404:
            raise
        observed_at = datetime.now(timezone.utc).isoformat()
    service.upsert_node('sample:source',NodeUpsert(type='Source',properties={
        'name':'Explicit seed message','kind':'USER_MESSAGE','external_id':'sample:message','observed_at':observed_at}))
    service.create_claim(ClaimCreate(id='sample:claim',text='Priya might provide transport.',status='PENDING',
        source_id='sample:source',message_id='sample:message',subject_ids=['sample:priya','sample:transport'],observed_at=observed_at))
    return service.repo.traverse(TraversalRequest(root_id='sample:appointment',hops=3,
        relationship_types=['DEPENDS_ON','ASSIGNED_TO']))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Explicitly seed an ORBIT test graph.')
    parser.add_argument('--graph',required=True,help='Must begin orbit_test_')
    args = parser.parse_args()
    if not args.graph.startswith('orbit_test_'):
        parser.error('Seed data is restricted to an explicitly named orbit_test_ graph.')
    settings = Settings.from_env().model_copy(update={'graph':args.graph})
    settings = Settings.model_validate(settings.model_dump())
    db = Database(settings)
    try:
        print(json.dumps(seed(GraphService(GraphRepository(db))),indent=2))
    finally:
        db.close()
