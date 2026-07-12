"""Fachlogik rund um die Bedrock Knowledge Base.

Kapselt die Bedrock-Aufrufe (Retrieve, RetrieveAndGenerate, Ingestion-Jobs)
sowie die S3-Auflistung der Quelldokumente. Bewusst frei von HTTP-Details,
damit die Funktionen einzeln testbar sind.
"""

from __future__ import annotations

from typing import Any

from .aws import get_client
from .config import Config

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
- Erfinde keine Normen, Kennzahlen, Fristen oder Produktnamen, die nicht in den \
Suchergebnissen stehen.

Suchergebnisse (nummeriert):
$search_results$

$output_format_instructions$"""


def _s3_uri_to_name(uri: str | None) -> str | None:
    if not uri:
        return None
    # s3://bucket/documents/foo.pdf -> foo.pdf
    return uri.rstrip("/").split("/")[-1]


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

    citations = _flatten_citations(response.get("citations", []))
    sources = _dedupe_sources(citations)

    return {
        "answer": response.get("output", {}).get("text", ""),
        "sessionId": response.get("sessionId"),
        "citations": citations,
        "sources": sources,
    }


def _flatten_citations(raw_citations: list[dict]) -> list[dict]:
    result: list[dict] = []
    for citation in raw_citations:
        for ref in citation.get("retrievedReferences", []):
            uri = ref.get("location", {}).get("s3Location", {}).get("uri")
            result.append(
                {
                    "uri": uri,
                    "document": _s3_uri_to_name(uri),
                    "snippet": ref.get("content", {}).get("text", ""),
                    "metadata": ref.get("metadata", {}),
                }
            )
    return result


def _dedupe_sources(citations: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for c in citations:
        uri = c.get("uri")
        if uri and uri not in seen:
            seen[uri] = {"uri": uri, "document": c.get("document")}
    return list(seen.values())


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
    results = []
    for item in response.get("retrievalResults", []):
        uri = item.get("location", {}).get("s3Location", {}).get("uri")
        results.append(
            {
                "uri": uri,
                "document": _s3_uri_to_name(uri),
                "score": item.get("score"),
                "snippet": item.get("content", {}).get("text", ""),
                "metadata": item.get("metadata", {}),
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
