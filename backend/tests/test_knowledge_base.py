"""Tests für die Fachlogik der Knowledge Base."""

from __future__ import annotations

import datetime as dt

from anwendungshinweise import knowledge_base as kb
from anwendungshinweise.config import load_config

PAGE_KEY = kb.PAGE_METADATA_KEY


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
                            "metadata": {PAGE_KEY: 3},
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
                    "metadata": {PAGE_KEY: "7.0"},
                }
            ]
        }


class FakeS3:
    """Deckt list_objects_v2 (Paginator) und generate_presigned_url ab."""

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

    def generate_presigned_url(self, _op, Params=None, ExpiresIn=None):  # noqa: N803
        key = Params["Key"]
        return f"https://s3.example/{Params['Bucket']}/{key}?sig=abc"


def test_retrieve_and_generate_shapes_output(fake_clients):
    fake_clients["bedrock-agent-runtime"] = FakeAgentRuntime()
    fake_clients["s3"] = FakeS3()
    cfg = load_config()

    result = kb.retrieve_and_generate(cfg, "Muss ich grundieren?")

    assert result["answer"].startswith("Ja")
    assert result["sessionId"] == "sess-1"
    cite = result["citations"][0]
    assert cite["document"] == "bfs-merkblatt-10.pdf"
    assert cite["page"] == 3
    assert cite["link"].endswith("#page=3")
    # Basis-URL (für den eingebetteten PDF.js-Viewer) ohne Seiten-Fragment.
    assert cite["pdfUrl"] and "#page=" not in cite["pdfUrl"]
    # Treffer vorhanden -> keine Warnung.
    assert result["grounded"] is True
    assert result["warning"] is None


class FakeAgentRuntimeNoMatch:
    """Simuliert 'kein Treffer': Vektorsuche liefert keine Ergebnisse."""

    def retrieve(self, **kwargs):
        return {"retrievalResults": []}

    def retrieve_and_generate(self, **kwargs):
        raise AssertionError("Ohne Treffer darf nicht generiert werden")


def test_no_match_sets_warning(fake_clients):
    fake_clients["bedrock-agent-runtime"] = FakeAgentRuntimeNoMatch()
    fake_clients["s3"] = FakeS3()
    cfg = load_config()

    result = kb.retrieve_and_generate(cfg, "Völlig fachfremde Frage?")

    assert result["grounded"] is False
    assert result["warning"] and "kein" in result["warning"].lower()
    assert result["sources"] == []
    assert result["topScore"] is None


class FakeAgentRuntimeLowScore:
    """Treffer vorhanden, aber Score unter der Schwelle -> Warnung, kein Gen."""

    def retrieve(self, **kwargs):
        return {
            "retrievalResults": [
                {
                    "content": {"text": "kaum relevant"},
                    "location": {"s3Location": {"uri": "s3://docs-bucket/documents/x.pdf"}},
                    "score": 0.2,
                    "metadata": {},
                }
            ]
        }

    def retrieve_and_generate(self, **kwargs):
        raise AssertionError("Bei zu niedrigem Score darf nicht generiert werden")


def test_low_score_warns_without_generating(fake_clients):
    fake_clients["bedrock-agent-runtime"] = FakeAgentRuntimeLowScore()
    fake_clients["s3"] = FakeS3()
    cfg = load_config()

    result = kb.retrieve_and_generate(cfg, "schwach relevante Frage")

    assert result["grounded"] is False
    assert "schwach" in result["warning"].lower()
    assert result["topScore"] == 0.2


def test_sources_aggregate_pages_and_link(fake_clients):
    fake_clients["bedrock-agent-runtime"] = FakeAgentRuntime()
    fake_clients["s3"] = FakeS3()
    cfg = load_config()

    result = kb.retrieve_and_generate(cfg, "Muss ich grundieren?")

    source = result["sources"][0]
    assert source["document"] == "bfs-merkblatt-10.pdf"
    assert source["pages"] == [3]
    assert source["link"].endswith("#page=3")
    assert source["link"].startswith("https://s3.example/")


def test_retrieve_and_generate_passes_grounding_prompt(fake_clients):
    runtime = FakeAgentRuntime()
    fake_clients["bedrock-agent-runtime"] = runtime
    fake_clients["s3"] = FakeS3()
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


def test_retrieve_returns_scores_page_and_link(fake_clients):
    fake_clients["bedrock-agent-runtime"] = FakeAgentRuntime()
    fake_clients["s3"] = FakeS3()
    cfg = load_config()

    results = kb.retrieve(cfg, "loser Putz")

    assert results[0]["score"] == 0.83
    assert results[0]["document"] == "wdvs.pdf"
    assert results[0]["page"] == 7  # "7.0" -> 7
    assert results[0]["link"].endswith("#page=7")


def test_extract_page_handles_missing_and_alternate_keys():
    assert kb._extract_page(None) is None
    assert kb._extract_page({}) is None
    assert kb._extract_page({"foo-page-number": 5}) == 5
    assert kb._extract_page({PAGE_KEY: "not-a-number"}) is None


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


def test_list_documents_skips_folder_placeholder(fake_clients):
    fake_clients["s3"] = FakeS3()
    cfg = load_config()

    docs = kb.list_documents(cfg)

    assert len(docs) == 1
    assert docs[0]["document"] == "bfs-10.pdf"
    assert docs[0]["uri"] == "s3://docs-bucket/documents/bfs-10.pdf"
