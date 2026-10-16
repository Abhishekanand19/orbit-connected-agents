"""Native generation grammar and the exact synthetic live failure regression."""
import json
from pathlib import Path
import httpx
import pytest
from pydantic import ValidationError
from jsonschema import Draft202012Validator
from backend.orbit import llm
from backend.orbit.agents import ActionPlan,Finding,validated
from backend.orbit.action_models import action_output_schema
from backend.orbit.database import GraphError

def test_actual_live_empty_payload_is_rejected_by_native_and_runtime_schema():
    captured=json.loads((Path(__file__).parent/'fixtures/gemini_empty_action_payload.json').read_text())
    payload=captured['parsed']
    with pytest.raises(ValidationError) as error:ActionPlan.model_validate(payload)
    assert [(e['loc'],e['type']) for e in error.value.errors()]==[(('actions',0,'task_id'),'missing'),(('actions',0,'changes'),'missing')]
    schema=action_output_schema(ActionPlan,{'task_create','task_update'})
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(payload))
    for branch in schema['$defs']['ActionDraft']['anyOf']:
        assert branch['properties']['payload']['required']==['task_id','changes']
        assert branch['properties']['payload']['additionalProperties'] is False

@pytest.mark.parametrize('role_kinds',[set(),{'task_create','task_update'},{'calendar_create','calendar_update'},{'gmail_send','slack_post'}])
def test_specialist_schema_has_real_nested_contracts(role_kinds):
    schema=action_output_schema(Finding,role_kinds)
    Draft202012Validator.check_schema(schema)
    assert schema['$defs']['ActionDraft']['anyOf']

def test_native_transport_extracts_non_thought_text_and_preserves_contract(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-placeholder')
    schema=action_output_schema(ActionPlan,{'task_create'})
    def post(url,**kwargs):
        config=kwargs['json']['generationConfig']
        assert config['responseMimeType']=='application/json'
        contract=config['responseJsonSchema']['$defs']['ActionDraft']['anyOf'][0]['properties']['payload']
        assert contract['required']==['task_id','changes'] and contract['additionalProperties'] is False
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'thought':True,'text':'not output'},{'text':'{"actions":[],'},{'text':'"missing_details":["Exact time required"]}'}]}}]})
    monkeypatch.setattr(llm.httpx,'post',post)
    assert llm.generate('test',{},schema)=={'actions':[],'missing_details':['Exact time required']}

def test_validation_diagnostics_do_not_log_input(caplog):
    with pytest.raises(GraphError):validated(ActionPlan,{'actions':'sensitive-placeholder','missing_details':[]})
    assert 'list_type' in caplog.text and 'sensitive-placeholder' not in caplog.text
