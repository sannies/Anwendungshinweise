"""Tests für den S3-Ingestion-Trigger."""

from __future__ import annotations

from botocore.exceptions import ClientError

from anwendungshinweise import ingest


def _s3_event(*keys):
    return {"Records": [{"s3": {"object": {"key": k}}} for k in keys]}


def test_ingest_starts_job(monkeypatch):
    called = {}

    def fake_start(cfg, description=""):
        called["description"] = description
        return {"ingestionJobId": "job-9", "status": "STARTING"}

    monkeypatch.setattr(ingest.kb, "start_ingestion_job", fake_start)
    result = ingest.handler(_s3_event("documents/neu.pdf"))

    assert result["started"] is True
    assert result["ingestionJobId"] == "job-9"
    assert "documents/neu.pdf" in called["description"]


def test_ingest_tolerates_conflict(monkeypatch):
    def fake_start(cfg, description=""):
        raise ClientError(
            {"Error": {"Code": "ConflictException", "Message": "running"}},
            "StartIngestionJob",
        )

    monkeypatch.setattr(ingest.kb, "start_ingestion_job", fake_start)
    result = ingest.handler(_s3_event("documents/neu.pdf"))

    assert result == {"started": False, "reason": "already-running"}


def test_ingest_reraises_other_errors(monkeypatch):
    def fake_start(cfg, description=""):
        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "nope"}},
            "StartIngestionJob",
        )

    monkeypatch.setattr(ingest.kb, "start_ingestion_job", fake_start)
    try:
        ingest.handler(_s3_event("documents/neu.pdf"))
    except ClientError:
        return
    raise AssertionError("ClientError sollte weitergereicht werden")
