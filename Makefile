PY ?= python

.PHONY: dev backend frontend scrape ingest rag-eval verify-models validate-locality test smoke tunnel

dev backend frontend scrape ingest rag-eval verify-models validate-locality test smoke tunnel:
	$(PY) tasks.py $@
