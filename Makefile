PYTHON ?= python3
IMAGE ?= ghcr.io/jaimehisao/sfalert

.PHONY: help test coverage ingest serve run docker clean

help:
	@echo "make test       run unit tests"
	@echo "make coverage  run unit tests with an 85% coverage gate (pip install -e '.[dev]' first)"
	@echo "make ingest    pull CAD into local SQLite (30 days)"
	@echo "make serve     start the map UI"
	@echo "make run       ingest if needed, then serve"
	@echo "make docker    build the container image locally"
	@echo "make clean     remove Python caches"

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

coverage:
	$(PYTHON) -m coverage run -m unittest discover -s tests -t . -v
	$(PYTHON) -m coverage report --fail-under=85

ingest:
	$(PYTHON) -m sfalert ingest --days 30

serve:
	$(PYTHON) -m sfalert serve

run:
	$(PYTHON) -m sfalert

docker:
	docker build -t $(IMAGE):local .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.py[cod]' -delete
