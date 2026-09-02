PYTHON ?= python3

.PHONY: help test ingest serve run clean

help:
	@echo "make test     run unit tests"
	@echo "make ingest   pull CAD into local SQLite (30 days)"
	@echo "make serve    start the map UI"
	@echo "make run      ingest if needed, then serve"
	@echo "make clean    remove Python caches"

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

ingest:
	$(PYTHON) -m sfalert ingest --days 30

serve:
	$(PYTHON) -m sfalert serve

run:
	$(PYTHON) -m sfalert

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.py[cod]' -delete
