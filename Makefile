# hivestack — common developer + ops tasks.
# Wraps the scripts/ helpers so builds/tests/ops are discoverable from one place.
#
#   make dev          run API (uvicorn) locally
#   make test         run pytest unit suite
#   make e2e          run offline end-to-end suite
#   make typecheck    TS type-check the web app
#   make build        build the Docker image
#   make release      build + push to GHCR (use --no-push to skip push)
#   make backup       write a dated backup of /data + /config
#   make check-gpu    verify M40 / nvidia-smi
#
# VERSION / venv are discovered automatically.

SHELL := bash
PY ?= python3
VENV := .venv
ROOT := $(CURDIR)
VERSION := $(shell tr -d '[:space:]' < VERSION)

ifeq ($(OS),Windows_NT)
  PYBIN := $(ROOT)/$(VENV)/Scripts/python.exe
else
  PYBIN := $(ROOT)/$(VENV)/bin/python
endif

.PHONY: help refresh dev test e2e typecheck build release backup check-gpu

help: ## list common targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F'[:#]' '{printf "  %-10s %s\n", $$1, $$3}'

refresh: ## create venv + install runtime and dev deps
	$(PY) -m venv $(VENV)
	$(PYBIN) -m pip install --upgrade pip
	$(PYBIN) -m pip install -r backend/requirements.txt
	$(PYBIN) -m pip install -r backend/requirements-dev.txt

dev: ## run the API locally (dev.ps1/dev.sh equivalent)
	bash scripts/dev.sh

test: ## run the pytest unit suite
	$(PYBIN) -m pytest tests/unit -q

e2e: ## run the offline end-to-end suite
	$(PYBIN) tests/e2e_offline.py

typecheck: ## TS type-check the web app
	cd web && npm run typecheck

build: ## build the Docker image (hivestack:$(VERSION))
	bash scripts/build.sh

release: ## build + push the GHCR image (VERSION)
	bash scripts/release.sh

backup: ## write a dated backup of /data + /config
	$(PYBIN) scripts/backup.py --data runtime/data --config runtime/config --out runtime/backups

check-gpu: ## verify the M40 / nvidia-smi
	bash scripts/check-m40.sh
