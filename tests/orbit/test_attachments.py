import base64
import pytest
from backend.orbit.attachments import decode_attachment
from backend.orbit.database import GraphError

def payload(name,data):return {'name':name,'data':base64.b64encode(data).decode()}

@pytest.mark.parametrize('name,data,code',[
 ('../bad.txt',b'hello',400),('program.exe',b'x',415),('fake.png',b'not png',415),('binary.txt',b'\xff',415),('large.txt',b'x'*(5*1024*1024+1),413),('empty.txt',b'',413)],ids=['path','type','signature','encoding','size','empty'])
def test_attachment_rejection(name,data,code):
    with pytest.raises(GraphError) as error:decode_attachment(payload(name,data))
    assert error.value.status==code

def test_text_preview_is_bounded():
    name,data,text,truncated=decode_attachment(payload('note.txt',b'a'*21000))
    assert len(data)==21000 and len(text)==20000 and truncated

def test_real_upload_persists_evidence_and_invalid_upload_creates_nothing(client):
    response=client.post('/api/attachments',json=payload('notes.txt',b'A harmless note.'))
    assert response.status_code==200,response.text
    record=client.app.state.service.repo.get_node(response.json()['id'])
    assert record['type']=='Source' and record['properties']['text_preview']=='A harmless note.'
    assert record['properties']['record_kind']=='ATTACHMENT'
    assert client.post('/api/attachments',json=payload('fake.pdf',b'not pdf')).status_code==415
    assert client.post('/api/attachments',json=[]).status_code==400
