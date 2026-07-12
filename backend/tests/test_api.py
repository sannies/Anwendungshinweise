"""Tests für den API-Router."""

from __future__ import annotations

import json

from anwendungshinweise import api


def _event(method, path, body=None, query=None):
    return {
        "httpMethod": method,
        "path": path,
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def test_health():
    resp = api.handler(_event("GET", "/health"))
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == {"status": "ok"}


def test_cors_headers_present():
    resp = api.handler(_event("GET", "/health"))
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"


def test_options_preflight():
    resp = api.handler(_event("OPTIONS", "/query"))
    assert resp["statusCode"] == 200


def test_unknown_route_404():
    resp = api.handler(_event("GET", "/gibtsnicht"))
    assert resp["statusCode"] == 404


def test_query_requires_question():
    resp = api.handler(_event("POST", "/query", body={}))
    assert resp["statusCode"] == 400


def test_query_success(monkeypatch):
    def fake_rag(cfg, question, session_id=None):
        assert question == "Muss ich grundieren?"
        return {"answer": "Ja.", "citations": [], "sources": [], "sessionId": "s1"}

    monkeypatch.setattr(api.kb, "retrieve_and_generate", fake_rag)
    resp = api.handler(_event("POST", "/query", body={"question": "Muss ich grundieren?"}))

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["answer"] == "Ja."


def test_stage_prefixed_path_is_normalised(monkeypatch):
    monkeypatch.setattr(api.kb, "list_documents", lambda cfg: [])
    resp = api.handler(_event("GET", "/prod/documents"))
    assert resp["statusCode"] == 200


def test_retrieve_requires_query():
    resp = api.handler(_event("GET", "/retrieve", query=None))
    assert resp["statusCode"] == 400
