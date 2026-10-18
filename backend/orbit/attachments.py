"""Bounded local attachments; file contents never become executable chat instructions."""
import base64, binascii, hashlib, json, tempfile
from pathlib import Path
from uuid import uuid4
from fastapi import Request
from .database import GraphError
from .models import EntityType
from .story_api import request_service

MAX_FILE=5*1024*1024
TEXT={'.txt','.md','.csv','.json'}

def decode_attachment(body):
    name=body.get('name','')
    if not isinstance(name,str) or not name or len(name)>240 or '/' in name or '\\' in name:
        raise GraphError(400,'attachment_name','Invalid attachment filename.')
    extension=Path(name).suffix.lower()
    if extension not in TEXT|{'.pdf','.png','.jpg','.jpeg'}:raise GraphError(415,'attachment_type','Unsupported attachment type.')
    try:data=base64.b64decode(body.get('data',''),validate=True)
    except (ValueError,TypeError,binascii.Error):raise GraphError(400,'attachment_data','Invalid file encoding.')
    if not data or len(data)>MAX_FILE:raise GraphError(413,'attachment_size','Files must contain data and be 5 MB or smaller.')
    signatures={'.pdf':b'%PDF-', '.png':b'\x89PNG\r\n\x1a\n','.jpg':b'\xff\xd8\xff','.jpeg':b'\xff\xd8\xff'}
    if extension in signatures and not data.startswith(signatures[extension]):raise GraphError(415,'attachment_type','The file contents do not match its extension.')
    text=''
    if extension in TEXT:
        try:text=data.decode('utf-8-sig')
        except UnicodeDecodeError:raise GraphError(415,'attachment_encoding','Text attachments must use UTF-8 encoding.')
        if '\x00' in text:raise GraphError(415,'attachment_encoding','Binary content is not supported as text.')
    return name,data,text[:20000],len(text)>20000

def mount_attachments(app):
    @app.post('/api/attachments')
    async def upload(request:Request):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>7*1024*1024:raise GraphError(413,'attachment_size','Upload is too large.')
        try:body=json.loads(raw)
        except (ValueError,UnicodeDecodeError):raise GraphError(400,'attachment_data','Invalid upload request.')
        if not isinstance(body,dict):raise GraphError(400,'attachment_data','Invalid upload request.')
        name,data,text,truncated=decode_attachment(body)
        service=request_service(request);id='attachment:'+uuid4().hex
        directory=Path(tempfile.gettempdir())/'orbit-attachments'/hashlib.sha256(service.repo.db.settings.graph.encode()).hexdigest()
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/id.split(':')[1]
        try:
            path.write_bytes(data)
            node=service.repo.upsert_node(id,EntityType.Source,{'name':name,'record_kind':'ATTACHMENT','size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'text_preview':text,'preview_truncated':truncated,'processing':'text preview' if text else 'Stored only; no OCR or analysis'})
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return {'id':node['id'],'name':name,'size':len(data),'text':text,'truncated':truncated,'processing':node['properties']['processing']}
