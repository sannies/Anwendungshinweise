# Anwendungshinweise-Wissensbasis – Entwicklungs- und Deployment-Aufgaben
#
# Voraussetzungen: Python >=3.11, Node >=20, AWS CLI konfiguriert (Region
# eu-central-1), Docker wird NICHT benötigt.

SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CDK := npx --yes aws-cdk@2

.DEFAULT_GOAL := help

.PHONY: help
help: ## Diese Hilfe anzeigen
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------
$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

.PHONY: install
install: $(VENV)/bin/activate ## Alle Python- und Frontend-Abhängigkeiten installieren
	$(PIP) install -r infra/requirements-dev.txt
	$(PIP) install -e "backend[dev]"
	cd frontend && npm install

# --------------------------------------------------------------------------
# Qualität
# --------------------------------------------------------------------------
.PHONY: test
test: test-backend test-infra ## Alle Python-Tests ausführen

.PHONY: test-backend
test-backend: ## Backend-Tests
	cd backend && ../$(PY) -m pytest -q

.PHONY: test-infra
test-infra: ## CDK-Infrastruktur-Tests
	cd infra && PYTHONPATH=. ../$(PY) -m pytest -q

.PHONY: lint
lint: ## Ruff-Linting über Backend und Infra
	$(VENV)/bin/ruff check backend infra

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
# Die CDK-App wird über die venv-Python-Umgebung ausgeführt (cdk.json ->
# "python3 app.py"), daher vor jedem CDK-Aufruf die venv aktivieren.
.PHONY: synth
synth: ## CloudFormation-Template synthetisieren
	cd infra && source ../$(VENV)/bin/activate && $(CDK) synth

.PHONY: bootstrap
bootstrap: ## CDK-Bootstrap für das Konto/Region (einmalig)
	cd infra && source ../$(VENV)/bin/activate && $(CDK) bootstrap

.PHONY: deploy
deploy: build-frontend ## Frontend bauen und den kompletten Stack deployen
	cd infra && source ../$(VENV)/bin/activate && $(CDK) deploy --require-approval never

.PHONY: destroy
destroy: ## Stack wieder abbauen
	cd infra && source ../$(VENV)/bin/activate && $(CDK) destroy --force
