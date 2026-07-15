"""API-тесты: очередь замокана, RabbitMQ/Postgres не нужны."""

from fastapi.testclient import TestClient

from app import main
from tests.test_validation import VALID

client = TestClient(main.app)


def test_valid_application_queued(monkeypatch):
    published = []
    monkeypatch.setattr(main.publisher, "publish", published.append)

    response = client.post("/applications", json=VALID)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert len(published) == 1
    assert published[0]["application_id"] == body["application_id"]
    assert published[0]["application"]["client_id"] == VALID["client_id"]


def test_invalid_application_returns_422(monkeypatch):
    published = []
    monkeypatch.setattr(main.publisher, "publish", published.append)

    response = client.post("/applications", json={**VALID, "phone": "983590502"})

    assert response.status_code == 422
    assert published == []
    assert any(err["loc"][-1] == "phone" for err in response.json()["detail"])


def test_queue_unavailable_returns_503(monkeypatch):
    def boom(_):
        raise ConnectionError("rabbitmq down")

    monkeypatch.setattr(main.publisher, "publish", boom)
    response = client.post("/applications", json=VALID)
    assert response.status_code == 503


def test_health():
    assert client.get("/health").json() == {"status": "ok"}
