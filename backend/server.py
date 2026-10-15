import json
import re
import threading
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.sandbox import ROOT, SESSION, probe
from backend.graph import sync, query
from backend.agents import investigate, plan
from backend.memory import recall, new_session
from backend.apply import apply

app=FastAPI(title='PathLock')
lock=threading.Lock()

@app.middleware('http')
async def local_only(request:Request, call_next):
    if request.method=='POST' and request.headers.get('origin') not in (None,'http://127.0.0.1:8000','http://localhost:8000'):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Origin denied'},status_code=403)
    return await call_next(request)

def explanation(role, evidence):
    client=SESSION.client('bedrock-runtime')
    system=[{'text':f'You are PathLock {role}. First call read_graph_context to retrieve persistent context. Then explain the deterministic evidence in at most 35 words. Never invent results. An action in a decision is a proposal awaiting human approval, not an applied change. Never expose chain of thought.'}]
    messages=[{'role':'user','content':[{'text':json.dumps(evidence)}]}]
    tools={'tools':[{'toolSpec':{'name':'read_graph_context','description':'Load persistent ownership, protected business capability and previously verified decisions from FalkorDB.','inputSchema':{'json':{'type':'object','properties':{},'additionalProperties':False}}}}]}
    first=client.converse(modelId='amazon.nova-micro-v1:0',system=system,messages=messages,toolConfig=tools,inferenceConfig={'maxTokens':300,'temperature':0.1})
    calls=[c['toolUse'] for c in first['output']['message']['content'] if 'toolUse' in c]
    if not calls or any(c['name']!='read_graph_context' for c in calls):
        raise RuntimeError('Agent did not request its required graph context tool')
    messages.append(first['output']['message'])
    messages.append({'role':'user','content':[{'toolResult':{'toolUseId':c['toolUseId'],'content':[{'json':{'current_evidence':evidence,'persistent_memory':recall()}}]}} for c in calls]})
    response=client.converse(modelId='amazon.nova-micro-v1:0',system=system,messages=messages,toolConfig=tools,inferenceConfig={'maxTokens':180,'temperature':0.1})
    summary=''.join(c.get('text','') for c in response['output']['message']['content'])
    summary=re.sub(r'<(?:thinking|think)>.*?</(?:thinking|think)>','',summary,flags=re.S|re.I).strip()
    if '<thinking>' in summary.lower() or '<think>' in summary.lower():
        raise RuntimeError('Model returned an incomplete summary')
    return summary

@app.get('/api/state')
def state():
    sync()
    data=json.loads((ROOT/'.aws/sandbox.json').read_text())
    paths=query('MATCH p=(:Application {id:"pathlock:app"})-[:RUNS_AS|CAN_ASSUME|CAN_ACCESS*1..6]->(:SensitiveResource {id:"pathlock:secret"}) RETURN length(p)')[1]
    return {'aws':True,'graph':True,'scenario':data.get('scenario',1),'paths':len(paths),'memory':recall(),'order':probe('order')}

@app.post('/api/{operation}')
def action(operation:str, request:dict):
    if not lock.acquire(blocking=False):raise HTTPException(409,'An operation is running')
    try:
        if operation=='analyze':
            sync(); finding=investigate()
            return {'finding':finding,'explanation':explanation('Investigator',{'finding':finding,'path':'Order App → Order Access → elevated demo role → Private Secret'})}
        if operation=='plan':
            sync(); result=plan(request['finding']);result['memory']=recall()
            result['explanation']=explanation('Remediator',result)
            return result
        if operation=='probe':return {'security':probe('probe'),'business':probe('order')}
        if operation=='apply':
            pending=json.loads((ROOT/'.aws/pending-decision.json').read_text())
            if request.get('decision')!=pending['decision'] or request.get('approved') is not True:raise HTTPException(409,'Explicit approval of current decision required')
            apply('Local demo operator')
            return {'security':probe('probe'),'business':probe('order'),'memory':recall()}
        if operation=='session':return new_session()
        raise HTTPException(404,'Unknown operation')
    except HTTPException:raise
    except Exception as error:
        raise HTTPException(503,f'Operation failed ({type(error).__name__}); no success assumed') from error
    finally:lock.release()

app.mount('/assets',StaticFiles(directory=ROOT/'frontend/dist/assets'),name='assets')
@app.get('/')
def index():return FileResponse(ROOT/'frontend/dist/index.html')
