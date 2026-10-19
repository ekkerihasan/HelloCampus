PY ?= python

.PHONY: dev backend frontend scrape ingest rag-eval quiz verify-models validate-locality test smoke tunnel

dev backend frontend scrape ingest rag-eval quiz verify-models validate-locality test smoke tunnel:
	$(PY) tasks.py $@
