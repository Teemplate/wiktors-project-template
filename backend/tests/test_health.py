"""The suite CI runs on every push. Keep it fast and dependency-free.

These need no database and no secret: a fresh clone with no .env at all must be
able to run the tests. If a test starts needing a credential, that is a design
problem, not a reason to add one to CI.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_hello_names_the_app():
    response = client.get("/api/hello")
    assert response.status_code == 200
    assert "hello from" in response.json()["message"]
