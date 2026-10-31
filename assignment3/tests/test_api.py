import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.crm import CrmClient, flush_outbox  # noqa: E402
from app.main import Settings, create_app  # noqa: E402


class FakeCrm:
    def __init__(self):
        self.requests: list[dict] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503)
        self.requests.append({"auth": request.headers.get("authorization"), **json.loads(request.content)})
        return httpx.Response(200, json={"ok": True})


@pytest.fixture
def crm():
    return FakeCrm()


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "calls.db")


@pytest.fixture
def client(crm, db_path):
    settings = Settings(crm_url="https://crm.test/schedule", crm_api_token="t0ken", db_path=db_path,
                        outbox_interval_s=3600)
    app = create_app(settings, crm_transport=httpx.MockTransport(crm.handler))
    with TestClient(app) as c:
        yield c


def rows(db_path, sql):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql).fetchall()


def post(client, **overrides):
    body = {"call_id": "C1", "account_id": "A1", "disposition": "NO_ANSWER", "attempt": 0, **overrides}
    return client.post("/webhook/call-completed", json=body)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_no_answer_records_and_notifies_crm(client, crm, db_path):
    r = post(client)
    assert r.status_code == 202
    assert r.json()["status"] == "accepted" and r.json()["next_call_at"] is not None
    assert rows(db_path, "SELECT call_id, account_id, disposition, attempt FROM calls") == [("C1", "A1", "NO_ANSWER", 0)]
    assert len(crm.requests) == 1
    assert crm.requests[0]["account_id"] == "A1"
    assert crm.requests[0]["auth"] == "Bearer t0ken"
    assert rows(db_path, "SELECT status FROM crm_outbox") == [("SENT",)]


@pytest.mark.parametrize("disposition", ["PTP", "CONNECTED", "DISPUTE", "WRONG_NUMBER"])
def test_non_retryable_dispositions_do_not_schedule(client, crm, db_path, disposition):
    """The original `== "NO_ANSWER" or "BUSY"` was always true."""
    r = post(client, disposition=disposition)
    assert r.status_code == 202 and r.json()["next_call_at"] is None
    assert crm.requests == []
    assert rows(db_path, "SELECT COUNT(*) FROM crm_outbox") == [(0,)]


def test_busy_is_retryable(client, crm):
    assert post(client, disposition="BUSY").json()["next_call_at"] is not None
    assert len(crm.requests) == 1


def test_exhausted_attempts_not_scheduled(client, crm):
    r = post(client, attempt=3)
    assert r.status_code == 202 and r.json()["next_call_at"] is None
    assert crm.requests == []


def test_duplicate_webhook_is_idempotent(client, crm, db_path):
    assert post(client).json()["status"] == "accepted"
    assert post(client).json()["status"] == "duplicate"
    assert rows(db_path, "SELECT COUNT(*) FROM calls") == [(1,)]
    assert len(crm.requests) == 1


@pytest.mark.parametrize("bad", [
    {"account_id": "A1'); DROP TABLE calls;--"},     # injection attempt rejected by validation
    {"account_id": ""},
    {"attempt": -1},
    {"attempt": "two"},
    {"disposition": None},
    {"call_id": None},
])
def test_invalid_payload_rejected(client, db_path, bad):
    assert post(client, **bad).status_code == 422
    assert rows(db_path, "SELECT COUNT(*) FROM calls") == [(0,)]


def test_crm_outage_keeps_notification_pending_then_delivers(client, crm, db_path):
    crm.down = True
    assert post(client).status_code == 202          # webhook still succeeds: the voice platform must not retry
    assert rows(db_path, "SELECT status, tries FROM crm_outbox") == [("PENDING", 1)]

    crm.down = False
    assert asyncio.run(_flush_with_fresh_client(client.app, crm)) == 1
    assert rows(db_path, "SELECT status FROM crm_outbox") == [("SENT",)]
    assert len(crm.requests) == 1


async def _flush_with_fresh_client(app, crm):
    # TestClient's event loop owns app.state.crm; use a fresh client on this loop.
    c = CrmClient("https://crm.test/schedule", "t0ken", transport=httpx.MockTransport(crm.handler))
    try:
        return await flush_outbox(app.state.store, c)
    finally:
        await c.aclose()


def test_missing_env_fails_fast(monkeypatch):
    monkeypatch.delenv("CRM_URL", raising=False)
    monkeypatch.delenv("CRM_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="CRM_URL"):
        Settings.from_env()
