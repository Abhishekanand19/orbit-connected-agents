"""Local-owner browser sessions and explicit approval endpoints; no agent approval API."""
import hashlib
import secrets
import time
from fastapi import Request,Response
from .actions import Actions,OWNER
from .action_models import ProposalRequest,ApprovalRequest
from .database import GraphError

def mount_actions(app,settings):
    def service(request):return request.app.state.service

    def browser(request):
        if request.headers.get('origin') not in settings.allowed_origins or request.headers.get('x-orbit-ui')!='1':
            raise GraphError(403,'approval_origin','Use the local ORBIT interface to review and approve actions.')

    def owner(request):
        browser(request)
        token=request.cookies.get('orbit_approval_session','')
        digest=hashlib.sha256(token.encode()).hexdigest()
        rows=service(request).repo.db.execute('MATCH (s:OrbitApprovalSession {id:$id}) WHERE s.expires>$now RETURN s.owner',{'id':digest,'now':time.time()},read=True)
        if not rows or rows[0][0]!=OWNER:raise GraphError(401,'approval_session','Open a local approval session first.')
        return OWNER

    @app.post('/api/actions/session')
    def start_session(request:Request,response:Response):
        browser(request)
        token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
        service(request).repo.db.execute('MERGE (s:OrbitApprovalSession {id:$id}) SET s.owner=$owner,s.expires=$expires',{'id':digest,'owner':OWNER,'expires':time.time()+86400})
        response.set_cookie('orbit_approval_session',token,httponly=True,samesite='strict',max_age=86400,path='/api/actions')
        response.headers['Cache-Control']='no-store'
        return {'owner':OWNER}

    @app.get('/api/actions')
    def list_actions(request:Request,response:Response):
        owner(request);response.headers['Cache-Control']='no-store'
        return {'actions':Actions(service(request)).list()}

    @app.post('/api/actions/propose')
    def propose(body:ProposalRequest,request:Request):
        owner(request)
        return Actions(service(request)).propose(body.draft,body.message_id)

    @app.post('/api/actions/{action_id}/approve')
    def approve(action_id:str,body:ApprovalRequest,request:Request):
        manager=Actions(service(request));manager.approve(action_id,body.digest,owner(request))
        return manager.dispatch(action_id,body.digest)

    @app.post('/api/actions/{action_id}/reject')
    def reject(action_id:str,body:ApprovalRequest,request:Request):
        return Actions(service(request)).reject(action_id,body.digest,owner(request))

    @app.post('/api/actions/{action_id}/retry')
    def retry(action_id:str,body:ApprovalRequest,request:Request):
        return Actions(service(request)).retry(action_id,body.digest,owner(request))

    @app.post('/api/actions/{action_id}/verify')
    def verify(action_id:str,body:ApprovalRequest,request:Request):
        owner(request)
        return Actions(service(request)).dispatch(action_id,body.digest,verify=True)

    @app.post('/api/actions/{action_id}/refresh')
    def refresh(action_id:str,body:ApprovalRequest,request:Request):
        return Actions(service(request)).refresh(action_id,body.digest,owner(request))
