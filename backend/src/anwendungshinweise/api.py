"""Lambda-Einstieg für die HTTP-API (API Gateway REST, Proxy-Integration).

Ein einzelner Handler mit kleinem Router deckt alle Abfrage- und
Debug-Endpunkte ab:

- ``POST /query``            – Frage grounded auf der Wissensbasis beantworten
- ``GET  /documents``        – im S3-Bucket abgelegte Quelldokumente auflisten
- ``GET  /ingestion-jobs``   – Status/Statistik der Indizierungs-Läufe
- ``GET  /retrieve``         – Debug: rohe Retrieval-Treffer inkl. Score
- ``GET  /health``           – Health-Check
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from . import knowledge_base as kb
from .config import ConfigError, load_config
from .responses import bad_request, not_found, ok, server_error

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# (METHOD, PATH) -> Handler
Route = tuple[str, str]
Handler = Callable[[dict], dict]


def _parse_body(event: dict) -> dict[str, Any]:
    body = event.get("body")
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return {}


def _query(event: dict) -> dict:
    payload = _parse_body(event)
    question = (payload.get("question") or payload.get("frage") or "").strip()
    if not question:
        return bad_request("Feld 'question' fehlt oder ist leer.")
    session_id: str | None = payload.get("sessionId")
    cfg = load_config()
    result = kb.retrieve_and_generate(cfg, question, session_id=session_id)
    return ok(result)


def _documents(_event: dict) -> dict:
    cfg = load_config()
    documents = kb.list_documents(cfg)
    return ok({"count": len(documents), "documents": documents})


def _ingestion_jobs(event: dict) -> dict:
    cfg = load_config()
    params = event.get("queryStringParameters") or {}
    max_results = int(params.get("max", "10"))
    jobs = kb.list_ingestion_jobs(cfg, max_results=max_results)
    return ok({"count": len(jobs), "jobs": jobs})


def _retrieve(event: dict) -> dict:
    params = event.get("queryStringParameters") or {}
    query = (params.get("q") or params.get("query") or "").strip()
    if not query:
        return bad_request("Query-Parameter 'q' fehlt.")
    cfg = load_config()
    n = params.get("n")
    results = kb.retrieve(cfg, query, number_of_results=int(n) if n else None)
    return ok({"count": len(results), "results": results})


def _health(_event: dict) -> dict:
    return ok({"status": "ok"})


ROUTES: dict[Route, Handler] = {
    ("POST", "/query"): _query,
    ("GET", "/documents"): _documents,
    ("GET", "/ingestion-jobs"): _ingestion_jobs,
    ("GET", "/retrieve"): _retrieve,
    ("GET", "/health"): _health,
}


def handler(event: dict, _context: Any = None) -> dict:
    method = (event.get("httpMethod") or "GET").upper()
    path = event.get("path") or "/"
    # API-Stage-Präfixe (z. B. "/prod") tolerieren.
    if path != "/" and path.count("/") > 1 and not any(
        path == p for _, p in ROUTES
    ):
        path = "/" + path.rstrip("/").split("/")[-1]

    logger.info("Request %s %s", method, path)

    if method == "OPTIONS":
        return ok({})  # CORS-Preflight (Header werden zentral gesetzt)

    route_handler = ROUTES.get((method, path))
    if route_handler is None:
        return not_found(f"Kein Endpunkt für {method} {path}")

    try:
        return route_handler(event)
    except ConfigError as exc:
        logger.exception("Konfigurationsfehler")
        return server_error(f"Konfigurationsfehler: {exc}")
    except Exception as exc:  # noqa: BLE001 – Demo: Fehler nach außen sichtbar
        logger.exception("Unerwarteter Fehler")
        return server_error(str(exc))
