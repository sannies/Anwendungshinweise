"""Tests für die Fachlogik der Knowledge Base."""

from __future__ import annotations

import datetime as dt

from anwendungshinweise import knowledge_base as kb
from anwendungshinweise.config import load_config


class FakeAgentRuntime:
    def __init__(self):
        self.last_request = None

    def retrieve_and_generate(self, **kwargs):
        self.last_request = kwargs
        return {
            "sessionId": "sess-1",
            "output": {"text": "Ja, die Fassade ist zu grundieren."},
            "citations": [
                {
                    "retrievedReferences": [
                        {
                            "content": {"text": "Kalksandstein grundieren ..."},
                            "location": {
                                "type": "S3",
                                "s3Location": {
                                    "uri": "s3://docs-bucket/documents/bfs-merkblatt-10.pdf"
                                },
                            },
                            "metadata": {"page": 3},
                        }
                    ]
                }
            ],
        }

    def retrieve(self, **kwargs):
        self.last_request = kwargs
        return {
            "retrievalResults": [
                {
                    "content": {"text": "Loser Putz ist zu entfernen."},
                    "location": {"s3Location": {"uri": "s3://docs-bucket/documents/wdvs.pdf"}},
                    "score": 0.83,
                    "metadata": {},
                }
            ]
        }


def test_retrieve_and_generate_shapes_output(fake_clients):
    fake_clients["bedrock-agent-runtime"] = FakeAgentRuntime()
    cfg = load_config()

    result = kb.retrieve_and_generate(cfg, "Muss ich grundieren?")

    assert result["answer"].startswith("Ja")
    assert result["sessionId"] == "sess-1"
    assert result["citations"][0]["document"] == "bfs-merkblatt-10.pdf"
    assert result["sources"] == [
        {
            "uri": "s3://docs-bucket/documents/bfs-merkblatt-10.pdf",
            "document": "bfs-merkblatt-10.pdf",
        }
    ]


def test_retrieve_and_generate_passes_grounding_prompt(fake_clients):
    runtime = FakeAgentRuntime()
    fake_clients["bedrock-agent-runtime"] = runtime
    cfg = load_config()

    kb.retrieve_and_generate(cfg, "Frage?", session_id="abc")

    req = runtime.last_request
    gen_cfg = req["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"][
        "generationConfiguration"
    ]
    template = gen_cfg["promptTemplate"]["textPromptTemplate"]
    assert "$search_results$" in template
    assert "KEIN allgemeines Weltwissen" in template
    assert req["sessionId"] == "abc"


def test_retrieve_returns_scores(fake_clients):
    fake_clients["bedrock-agent-runtime"] = FakeAgentRuntime()
    cfg = load_config()

    results = kb.retrieve(cfg, "loser Putz")

    assert results[0]["score"] == 0.83
    assert results[0]["document"] == "wdvs.pdf"


class FakeAgent:
    def list_ingestion_jobs(self, **kwargs):
        return {
            "ingestionJobSummaries": [
                {
                    "ingestionJobId": "job-1",
                    "status": "COMPLETE",
                    "startedAt": dt.datetime(2026, 7, 1),
                    "updatedAt": dt.datetime(2026, 7, 1),
                    "statistics": {"numberOfNewDocumentsIndexed": 2},
                }
            ]
        }

    def start_ingestion_job(self, **kwargs):
        return {"ingestionJob": {"ingestionJobId": "job-2", "status": "STARTING"}}


def test_list_ingestion_jobs(fake_clients):
    fake_clients["bedrock-agent"] = FakeAgent()
    cfg = load_config()

    jobs = kb.list_ingestion_jobs(cfg)

    assert jobs[0]["ingestionJobId"] == "job-1"
    assert jobs[0]["statistics"]["numberOfNewDocumentsIndexed"] == 2


def test_start_ingestion_job(fake_clients):
    fake_clients["bedrock-agent"] = FakeAgent()
    cfg = load_config()

    result = kb.start_ingestion_job(cfg, description="test")

    assert result == {"ingestionJobId": "job-2", "status": "STARTING"}


class FakeS3:
    def get_paginator(self, _name):
        return self

    def paginate(self, **kwargs):
        yield {
            "Contents": [
                {"Key": "documents/", "Size": 0},
                {
                    "Key": "documents/bfs-10.pdf",
                    "Size": 12345,
                    "LastModified": dt.datetime(2026, 7, 1),
                },
            ]
        }


def test_list_documents_skips_folder_placeholder(fake_clients):
    fake_clients["s3"] = FakeS3()
    cfg = load_config()

    docs = kb.list_documents(cfg)

    assert len(docs) == 1
    assert docs[0]["document"] == "bfs-10.pdf"
    assert docs[0]["uri"] == "s3://docs-bucket/documents/bfs-10.pdf"
