# Anwendungshinweise-Wissensbasis

Eine AWS-CDK-basierte Anwendung, die PDF-**Anwendungshinweise** (Merkblätter,
technische Richtlinien) des deutschen Maler- und Lackiererhandwerks einliest,
indiziert und **natürlichsprachliche Fachfragen** beantwortet – **ausschließlich**
auf Grundlage der hinterlegten Dokumente (kein allgemeines Weltwissen).

> Beispielfragen:
> - *„Ich habe eine neue Kalksandsteinfassade ohne Wärmedämmung und möchte die
>   Dämmung verkleben. Muss ich die Fassade vorher grundieren?“*
> - *„Ich habe losen Putz auf einer Wärmedämmverbundfassade und bin mit der
>   Sanierung beauftragt. Wie gehe ich vor?“*

Die Anwendung dient als Grundlage, um zu beurteilen, ob eine Arbeit „nach den
Regeln der Kunst“ ausgeführt wurde – im Streitfall ein wichtiger Nachweis.

## Was steckt drin?

| Anforderung | Umsetzung |
|---|---|
| PDFs einlesen & verstehen | Amazon Bedrock Knowledge Base (RAG) |
| Automatische Indizierung bei S3-Upload | S3-Event → Lambda → `StartIngestionJob` |
| Antworten nur aus dem PDF-Kanon | `RetrieveAndGenerate` + strikter Grounding-Prompt, Temperatur 0 |
| Abfrage-API | API Gateway (REST) + Lambda |
| „Welche PDFs sind eingeflossen?“ + Debug | `/documents`, `/ingestion-jobs`, `/retrieve` |
| Kleines Demo-Frontend | Vue 3 (Vite) auf S3 + CloudFront |
| Region | **eu-central-1 (Frankfurt)** |
| Backend | **Python** (nur boto3, kein Bundling nötig) |
| Vektorspeicher | **Amazon S3 Vectors** (pay-per-use, günstig für Demos) |

Architekturdetails: siehe [`docs/architecture.md`](docs/architecture.md).

## Projektstruktur

```
.
├── infra/                     # AWS-CDK-App (Python)
│   ├── app.py
│   ├── cdk.json               # Konfiguration (Modelle, Prefix, Chunking …)
│   ├── anwendungshinweise_infra/
│   │   ├── knowledge_base_construct.py   # S3 + S3 Vectors + Bedrock KB
│   │   ├── backend_construct.py          # Lambdas + REST-API + S3-Trigger
│   │   ├── frontend_construct.py         # S3 + CloudFront
│   │   └── main_stack.py
│   └── tests/                 # Template-Assertions
├── backend/                   # Lambda-Handler (Python, boto3)
│   ├── src/anwendungshinweise/
│   │   ├── api.py             # HTTP-Router (query/documents/ingestion-jobs/retrieve)
│   │   ├── ingest.py          # S3-Trigger → Ingestion-Job
│   │   └── knowledge_base.py  # Bedrock-/S3-Fachlogik + Grounding-Prompt
│   └── tests/
├── frontend/                  # Vue-3-Demo (Vite)
│   └── src/{App.vue,api.js}
├── docs/architecture.md
├── sample-docs/               # (leer) Ablage für lokale Test-PDFs
├── pyproject.toml            # uv-Projekt + poe-Tasks (Orchestrierung)
└── uv.lock
```

## Voraussetzungen

- **[uv](https://docs.astral.sh/uv/)** (verwaltet Python-Env und Tasks), **Node ≥ 20**, **npm**
- **Python ≥ 3.11** (uv installiert bei Bedarf eine passende Version selbst)
- **AWS CLI** konfiguriert mit einem Profil/Konto für **eu-central-1**
- In der Bedrock-Konsole (eu-central-1) **Modellzugriff freischalten** für:
  - `Amazon Titan Text Embeddings V2` (Embeddings)
  - `Mistral Large` (Generierung, PoC-Default – bzw. das in `cdk.json` gewählte Modell)
- **Docker wird nicht benötigt** – die Lambdas nutzen ausschließlich das im
  Runtime enthaltene `boto3`.

> **Hinweis zu S3 Vectors:** Der Vektorspeicher „Amazon S3 Vectors“ ist in
> Frankfurt (eu-central-1) verfügbar. Sollte er in einem Konto (noch) nicht
> nutzbar sein, kann in `cdk.json` auf einen anderen Vektorspeicher gewechselt
> werden – die Anwendungslogik bleibt gleich.

## Loslegen

Die Orchestrierung läuft über **uv + poethepoet** (Tasks in `pyproject.toml`).
`uv run poe` listet alle Tasks auf.

```bash
# 1) Python-Env einrichten (.venv) + Frontend-Abhängigkeiten
uv sync
uv run poe install        # npm install im Frontend

# 2) Tests ausführen
uv run poe test

# 3) Einmalig: CDK-Bootstrap für Konto/Region
uv run poe bootstrap

# 4) Frontend bauen + kompletten Stack deployen
uv run poe deploy
```

Nach dem Deploy zeigt die CLI u. a. diese **Outputs**:

- `ApiUrl` – Basis-URL der REST-API
- `FrontendUrl` – öffentliche CloudFront-URL der Demo
- `DocumentsBucketName` – S3-Bucket für die PDFs
- `KnowledgeBaseId` / `DataSourceId`

## Dokumente hinzufügen

PDFs in den Bucket (unter dem Prefix `documents/`) hochladen – die Indizierung
startet automatisch:

```bash
aws s3 cp mein-merkblatt.pdf \
  s3://<DocumentsBucketName>/documents/ --region eu-central-1
```

Fortschritt prüfen: `GET <ApiUrl>ingestion-jobs` oder im Frontend unter
**„Wissensbasis“**.

## API

Alle Endpunkte sind CORS-fähig. Basis-URL = Stack-Output `ApiUrl` (endet auf `/prod/`).

| Methode & Pfad | Zweck |
|---|---|
| `POST /query` | Frage beantworten. Body: `{"question": "...", "sessionId": "optional"}` |
| `GET /documents` | Im Bucket abgelegte Quelldokumente auflisten |
| `GET /ingestion-jobs` | Status/Statistik der Indizierungs-Läufe |
| `GET /retrieve?q=...` | Debug: rohe Vektortreffer inkl. Score (ohne Generierung) |
| `GET /health` | Health-Check |

Beispiel:

```bash
curl -s -X POST "<ApiUrl>query" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Muss ich eine neue Kalksandsteinfassade vor dem Verkleben der Dämmung grundieren?"}' | jq
```

Antwortformat:

```json
{
  "answer": "…",
  "sessionId": "…",
  "grounded": true,
  "warning": null,
  "sources": [
    {
      "document": "bfs-merkblatt.pdf",
      "uri": "s3://…/bfs-merkblatt.pdf",
      "pages": [3, 5],
      "link": "https://…/bfs-merkblatt.pdf?X-Amz-…#page=3"
    }
  ],
  "citations": [
    {
      "document": "bfs-merkblatt.pdf",
      "page": 3,
      "snippet": "…wörtlich zitierte Passage…",
      "link": "https://…#page=3",
      "uri": "s3://…"
    }
  ]
}
```

### Quellen, Seiten & Deeplinks

- Wird **kein ausreichender Treffer** in den PDFs gefunden, liefert die API
  `grounded: false` samt `warning`-Text; das Frontend zeigt dann eine deutliche
  Warnung und `uv run poe demo` steigt mit Warnung und Exit-Code 2 aus. Als
  „kein Treffer" gilt: keine Quellen, die Nicht-gefunden-Formulierung des
  Modells, **oder** ein bester Relevanzscore unter `minScore` (dann wird gar
  nicht erst generiert). Das Feld `topScore` in der Antwort zeigt den besten Score.
- Die Vektorsuche läuft automatisch über **alle** indizierten PDFs; die
  zurückgegebenen `sources` sind genau die für die Frage **relevanten** PDFs.
- Jede Fundstelle enthält die **Seitenzahl** (aus dem Bedrock-Metadatum
  `x-amz-bedrock-kb-document-page-number`) und einen **präsignierten Link**, der
  das PDF per `#page=N` direkt auf der Seite öffnet (Standard-PDF-Viewer der
  Browser). Der `snippet` gibt die wörtlich zitierte Passage – so ist der
  Absatz auf der Seite sofort auffindbar.
- Absatz-/Überschriften-Anker (`#nameddest=…`) funktionieren nur, wenn das PDF
  entsprechende *named destinations* enthält – das ist bei Merkblättern selten,
  daher der robuste Weg über Seite + Zitat.

### In-PDF-Hervorhebung (Frontend)

Das Frontend bettet einen **PDF.js-Viewer** ein: Ein Klick auf „Im PDF anzeigen"
öffnet die Fundstelle, springt auf die Seite und **markiert das wörtlich
zitierte Textstück** direkt im PDF (Textsuche in der PDF-Textebene). Damit der
Browser die PDF-Bytes laden darf, ist am Dokumenten-Bucket **CORS** aktiv; das
Chunking der Knowledge Base ist auf **SEMANTIC** gestellt (Fundstellen näher an
Absätzen). Findet der Viewer den Zitattext auf der Seite nicht exakt (z. B. durch
Trennungen), zeigt er die Seite unmarkiert an.

### Design

Die Oberfläche ist optisch an den **Malerverband Niedersachsen** angelehnt
(seriöse Blau/Weiß-Optik). Der Markenton lässt sich zentral über die
CSS-Variable `--brand` in `frontend/src/style.css` anpassen; für das echte Logo
kann der Platzhalter „MV" in `App.vue` ersetzt werden.

## Frontend lokal entwickeln

```bash
cd frontend
cp .env.example .env      # VITE_API_BASE_URL = ApiUrl aus dem Deploy eintragen
cd .. && uv run poe dev-frontend   # http://localhost:5173
```

Im Deployment wird die API-URL automatisch über eine `config.json` im
S3-Bucket bereitgestellt – lokal übersteuert `VITE_API_BASE_URL`.

## Konfiguration

Zentrale Parameter stehen im CDK-Context (`infra/cdk.json`) und lassen sich per
`-c key=value` überschreiben:

| Schlüssel | Default | Bedeutung |
|---|---|---|
| `region` | `eu-central-1` | AWS-Region |
| `documentsPrefix` | `documents/` | S3-Prefix der Quelldateien |
| `embeddingModelId` | `amazon.titan-embed-text-v2:0` | Embedding-Modell |
| `embeddingDimensions` | `1024` | Vektordimension (muss zum Modell passen) |
| `generationModelId` | `mistral.mistral-large-2402-v1:0` | Generierungsmodell. Foundation-Model-ID (z. B. `mistral.…`), Inference-Profile-ID (z. B. `eu.anthropic.claude-3-5-sonnet-20240620-v1:0`) oder volle ARN – die passende ARN wird automatisch abgeleitet. |
| `maxResults` | `8` | Anzahl der abgerufenen Passagen |
| `minScore` | `0.4` | Mindest-Relevanzscore des besten Treffers; darunter Warnung statt Antwort (`0` = aus) |
| `chunkMaxTokens` / `chunkOverlapPercentage` | `300` / `20` | Chunking |

## Tests & Qualität

```bash
uv run poe test     # Backend- + Infra-Tests
uv run poe lint     # Ruff (backend, infra, scripts)
uv run poe synth    # CloudFormation-Template erzeugen
```

`uv run poe` (ohne Task) listet alle verfügbaren Tasks auf. Die CI
(`.github/workflows/ci.yml`) führt Lint, Tests inkl. `cdk synth` und den
Frontend-Build aus.

## Echte Frage stellen (nach dem Deploy)

```bash
# PDF hochladen, Indizierung abwarten, Frage stellen:
uv run poe demo --pdf sample-docs/mein-merkblatt.pdf \
  --question "Muss ich eine neue Kalksandsteinfassade vor dem Verkleben der Dämmung grundieren?"

# Nur fragen (PDFs bereits indiziert):
uv run poe demo --skip-upload --question "Wie gehe ich bei losem Putz auf einer WDVS-Fassade vor?"
```

## Aufräumen

```bash
uv run poe destroy
```

> Der S3-Vectors-Bucket lässt sich nur löschen, wenn er leer ist. Sollte
> `destroy` daran scheitern, zuvor die Knowledge Base / Datenquelle abbauen
> lassen (die Datenquelle hat `DataDeletionPolicy = DELETE`) bzw. die Vektoren
> manuell entfernen.

## Kosten (grobe Einordnung)

S3 Vectors verursacht **keine** dauerhaften Kapazitätskosten (im Gegensatz zu
OpenSearch Serverless). Relevant sind vor allem Bedrock-Aufrufe (Embeddings beim
Indizieren + Generierung pro Frage) sowie geringe S3-/CloudFront-Kosten. Für
eine Demo mit wenigen Dokumenten und Anfragen bleibt das im niedrigen Bereich.
