"""Fachlogik rund um die Bedrock Knowledge Base.

Kapselt die Bedrock-Aufrufe (Retrieve, RetrieveAndGenerate, Ingestion-Jobs)
sowie die S3-Auflistung der Quelldokumente. Bewusst frei von HTTP-Details,
damit die Funktionen einzeln testbar sind.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .aws import get_client
from .config import Config

# Reserviertes Bedrock-Metadatum mit der Seitenzahl einer PDF-Fundstelle.
PAGE_METADATA_KEY = "x-amz-bedrock-kb-document-page-number"

# Prompt-Vorlage für die Generierung. WICHTIG: Die Antwort wird ausschließlich
# aus den Suchergebnissen ($search_results$) abgeleitet – kein Weltwissen.
# Bedrock ersetzt $search_results$ durch die abgerufenen Passagen und stellt die
# eigentliche Nutzerfrage separat als User-Turn bereit.
GENERATION_PROMPT_TEMPLATE = """\
Du bist ein Fachassistent für die Anwendungshinweise (Merkblätter und \
technische Richtlinien) des deutschen Maler- und Lackiererhandwerks.

Der Nutzer stellt eine praxisbezogene Frage. Beantworte sie AUSSCHLIESSLICH auf \
Grundlage der unten stehenden Suchergebnisse aus den Anwendungshinweisen. \
Verwende KEIN allgemeines Weltwissen und rate nicht.

Regeln:
- Enthalten die Suchergebnisse keine ausreichende Grundlage, antworte exakt: \
"Dazu finde ich in den vorliegenden Anwendungshinweisen keine ausreichende Angabe."
- Antworte auf Deutsch, fachlich präzise und in ganzen Sätzen.
- Nenne die relevanten Arbeitsschritte, Bedingungen und Voraussetzungen konkret.
- Belege zentrale Aussagen mit einem KURZEN wörtlichen Zitat aus den \
Suchergebnissen in doppelten Anführungszeichen.
- Erfinde keine Normen, Kennzahlen, Fristen oder Produktnamen, die nicht in den \
Suchergebnissen stehen.

Suchergebnisse (nummeriert):
$search_results$

$output_format_instructions$"""

# Formulierung, mit der das Modell bei fehlender Grundlage antwortet (siehe
# Prompt). Wird zusätzlich zur Quellen-Prüfung zur Warnungs-Erkennung genutzt.
NO_MATCH_PHRASE = "keine ausreichende angabe"
NO_MATCH_WARNING = (
    "Zu dieser Frage wurde in den hinterlegten Anwendungshinweisen kein "
    "ausreichender Treffer gefunden – die Antwort ist nicht durch Quellen belegt."
)


def _s3_uri_to_name(uri: str | None) -> str | None:
    if not uri:
        return None
    # s3://bucket/documents/foo.pdf -> foo.pdf
    return uri.rstrip("/").split("/")[-1]


def _parse_s3_uri(uri: str | None) -> tuple[str, str] | None:
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        return None
    return parsed.netloc, parsed.path.lstrip("/")


def _extract_page(metadata: dict | None) -> int | None:
    """Liest die Seitenzahl aus den Bedrock-Metadaten (robust ggü. Typen)."""
    if not metadata:
        return None
    value = metadata.get(PAGE_METADATA_KEY)
    if value is None:
        # Fallback: irgendein Schlüssel, der auf 'page-number' endet.
        for key, val in metadata.items():
            if key.endswith("page-number"):
                value = val
                break
    if value is None:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


class _LinkBuilder:
    """Erzeugt präsignierte PDF-URLs (pro S3-Objekt einmal signiert & gecacht).

    - ``base(uri)``           – reine präsignierte URL (für den PDF.js-Viewer)
    - ``with_page(uri, page)`` – gleiche URL mit ``#page=N``-Fragment
    """

    def __init__(self, cfg: Config) -> None:
        self._client = get_client("s3")
        self._cfg = cfg
        self._cache: dict[str, str] = {}

    def base(self, uri: str | None) -> str | None:
        parsed = _parse_s3_uri(uri)
        if not parsed:
            return None
        if uri not in self._cache:
            bucket, key = parsed
            try:
                self._cache[uri] = self._client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=self._cfg.presign_expiry,
                )
            except Exception:  # noqa: BLE001 – Link ist optional
                self._cache[uri] = ""
        return self._cache[uri] or None

    def with_page(self, uri: str | None, page: int | None = None) -> str | None:
        base = self.base(uri)
        if not base:
            return None
        return f"{base}#page={page}" if page else base


def retrieve_and_generate(
    cfg: Config, question: str, session_id: str | None = None
) -> dict[str, Any]:
    """Beantwortet eine Frage grounded auf der Knowledge Base."""
    client = get_client("bedrock-agent-runtime")

    request: dict[str, Any] = {
        "input": {"text": question},
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": cfg.knowledge_base_id,
                "modelArn": cfg.generation_model_arn,
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {"numberOfResults": cfg.max_results}
                },
                "generationConfiguration": {
                    "promptTemplate": {"textPromptTemplate": GENERATION_PROMPT_TEMPLATE},
                    "inferenceConfig": {
                        "textInferenceConfig": {"temperature": 0, "maxTokens": 1024}
                    },
                },
            },
        },
    }
    # Folgefragen im selben Gesprächskontext.
    if session_id:
        request["sessionId"] = session_id

    response = client.retrieve_and_generate(**request)

    links = _LinkBuilder(cfg)
    citations = _flatten_citations(response.get("citations", []), links)
    sources = _aggregate_sources(citations, links)

    answer_text = response.get("output", {}).get("text", "")
    # "Sinnvoller Treffer" = es wurden Quellen herangezogen UND das Modell hat
    # nicht die Nicht-gefunden-Formulierung ausgegeben.
    grounded = bool(sources) and NO_MATCH_PHRASE not in answer_text.lower()

    return {
        "answer": answer_text,
        "sessionId": response.get("sessionId"),
        "citations": citations,
        "sources": sources,
        "grounded": grounded,
        "warning": None if grounded else NO_MATCH_WARNING,
    }


def _flatten_citations(raw_citations: list[dict], links: _LinkBuilder) -> list[dict]:
    result: list[dict] = []
    for citation in raw_citations:
        for ref in citation.get("retrievedReferences", []):
            uri = ref.get("location", {}).get("s3Location", {}).get("uri")
            metadata = ref.get("metadata", {})
            page = _extract_page(metadata)
            result.append(
                {
                    "uri": uri,
                    "document": _s3_uri_to_name(uri),
                    "page": page,
                    "snippet": ref.get("content", {}).get("text", ""),
                    "link": links.with_page(uri, page),
                    "pdfUrl": links.base(uri),
                    "metadata": metadata,
                }
            )
    return result


def _aggregate_sources(citations: list[dict], links: _LinkBuilder) -> list[dict]:
    """Fasst die Fundstellen je PDF zusammen (Seitenliste + Deeplink)."""
    by_uri: dict[str, dict] = {}
    for c in citations:
        uri = c.get("uri")
        if not uri:
            continue
        entry = by_uri.setdefault(
            uri, {"uri": uri, "document": c.get("document"), "pages": set()}
        )
        if c.get("page"):
            entry["pages"].add(c["page"])

    sources = []
    for entry in by_uri.values():
        pages = sorted(entry["pages"])
        sources.append(
            {
                "uri": entry["uri"],
                "document": entry["document"],
                "pages": pages,
                # Deeplink auf die erste relevante Seite.
                "link": links.with_page(entry["uri"], pages[0] if pages else None),
                "pdfUrl": links.base(entry["uri"]),
            }
        )
    return sources


def retrieve(cfg: Config, query: str, number_of_results: int | None = None) -> list[dict]:
    """Debug-Retrieval: liefert die rohen Treffer inkl. Score, ohne Generierung."""
    client = get_client("bedrock-agent-runtime")
    response = client.retrieve(
        knowledgeBaseId=cfg.knowledge_base_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": number_of_results or cfg.max_results
            }
        },
    )
    links = _LinkBuilder(cfg)
    results = []
    for item in response.get("retrievalResults", []):
        uri = item.get("location", {}).get("s3Location", {}).get("uri")
        metadata = item.get("metadata", {})
        page = _extract_page(metadata)
        results.append(
            {
                "uri": uri,
                "document": _s3_uri_to_name(uri),
                "page": page,
                "score": item.get("score"),
                "snippet": item.get("content", {}).get("text", ""),
                "link": links.with_page(uri, page),
                "pdfUrl": links.base(uri),
                "metadata": metadata,
            }
        )
    return results


def list_ingestion_jobs(cfg: Config, max_results: int = 10) -> list[dict]:
    """Listet die letzten Ingestion-Jobs inkl. Statistik (Debug/Transparenz)."""
    client = get_client("bedrock-agent")
    response = client.list_ingestion_jobs(
        knowledgeBaseId=cfg.knowledge_base_id,
        dataSourceId=cfg.data_source_id,
        maxResults=max_results,
        sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
    )
    jobs = []
    for job in response.get("ingestionJobSummaries", []):
        jobs.append(
            {
                "ingestionJobId": job.get("ingestionJobId"),
                "status": job.get("status"),
                "startedAt": job.get("startedAt"),
                "updatedAt": job.get("updatedAt"),
                "statistics": job.get("statistics", {}),
                "description": job.get("description"),
            }
        )
    return jobs


def list_documents(cfg: Config) -> list[dict]:
    """Listet die im S3-Bucket abgelegten Quelldokumente (unter dem Prefix)."""
    client = get_client("s3")
    paginator = client.get_paginator("list_objects_v2")
    documents = []
    for page in paginator.paginate(
        Bucket=cfg.documents_bucket, Prefix=cfg.documents_prefix
    ):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # "Ordner"-Platzhalter überspringen
            if key.endswith("/"):
                continue
            documents.append(
                {
                    "key": key,
                    "document": _s3_uri_to_name(key),
                    "size": obj.get("Size"),
                    "lastModified": obj.get("LastModified"),
                    "uri": f"s3://{cfg.documents_bucket}/{key}",
                }
            )
    return documents


def start_ingestion_job(cfg: Config, description: str = "") -> dict[str, Any]:
    """Startet einen Ingestion-Job. Läuft bereits einer, wird das toleriert."""
    client = get_client("bedrock-agent")
    kwargs: dict[str, Any] = {
        "knowledgeBaseId": cfg.knowledge_base_id,
        "dataSourceId": cfg.data_source_id,
    }
    if description:
        kwargs["description"] = description[:200]
    response = client.start_ingestion_job(**kwargs)
    job = response.get("ingestionJob", {})
    return {
        "ingestionJobId": job.get("ingestionJobId"),
        "status": job.get("status"),
    }
