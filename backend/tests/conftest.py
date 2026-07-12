"""Gemeinsame Test-Fixtures. Setzt eine vollständige Fake-Umgebung."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-123")
    monkeypatch.setenv("DATA_SOURCE_ID", "ds-456")
    monkeypatch.setenv("DOCUMENTS_BUCKET", "docs-bucket")
    monkeypatch.setenv("DOCUMENTS_PREFIX", "documents/")
    monkeypatch.setenv(
        "GENERATION_MODEL_ARN",
        "arn:aws:bedrock:eu-central-1:111122223333:inference-profile/"
        "eu.anthropic.claude-3-5-sonnet-20240620-v1:0",
    )
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("MAX_RESULTS", "8")


@pytest.fixture
def fake_clients(monkeypatch):
    """Ersetzt ``aws.get_client`` durch einen Registry-basierten Fake."""
    from anwendungshinweise import aws

    registry = {}

    def _get_client(service):
        return registry[service]

    monkeypatch.setattr(aws, "get_client", _get_client)
    # knowledge_base importiert get_client per ``from .aws import get_client``,
    # daher dort ebenfalls patchen.
    from anwendungshinweise import knowledge_base

    monkeypatch.setattr(knowledge_base, "get_client", _get_client)
    return registry
