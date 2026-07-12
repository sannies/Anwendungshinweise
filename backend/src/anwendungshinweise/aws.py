"""Zentrale, gecachte boto3-Clients.

Die Clients werden lazy erzeugt und modulweit gecacht. In Tests kann
``get_client`` gemonkeypatcht oder der Cache über ``_CLIENTS`` geleert werden.
"""

from __future__ import annotations

import os
from typing import Any

import boto3

_CLIENTS: dict[str, Any] = {}


def get_client(service: str) -> Any:
    """Liefert einen (gecachten) boto3-Client für den angegebenen Service."""
    if service not in _CLIENTS:
        region = os.environ.get("AWS_REGION", "eu-central-1")
        _CLIENTS[service] = boto3.client(service, region_name=region)
    return _CLIENTS[service]
