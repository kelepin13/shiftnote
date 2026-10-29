from fastapi.testclient import TestClient

from shiftnote.api import app, get_provider
from shiftnote.providers import MockProvider

from .conftest import NOTE, ScriptedProvider


def client(provider=None):
    app.dependency_overrides[get_provider] = lambda: provider or MockProvider()
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_structures_a_note_with_the_offline_mock():
    res = client().post("/v1/notes/structure", json={"text": NOTE})
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "mock"
    assert {v["type"] for v in body["note"]["vitals"]} >= {"blood_pressure", "heart_rate"}


def test_rejects_an_empty_note():
    assert client().post("/v1/notes/structure", json={"text": "hi"}).status_code == 422


def test_still_answers_when_the_llm_is_down(down):
    res = client(ScriptedProvider(down)).post("/v1/notes/structure", json={"text": NOTE})
    assert res.status_code == 200
    assert res.json()["status"] == "partial"


def test_health_and_demo_page():
    c = client()
    assert c.get("/health").json() == {"status": "ok", "provider": "mock", "model": "rules-v1"}
    page = c.get("/")
    assert page.status_code == 200 and "Shiftnote" in page.text
