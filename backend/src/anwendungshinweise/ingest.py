"""Lambda-Handler für die automatische Indizierung.

Wird durch S3-``ObjectCreated``/``ObjectRemoved``-Events des Dokumenten-Buckets
ausgelöst und startet einen Bedrock-Ingestion-Job. Läuft bereits ein Job,
liefert Bedrock eine ``ConflictException`` – die wird toleriert, da der laufende
Job die neuen Objekte ohnehin miterfasst bzw. ein Folge-Event einen neuen Job
auslöst.
"""

from __future__ import annotations

import logging
from typing import Any

from botocore.exceptions import ClientError

from . import knowledge_base as kb
from .config import load_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, _context: Any = None) -> dict:
    records = event.get("Records", [])
    object_keys = [
        r.get("s3", {}).get("object", {}).get("key")
        for r in records
        if "s3" in r
    ]
    logger.info("S3-Event für %d Objekt(e): %s", len(object_keys), object_keys)

    cfg = load_config()
    description = "Auto-Ingestion nach S3-Upload: " + ", ".join(
        filter(None, object_keys)
    )

    try:
        result = kb.start_ingestion_job(cfg, description=description)
        logger.info("Ingestion-Job gestartet: %s", result)
        return {"started": True, **result}
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "ConflictException":
            logger.info("Ingestion-Job läuft bereits – übersprungen.")
            return {"started": False, "reason": "already-running"}
        logger.exception("Ingestion-Job konnte nicht gestartet werden")
        raise
