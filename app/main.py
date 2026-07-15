"""REST API приёма кредитных заявок.

POST /applications  — валидация и постановка в очередь (202 Accepted).
GET  /applications/{id} — результат обработки (после воркера).
GET  /health — liveness.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.db import ApplicationResult, SessionLocal
from app.logging_config import setup_logging
from app.queue import publisher
from app.schemas import CreditApplication

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Credit Applications Pipeline", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/applications", status_code=202)
def submit_application(application: CreditApplication) -> dict:
    """FastAPI уже провалидировал заявку через CreditApplication (иначе 422)."""
    application_id = str(uuid.uuid4())
    message = {
        "application_id": application_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "application": application.model_dump(mode="json"),
    }
    try:
        publisher.publish(message)
    except Exception:
        logger.exception("Failed to publish application %s", application_id)
        raise HTTPException(status_code=503, detail="Queue is unavailable, try again later")

    logger.info("Application %s (client_id=%s) queued", application_id, application.client_id)
    return {"application_id": application_id, "status": "queued"}


@app.get("/applications/{application_id}")
def get_application(application_id: str) -> dict:
    with SessionLocal() as session:
        result = session.get(ApplicationResult, application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Not found (possibly still processing)")
    return {
        "application_id": result.application_id,
        "client_id": result.client_id,
        "decision": result.decision,
        "score": result.score,
        "pti": result.pti,
        "reasons": result.reasons,
        "processed_at": result.processed_at.isoformat(),
    }
