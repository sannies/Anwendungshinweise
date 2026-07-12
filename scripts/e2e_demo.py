#!/usr/bin/env python3
"""End-to-End-Demo: PDF hochladen, Indizierung abwarten, echte Frage stellen.

Voraussetzung: Der Stack ist deployt (``make deploy``) und es bestehen gültige
AWS-Credentials für eu-central-1. Liest die Stack-Outputs selbst aus, es sind
also keine URLs/Bucket-Namen von Hand nötig.

Beispiele
---------
    # PDF hochladen, auf Indizierung warten, Frage stellen:
    python scripts/e2e_demo.py \
        --pdf sample-docs/bfs-merkblatt.pdf \
        --question "Muss ich eine Kalksandsteinfassade vor dem Dämmung-Verkleben grundieren?"

    # Nur fragen (PDFs sind bereits indiziert):
    python scripts/e2e_demo.py --skip-upload \
        --question "Wie gehe ich bei losem Putz auf einer WDVS-Fassade vor?"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import boto3

REGION = "eu-central-1"


def get_outputs(stack_name: str) -> dict:
    cfn = boto3.client("cloudformation", region_name=REGION)
    stacks = cfn.describe_stacks(StackName=stack_name)["Stacks"]
    outputs = stacks[0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def upload_pdf(bucket: str, prefix: str, pdf_path: Path) -> None:
    s3 = boto3.client("s3", region_name=REGION)
    key = prefix + pdf_path.name
    print(f"→ Lade {pdf_path} nach s3://{bucket}/{key} …")
    s3.upload_file(str(pdf_path), bucket, key)


def api_get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=60) as resp:
        return json.load(resp)


def api_post(base: str, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def wait_for_ingestion(base: str, timeout_s: int = 600) -> None:
    print("→ Warte auf Abschluss der Indizierung …")
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        jobs = api_get(base, "/ingestion-jobs").get("jobs", [])
        if jobs:
            job = jobs[0]
            status = job.get("status")
            if status != last_status:
                print(f"   Status: {status}  {job.get('statistics', {})}")
                last_status = status
            if status == "COMPLETE":
                return
            if status == "FAILED":
                sys.exit(f"Indizierung fehlgeschlagen: {job}")
        time.sleep(10)
    sys.exit("Timeout beim Warten auf die Indizierung.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", default="AnwendungshinweiseStack")
    parser.add_argument("--pdf", type=Path, help="PDF, das hochgeladen wird")
    parser.add_argument("--skip-upload", action="store_true", help="Nur fragen")
    parser.add_argument("--question", required=True, help="Die zu stellende Frage")
    args = parser.parse_args()

    outputs = get_outputs(args.stack)
    api_url = outputs["ApiUrl"]
    bucket = outputs["DocumentsBucketName"]
    print(f"API:    {api_url}")
    print(f"Bucket: {bucket}\n")

    if not args.skip_upload:
        if not args.pdf or not args.pdf.is_file():
            sys.exit("Bitte ein existierendes --pdf angeben (oder --skip-upload).")
        upload_pdf(bucket, "documents/", args.pdf)
        wait_for_ingestion(api_url)

    print(f"\n❓ Frage: {args.question}")
    result = api_post(api_url, "/query", {"question": args.question})

    print("\n💬 Antwort:")
    print(result.get("answer", "<keine Antwort>"))

    sources = result.get("sources", [])
    if sources:
        print("\n📄 Relevante Dokumente:")
        for s in sources:
            pages = s.get("pages") or []
            page_str = f" (Seite {', '.join(map(str, pages))})" if pages else ""
            print(f"   - {s.get('document')}{page_str}")
            if s.get("link"):
                print(f"     {s['link']}")

    # Mit Warnung + Fehlercode aussteigen, wenn kein sinnvoller Treffer.
    if result.get("grounded") is False or result.get("warning"):
        warning = result.get("warning") or (
            "Kein ausreichender Treffer in den Anwendungshinweisen gefunden."
        )
        print(f"\n⚠️  WARNUNG: {warning}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
