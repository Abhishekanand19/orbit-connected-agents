"""Opt-in persistence check: recreate only this project's Compose DB container.
Run after seeding a test graph. Never removes the named volume or any graph.
"""
import argparse
import json
from pathlib import Path
import subprocess
from .config import Settings
from .database import Database

ROOT = Path(__file__).resolve().parents[2]

def snapshot(settings):
    db = Database(settings)
    try:
        nodes = db.execute('MATCH (n:Entity) RETURN properties(n) ORDER BY n.id',read=True)
        edges = db.execute('MATCH ()-[r]->() RETURN properties(r) ORDER BY r.id',read=True)
        if not nodes:
            raise RuntimeError('Seed the selected test graph before verifying persistence.')
        return {'nodes':nodes,'edges':edges}
    finally:
        db.close()

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph',required=True)
    parser.add_argument('--recreate-container',required=True,action='store_true')
    args=parser.parse_args()
    if not args.graph.startswith('orbit_test_'):
        parser.error('Only orbit_test_ graphs can be used for verification.')
    settings=Settings.model_validate({**Settings.from_env().model_dump(),'graph':args.graph})
    if settings.host not in ('localhost','127.0.0.1'):
        parser.error('This check is only for the local Compose database.')
    before=snapshot(settings)
    subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'up','-d',
        '--force-recreate','--wait','falkordb'],cwd=ROOT,check=True)
    after=snapshot(settings)
    if before != after:
        raise RuntimeError('Persistence mismatch after container recreation.')
    print(json.dumps({'persistence':'PASS','graph':settings.graph,
        'nodes':len(after['nodes']),'edges':len(after['edges']),
        'verification':'All node and edge properties identical after container recreation.'}))
