"""Call-completion webhook service.

Run:  uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
"""
import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .crm import CrmClient, flush_outbox
from .logging_config import configure_logging
from .scheduling import schedule_retry
from .storage import Store

log = logging.getLogger("webhook")

RETRYABLE = frozenset({"NO_ANSWER", "BUSY"})
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


@dataclass(frozen=True)
class Settings:
    crm_url: str
    crm_api_token: str
    db_path: str = "calls.db"
    outbox_interval_s: float = 15.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [k for k in ("CRM_URL", "CRM_API_TOKEN") if not os.getenv(k)]
        if missing:
            raise RuntimeError(f"missing required env vars: {missing}")      # fail at boot, not on first request
        return cls(
            crm_url=os.environ["CRM_URL"],
            crm_api_token=os.environ["CRM_API_TOKEN"],
            db_path=os.getenv("DB_PATH", "calls.db"),
            outbox_interval_s=float(os.getenv("OUTBOX_INTERVAL_S", "15")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


class CallCompleted(BaseModel):
    call_id: str = Field(pattern=ID_PATTERN, description="Voice platform's unique call id; idempotency key")
    account_id: str = Field(pattern=ID_PATTERN)
    disposition: str = Field(pattern=r"^[A-Z_]{1,32}$")
    attempt: int = Field(default=0, ge=0, le=50)


def create_app(settings: Settings | None = None, crm_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    store = Store(settings.db_path)
    crm = CrmClient(settings.crm_url, settings.crm_api_token, transport=crm_transport)

    async def sweep_forever():
        while True:
            await asyncio.sleep(settings.outbox_interval_s)
            try:
                await flush_outbox(store, crm)
            except Exception:
                log.exception("outbox sweep failed")

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(sweep_forever())
        yield
        task.cancel()
        await crm.aclose()

    app = FastAPI(title="call-webhook", lifespan=lifespan)
    app.state.store, app.state.crm = store, crm

    @app.get("/health")
    def health():
        try:
            store.ping()
        except Exception:
            log.exception("health check failed")
            return JSONResponse({"status": "unhealthy"}, status_code=503)
        return {"status": "ok"}

    @app.post("/webhook/call-completed", status_code=202)
    def call_completed(body: CallCompleted, background: BackgroundTasks):
        # Sync handler: FastAPI runs it in a threadpool, so blocking sqlite never stalls the event loop.
        nxt = None
        if body.disposition in RETRYABLE:
            nxt = schedule_retry(body.attempt, datetime.now(timezone.utc))
        created = store.record_call(body.call_id, body.account_id, body.disposition, body.attempt, nxt)
        log.info("call recorded", extra={"call_id": body.call_id, "account_id": body.account_id,
                                         "disposition": body.disposition, "attempt": body.attempt,
                                         "next_call_at": nxt.isoformat() if nxt else None, "duplicate": not created})
        if created and nxt is not None:
            background.add_task(flush_outbox, store, crm)     # fast path; the sweeper is the safety net
        return {"status": "accepted" if created else "duplicate",
                "next_call_at": nxt.isoformat() if nxt else None}

    return app
