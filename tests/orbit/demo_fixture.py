"""Isolated browser demo fixture; no LLM or provider operations."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uvicorn
from backend.orbit.demo import Demo
from backend.orbit.api import create_app
from backend.orbit.database import Database
from backend.orbit.repository import GraphRepository
from backend.orbit.service import GraphService
from backend.orbit.config import Settings
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--graph',required=True);p.add_argument('--delete',action='store_true');a=p.parse_args()
 if not a.graph.startswith('orbit_test_demo_'):p.error('Isolated graph required')
 settings=Settings.from_env().model_copy(update={'graph':a.graph,'allowed_origins':['http://127.0.0.1:5174']})
 db=Database(settings);db.initialize()
 if a.delete:
  db.graph.delete();db.close();sys.exit(0)
 Demo(GraphService(GraphRepository(db))).seed();db.close()
 uvicorn.run(create_app(settings),host='127.0.0.1',port=8002)
