"""Single-attempt writes and independent readback. Never retry uncertain sends."""
import base64
import json
import os
from datetime import datetime
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses
from urllib.parse import quote
from uuid import NAMESPACE_URL,uuid5
import httpx
from .database import GraphError
from .integration_providers import Providers
from .integration_auth import WRITE_SCOPES


class WriteFailure(Exception):
    def __init__(self, message, uncertain=False, retryable=False):
        self.message,self.uncertain,self.retryable=message,uncertain,retryable
        super().__init__(message)


def event_body(payload, action_id):
    changes=payload['changes']
    body={k:v for k,v in changes.items() if k in ('summary','description','location')}
    if 'starts_at' in changes:
        body.update(start={'dateTime':changes['starts_at']},end={'dateTime':changes['ends_at']})
    if 'attendees' in changes:body['attendees']=[{'email':e} for e in changes['attendees']]
    body['extendedProperties']={'private':{'orbit_action':action_id}}
    return body


def event_matches(event,payload,action_id):
    if event.get('extendedProperties',{}).get('private',{}).get('orbit_action')!=action_id:return False
    for k,v in payload['changes'].items():
        if k in ('starts_at','ends_at'):
            actual=event.get('start' if k=='starts_at' else 'end',{}).get('dateTime','')
            try:
                if datetime.fromisoformat(actual.replace('Z','+00:00'))!=datetime.fromisoformat(v.replace('Z','+00:00')):return False
            except ValueError:return False
        elif k=='attendees':
            if sorted(e.get('email','').casefold() for e in event.get('attendees',[]))!=sorted(e.casefold() for e in v):return False
        elif event.get(k,'')!=v:return False
    return True


class ActionProviders(Providers):
    def account(self,kind):
        # Persist only a connection fingerprint, never a credential.
        from .service import fingerprint
        if kind.startswith(('calendar','gmail')):
            saved=self.auth.vault.load()
            if not saved or not saved.get('connection_id'):raise GraphError(401,'google_reconnect','Reconnect Google before proposing external actions.')
            return saved['connection_id']
        if kind=='slack_post':
            token=os.getenv('SLACK_BOT_TOKEN')
            if not token:raise GraphError(503,'slack_unconfigured','Configure SLACK_BOT_TOKEN.')
            return fingerprint(token)
        return 'local-owner'

    def write(self,provider,path,body,params=None,etag=None):
        if provider=='slack':
            token=os.getenv('SLACK_BOT_TOKEN')
            if not token:raise WriteFailure('SLACK_BOT_TOKEN is missing.',retryable=True)
        else:
            scope=WRITE_SCOPES[0] if provider=='gmail' else WRITE_SCOPES[1]
            try:
                self.auth.require_scopes([scope]);token=self.auth.token()
            except GraphError as exc:raise WriteFailure(exc.message,retryable=True) from None
        origin={'gmail':'https://gmail.googleapis.com/gmail/v1/users/me/',
                'calendar':'https://www.googleapis.com/calendar/v3/','slack':'https://slack.com/api/'}[provider]
        headers={'Authorization':'Bearer '+token}
        if etag:headers['If-Match']=etag
        method='PATCH' if etag else 'POST'
        try:
            with httpx.Client(transport=self.transport,timeout=20,follow_redirects=False) as client:
                response=client.request(method,origin+path,json=body,params=params,headers=headers)
        except httpx.ConnectError:
            raise WriteFailure('Connection failed before a provider response; retry requires the same approval.',retryable=True) from None
        except httpx.HTTPError:
            raise WriteFailure('Provider transport failed. The write may have completed; readback only.',uncertain=True) from None
        if response.status_code in (400,401,403,404,412,429):
            raise WriteFailure('Provider rejected the write (HTTP '+str(response.status_code)+'). Check permissions or refresh the proposal.',retryable=response.status_code in (401,403,429))
        if response.status_code>=500 or response.status_code not in (200,201):
            raise WriteFailure('Provider did not confirm the write. Readback is required.',uncertain=True)
        try:data=response.json()
        except ValueError:raise WriteFailure('Invalid provider acknowledgement; readback is required.',uncertain=True) from None
        if provider=='slack' and not data.get('ok'):
            error=data.get('error')
            known={'missing_scope','not_in_channel','channel_not_found','invalid_auth','token_revoked','ratelimited','msg_too_long'}
            raise WriteFailure('Slack rejected the post: '+(error if error in known else 'unconfirmed_error'),uncertain=error not in known,retryable=error in ('missing_scope','ratelimited','not_in_channel'))
        return data

    def perform(self,kind,payload,action_id):
        key=str(uuid5(NAMESPACE_URL,action_id))
        if kind.startswith('calendar'):
            body=event_body(payload,action_id)
            path='calendars/'+quote(payload['calendar_id'],safe='')+'/events'
            if kind=='calendar_create':body['id']='orbit'+key.replace('-','')
            else:
                path+='/'+quote(payload['event_id'],safe='')
                # Keep other private metadata; If-Match prevents a concurrent overwrite.
                before=self.get('calendar',path)
                if before.get('etag')!=payload['expected_etag']:raise WriteFailure('Calendar event changed since proposal. Create a fresh proposal.')
                body['extendedProperties']['private']={**before.get('extendedProperties',{}).get('private',{}),'orbit_action':action_id}
            data=self.write('calendar',path,body,{'sendUpdates':payload['send_updates']},payload.get('expected_etag'))
            if not data.get('id'):raise WriteFailure('Calendar acknowledgement lacks an event ID.',uncertain=True)
            return {'id':data['id'],'calendar_id':payload['calendar_id']}
        if kind=='gmail_send':
            message=EmailMessage();message['To']=', '.join(payload['to']);message['Subject']=payload['subject']
            if payload['cc']:message['Cc']=', '.join(payload['cc'])
            message['Message-ID']='<'+key+'@orbit.local>'
            message.set_content(payload['body'])
            raw=base64.urlsafe_b64encode(message.as_bytes()).decode()
            data=self.write('gmail','messages/send',{'raw':raw})
            if not data.get('id'):raise WriteFailure('Gmail acknowledgement lacks a message ID.',uncertain=True)
            return {'id':data['id'],'rfc_message_id':key+'@orbit.local'}
        if kind=='slack_post':
            data=self.write('slack','chat.postMessage',{'channel':payload['channel_id'],'text':payload['text'],
                'client_msg_id':key,'parse':'none','link_names':False,'unfurl_links':False,'unfurl_media':False})
            if not data.get('ts') or data.get('channel')!=payload['channel_id']:raise WriteFailure('Slack acknowledgement lacks the expected channel/timestamp.',uncertain=True)
            return {'ts':data['ts'],'channel':data['channel'],'client_msg_id':key}
        raise WriteFailure('Unsupported external action.')

    def verify(self,kind,payload,action_id,receipt):
        key=str(uuid5(NAMESPACE_URL,action_id))
        if kind.startswith('calendar'):
            id=receipt.get('id') or payload.get('event_id') or 'orbit'+key.replace('-','')
            data=self.get('calendar','calendars/'+quote(payload['calendar_id'],safe='')+'/events/'+quote(id,safe=''))
            return {'verified':event_matches(data,payload,action_id),'provider_id':id,'readback':{k:data.get(k) for k in ('id','etag','summary','start','end','attendees','extendedProperties')}}
        if kind=='gmail_send':
            id=receipt.get('id')
            if not id:
                found=self.get('gmail','messages',{'q':'in:sent rfc822msgid:'+key+'@orbit.local','maxResults':2})
                if len(found.get('messages',[]))!=1:return {'verified':False,'reason':'No unique sent message found; do not resend.'}
                id=found['messages'][0]['id']
            data=self.get('gmail','messages/'+quote(id,safe=''),{'format':'raw'})
            raw=data.get('raw','');message=BytesParser(policy=default).parsebytes(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
            body=message.get_body(preferencelist=('plain',))
            recipients=lambda name:sorted(address.casefold() for _,address in getaddresses(message.get_all(name,[])))
            verified=('SENT' in data.get('labelIds',[]) and message.get('Message-ID')=='<'+key+'@orbit.local>'
                and recipients('to')==sorted(a.casefold() for a in payload['to']) and recipients('cc')==sorted(a.casefold() for a in payload['cc'])
                and str(message.get('Subject',''))==payload['subject'] and body is not None
                and body.get_content().replace('\r\n','\n').rstrip('\n')==payload['body'].replace('\r\n','\n').rstrip('\n'))
            return {'verified':verified,'provider_id':id,'readback':{'id':id,'labels':data.get('labelIds',[]),'message_id':message.get('Message-ID'),'recipients':recipients('to')}}
        if kind=='slack_post':
            params={'channel':payload['channel_id'],'limit':100}
            if receipt.get('ts'):params.update(oldest=receipt['ts'],latest=receipt['ts'],inclusive='true')
            data=self.get('slack','conversations.history',params)
            matches=[m for m in data.get('messages',[]) if (m.get('ts')==receipt.get('ts') if receipt.get('ts') else m.get('client_msg_id')==key) and m.get('text')==payload['text']]
            return {'verified':len(matches)==1,'provider_id':matches[0]['ts'] if len(matches)==1 else '',
                    'readback':{'channel':payload['channel_id'],'matches':len(matches),'truncated':bool(data.get('has_more'))}}
        return {'verified':False}
