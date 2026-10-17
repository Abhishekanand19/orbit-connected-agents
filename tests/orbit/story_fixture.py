"""Isolated browser host with model and external-write tripwires."""
import argparse,sys,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uvicorn
from backend.orbit.config import Settings
from backend.orbit.database import Database
from backend.orbit.api import create_app
from backend.orbit import llm
from backend.orbit.action_providers import ActionProviders

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--graph',required=True);p.add_argument('--delete',action='store_true');args=p.parse_args()
    if not args.graph.startswith('orbit_test_story_'):p.error('Test namespace required')
    settings=Settings.from_env().model_copy(update={'graph':args.graph,'allowed_origins':['http://127.0.0.1:5174']})
    db=Database(settings);db.initialize()
    if args.delete:
        for key,graph in db.execute('MATCH (w:OrbitStoryWorkspace) RETURN w.id,w.graph',read=True):
            assert re.fullmatch('[a-f0-9]{32}',key) and graph=='orbit_story_'+key
            child=Database(settings.model_copy(update={'graph':graph}));child.initialize();child.graph.delete();child.close()
        db.graph.delete();db.close();sys.exit(0)
    db.close()
    def forbidden(*a,**k):raise AssertionError('No LLM or external write allowed in story browser tests')
    llm.generate=forbidden;ActionProviders.perform=forbidden
    uvicorn.run(create_app(settings),host='127.0.0.1',port=8002)
