from __future__ import annotations

import json
import asyncio
from pathlib import Path

import httpx

from app import logging_config
from app.main import app


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True

def test_correlation_id_and_enrichment_in_logs(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-42",
                    "session_id": "session-42",
                    "feature": "qa",
                    "message": "My email is test@domain.com and phone is 0912345678",
                },
            )

    response = asyncio.run(send_request())
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"].startswith("req-")
    assert "x-response-time-ms" in response.headers

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2
    events = [json.loads(line) for line in lines]
    req_event = next(e for e in events if e["event"] == "request_received")
    assert req_event["correlation_id"] == response.headers["x-request-id"]
    assert "user_id_hash" in req_event
    assert req_event["session_id"] == "session-42"
    assert req_event["feature"] == "qa"
    assert req_event["model"] != ""
    # Verify PII was scrubbed
    raw_log = json.dumps(req_event)
    assert "test@domain.com" not in raw_log
    assert "0912345678" not in raw_log
    assert "REDACTED_EMAIL" in raw_log
    assert "REDACTED_PHONE_VN" in raw_log


def test_custom_correlation_id_propagated(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                headers={"x-request-id": "req-custom99"},
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "summary",
                    "message": "Summarize log",
                },
            )

    response = asyncio.run(send_request())
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-custom99"
    assert response.json()["correlation_id"] == "req-custom99"

