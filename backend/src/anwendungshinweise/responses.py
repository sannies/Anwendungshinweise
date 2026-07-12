"""Hilfsfunktionen für HTTP-Antworten (API Gateway REST, Proxy-Integration v1)."""

from __future__ import annotations

import json
from typing import Any

# Für eine Demo ist ein offener CORS-Header ausreichend. In Produktion sollte
# hier die konkrete CloudFront-Domain stehen.
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def json_response(status_code: int, body: Any) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json; charset=utf-8", **CORS_HEADERS},
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def ok(body: Any) -> dict:
    return json_response(200, body)


def bad_request(message: str) -> dict:
    return json_response(400, {"error": message})


def not_found(message: str = "Nicht gefunden") -> dict:
    return json_response(404, {"error": message})


def server_error(message: str) -> dict:
    return json_response(500, {"error": message})
