"""Public deployment boundary tested against disposable real FalkorDB graphs."""
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from backend.orbit.api import create_app
from backend.orbit.config import Settings
from backend.orbit.database import Database, GraphError
from backend.orbit.actions import Actions
from backend.orbit.action_providers import ActionProviders
from backend.orbit import llm


def test_public_demo_isolation_and_policy(monkeypatch):
    monkeypatch.setattr(llm, 'generate', lambda *a, **k: pytest.fail('Public demo called a model'))
    monkeypatch.setattr(ActionProviders, 'perform', lambda *a, **k: pytest.fail('External write attempted'))
    settings = Settings.from_env().model_copy(update={'public_demo': True, 'graph': 'orbit_public_test_' + uuid4().hex})
    graphs = [settings.graph]
    try:
        with TestClient(create_app(settings)) as client:
            for path in ['/api/nodes', '/api/story/state', '/api/actions/session']:
                response = client.post(path) if path.endswith('session') else client.get(path)
                assert response.status_code == 401
            assert client.post('/api/integrations/google/connect').status_code == 403
            assert client.post('/api/attachments').status_code == 403
            assert client.get('/api/onboarding/connections').json()['connections'][0]['status'] == 'unavailable'
            first = client.post('/api/story/workspaces').json()
            graphs.append(first['graph'])
            second = client.post('/api/story/workspaces').json()
            graphs.append(second['graph'])
            headers = {'X-Orbit-Story': first['workspace_id']}
            payload = {'id': 'public:turn:one', 'bot_id': 'coordinator', 'name': 'Coordinator', 'conversation_id': 'public:conversation:one', 'content': 'I am Aarav. My father is Ramesh and my sister is Priya.'}
            assert client.post('/api/chat', json=payload, headers=headers).status_code == 200
            assert client.get('/api/nodes/story:ramesh', headers=headers).status_code == 200
            assert client.get('/api/nodes/story:ramesh', headers={'X-Orbit-Story': second['workspace_id']}).status_code == 404
            assert client.get('/api/story/state', headers={'X-Orbit-Story': '0' * 32}).status_code == 404
            assert client.post('/api/chat', content='x' * 65537, headers=headers).status_code == 413
            denied = client.get('/api/nodes', headers={'Origin': settings.allowed_origins[0]})
            assert denied.headers['access-control-allow-origin'] == settings.allowed_origins[0]
            actions = Actions(client.app.state.service)
            for kind in ['gmail_send', 'calendar_create', 'slack_post']:
                with pytest.raises(GraphError) as error:
                    actions.policy(kind)
                assert error.value.status == 403
            actions.policy('task_update')
    finally:
        for graph in graphs:
            db = Database(settings.model_copy(update={'graph': graph}))
            db.initialize()
            db.graph.delete()
            db.close()


def test_public_demo_rejects_owner_registry():
    with pytest.raises(ValueError):
        create_app(Settings(public_demo=True, graph='orbit'))
