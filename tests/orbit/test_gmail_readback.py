"""Read-only regression: no send endpoint is allowed, even in fixtures."""
import base64
from email.message import EmailMessage
from uuid import uuid5,NAMESPACE_URL
import httpx
import pytest
from backend.orbit.action_providers import ActionProviders

@pytest.mark.parametrize('fault',[None,'id','sender','recipient','subject','body','sent','ambiguous','unbound_rfc'])
def test_api_identifier_and_rewritten_rfc_header(fault):
    action='action:readback-test';key=str(uuid5(NAMESPACE_URL,action))
    message=EmailMessage()
    message['From']='wrong@example.test' if fault=='sender' else 'owner@example.test'
    message['To']='wrong@example.test' if fault=='recipient' else 'owner@example.test'
    message['Subject']='Wrong' if fault=='subject' else 'Test'
    message['Message-ID']='<provider-rewritten@mail.gmail.com>'
    message.set_content('Wrong' if fault=='body' else 'Harmless test.')
    calls=[]
    def respond(req):
        assert req.method=='GET';calls.append(req.url.path)
        if req.url.path.endswith('/profile'):return httpx.Response(200,json={'emailAddress':'owner@example.test'})
        if req.url.path.endswith('/messages'):
            return httpx.Response(200,json={'messages':[{'id':'api-id'}]* (2 if fault=='ambiguous' else 1)})
        assert req.url.path.endswith('/messages/api-id')
        return httpx.Response(200,json={'id':'other-id' if fault=='id' else 'api-id','raw':base64.urlsafe_b64encode(message.as_bytes()).decode(),'labelIds':[] if fault=='sent' else ['SENT']})
    class Auth:
        def token(self,force=False):return 'fixture-token'
    provider=ActionProviders(auth=Auth(),transport=httpx.MockTransport(respond))
    receipt={} if fault in ('ambiguous','unbound_rfc') else {'id':'api-id','rfc_message_id':key+'@orbit.local'}
    result=provider.verify('gmail_send',{'to':['owner@example.test'],'cc':[],'subject':'Test','body':'Harmless test.'},action,receipt)
    assert result['verified']==(fault is None)
    if fault is None:
        assert result['readback']['rfc_message_id']=='<provider-rewritten@mail.gmail.com>'
        assert result['provider_id']=='api-id' and len(calls)==2
