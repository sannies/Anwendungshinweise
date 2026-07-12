# Anwendungshinweise-Wissensbasis – Entwicklungs- und Deployment-Aufgaben
#
# Voraussetzungen: Python >=3.11, Node >=20, AWS CLI konfiguriert (Region
# eu-central-1), Docker wird NICHT benötigt.

SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CDK := npx --yes aws-cdk@2
# Absoluter Pfad zum venv-Python. Wird der CDK-CLI per --app übergeben, damit
# die App garantiert mit dem venv-Interpreter läuft – unabhängig davon, worauf
# "python3" nach einem `source activate` gerade zeigt.
CDK_APP := --app "$(CURDIR)/$(VENV)/bin/python app.py"

.DEFAULT_GOAL := help

.PHONY: help
help: ## Diese Hilfe anzeigen
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --------------------------------------------------------------------------
# Setup (selbst-bootstrappend: CDK- und Test-Targets installieren die
# Python-Abhängigkeiten bei Bedarf automatisch in die venv)
# --------------------------------------------------------------------------
DEPS_STAMP := $(VENV)/.deps-installed

$(DEPS_STAMP): infra/requirements-dev.txt backend/pyproject.toml
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r infra/requirements-dev.txt
	$(PIP) install -e "backend[dev]"
	touch $(DEPS_STAMP)

.PHONY: install
install: $(DEPS_STAMP) ## Alle Python- und Frontend-Abhängigkeiten installieren
	cd frontend && npm install

# --------------------------------------------------------------------------
# Qualität
# --------------------------------------------------------------------------
.PHONY: test
test: test-backend test-infra ## Alle Python-Tests ausführen

.PHONY: test-backend
test-backend: $(DEPS_STAMP) ## Backend-Tests
	cd backend && ../$(PY) -m pytest -q

.PHONY: test-infra
test-infra: $(DEPS_STAMP) ## CDK-Infrastruktur-Tests
	cd infra && PYTHONPATH=. ../$(PY) -m pytest -q

.PHONY: lint
lint: $(DEPS_STAMP) ## Ruff-Linting über Backend und Infra
	$(VENV)/bin/ruff check backend infra scripts

# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------
.PHONY: dev-frontend
dev-frontend: ## Frontend lokal starten (Vite Dev-Server, Port 5173)
	cd frontend && npm run dev

.PHONY: build-frontend
build-frontend: ## Frontend für die Auslieferung bauen (nach frontend/dist)
	cd frontend && npm run build

# --------------------------------------------------------------------------
# Infrastruktur (CDK)
# --------------------------------------------------------------------------
# Der CDK-CLI wird der venv-Interpreter explizit via --app übergeben
# (siehe CDK_APP oben) – kein Verlass auf `source activate`.
.PHONY: synth
synth: $(DEPS_STAMP) ## CloudFormation-Template synthetisieren
	cd infra && $(CDK) synth $(CDK_APP)

.PHONY: bootstrap
bootstrap: $(DEPS_STAMP) ## CDK-Bootstrap für das Konto/Region (einmalig)
	cd infra && $(CDK) bootstrap $(CDK_APP)

.PHONY: deploy
deploy: $(DEPS_STAMP) build-frontend ## Frontend bauen und den kompletten Stack deployen
	cd infra && $(CDK) deploy $(CDK_APP) --require-approval never

.PHONY: destroy
destroy: $(DEPS_STAMP) ## Stack wieder abbauen
	cd infra && $(CDK) destroy $(CDK_APP) --force

# --------------------------------------------------------------------------
# End-to-End-Demo (nach dem Deploy)
# --------------------------------------------------------------------------
.PHONY: demo
demo: $(DEPS_STAMP) ## E2E: PDF=… hochladen, indizieren, Frage stellen. Bsp: make demo PDF=sample-docs/x.pdf Q="…"
	$(PY) scripts/e2e_demo.py --pdf "$(PDF)" --question "$(Q)"

.PHONY: ask
ask: $(DEPS_STAMP) ## Nur fragen (PDFs schon indiziert). Bsp: make ask Q="Wie gehe ich bei losem Putz vor?"
	$(PY) scripts/e2e_demo.py --skip-upload --question "$(Q)"
