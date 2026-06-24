"""
API smoke tests -- verify the service boots and the lightweight endpoints work
without needing the LLM or database (we don't run a full investigation here).
"""

from fastapi.testclient import TestClient
from app.api.routes import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_scenarios_lists_demo_cases():
    r = client.get("/scenarios")
    assert r.status_code == 200
    assert len(r.json()) >= 4


def test_unknown_case_returns_404():
    r = client.get("/case/DOES-NOT-EXIST")
    assert r.status_code == 404


def test_rerun_unknown_agent_returns_404():
    r = client.post("/case/ANY/rerun-agent/not_a_real_agent")
    assert r.status_code == 404
