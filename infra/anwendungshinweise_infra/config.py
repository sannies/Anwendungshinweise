"""Stack-Konfiguration, gespeist aus dem CDK-Context (``cdk.json`` / ``-c``)."""

from __future__ import annotations

from dataclasses import dataclass

import aws_cdk as cdk


@dataclass(frozen=True)
class StackConfig:
    resource_prefix: str
    region: str
    documents_prefix: str
    embedding_model_id: str
    embedding_dimensions: int
    generation_model_id: str
    max_results: int
    min_score: float
    chunk_max_tokens: int
    chunk_overlap_percentage: int

    @classmethod
    def from_app(cls, app: cdk.App) -> StackConfig:
        ctx = app.node.try_get_context

        def get(key: str, default):
            value = ctx(key)
            return default if value is None else value

        return cls(
            resource_prefix=get("resourcePrefix", "anwendungshinweise"),
            region=get("region", "eu-central-1"),
            documents_prefix=get("documentsPrefix", "documents/"),
            embedding_model_id=get("embeddingModelId", "amazon.titan-embed-text-v2:0"),
            embedding_dimensions=int(get("embeddingDimensions", 1024)),
            generation_model_id=get(
                "generationModelId", "mistral.mistral-large-2402-v1:0"
            ),
            max_results=int(get("maxResults", 8)),
            min_score=float(get("minScore", 0.4)),
            chunk_max_tokens=int(get("chunkMaxTokens", 300)),
            chunk_overlap_percentage=int(get("chunkOverlapPercentage", 20)),
        )
