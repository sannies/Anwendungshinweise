"""Laufzeit-Konfiguration der Lambda-Handler.

Alle Werte kommen aus Umgebungsvariablen, die vom CDK-Stack gesetzt werden.
Die Konfiguration wird bewusst *pro Aufruf* geladen (``load_config``), damit
Tests die Umgebung monkeypatchen können, ohne Modul-Reloads zu benötigen.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Wird geworfen, wenn eine erforderliche Umgebungsvariable fehlt."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"Erforderliche Umgebungsvariable fehlt: {name}")
    return value


@dataclass(frozen=True)
class Config:
    knowledge_base_id: str
    data_source_id: str
    documents_bucket: str
    documents_prefix: str
    generation_model_arn: str
    region: str
    max_results: int
    # Gültigkeitsdauer der präsignierten PDF-Links (Sekunden).
    presign_expiry: int


def load_config() -> Config:
    """Liest die Konfiguration aus den Umgebungsvariablen."""
    return Config(
        knowledge_base_id=_require("KNOWLEDGE_BASE_ID"),
        data_source_id=_require("DATA_SOURCE_ID"),
        documents_bucket=_require("DOCUMENTS_BUCKET"),
        documents_prefix=os.environ.get("DOCUMENTS_PREFIX", "documents/"),
        generation_model_arn=_require("GENERATION_MODEL_ARN"),
        region=os.environ.get("AWS_REGION", "eu-central-1"),
        max_results=int(os.environ.get("MAX_RESULTS", "8")),
        presign_expiry=int(os.environ.get("PRESIGN_EXPIRY", "3600")),
    )
