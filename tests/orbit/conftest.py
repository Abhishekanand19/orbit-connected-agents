import os
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.orbit.api import create_app
from backend.orbit.config import Settings
from backend.orbit.database import Database

@pytest.fixture
def settings():
    return Settings.from_env().model_copy(update={'graph':'orbit_test_'+uuid.uuid4().hex})

@pytest.fixture
def client(settings):
    # Real DB required. Connectivity failures fail tests rather than silently skipping.
    db=Database(settings)
    db.initialize()
    try:
        with TestClient(create_app(settings)) as client:
            yield client
    finally:
        assert settings.graph.startswith('orbit_test_')
        db.graph.delete()
        db.close()
