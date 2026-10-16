"""Explicit test-only server for browser verification; never imported by the app."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uvicorn
from backend.orbit.api import create_app
from backend.orbit.config import Settings
from backend.orbit.database import Database
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.seed import seed
from backend.orbit.models import RelationshipUpsert

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--graph',required=True)
    parser.add_argument('--delete',action='store_true')
    parser.add_argument('--empty',action='store_true')
    args=parser.parse_args()
    if not args.graph.startswith('orbit_test_visuals_'):
        parser.error('Only isolated orbit_test_visuals_ graphs are allowed.')
    settings=Settings.model_validate({**Settings.from_env().model_dump(),'graph':args.graph,
        'allowed_origins':['http://127.0.0.1:5174']})
    db=Database(settings)
    try:
        db.initialize()
        if args.delete or args.empty:
            db.graph.delete()
            if args.empty:
                db.initialize()
        else:
            service=GraphService(GraphRepository(db))
            seed(service)
            for source,kind,target in [('sample:work','RELATED_TO','sample:appointment'),
                ('sample:transport','AFFECTS','sample:appointment'),
                ('sample:transport','RELATED_TO','sample:transport')]:
                service.upsert_relationship(RelationshipUpsert(source=source,type=kind,target=target))
    finally:
        db.close()
    if not args.delete and not args.empty:
        uvicorn.run(create_app(settings),host='127.0.0.1',port=8002)
