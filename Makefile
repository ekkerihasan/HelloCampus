PY ?= python

.PHONY: dev backend frontend scrape ingest validate-locality test smoke tunnel

dev backend frontend scrape ingest validate-locality test smoke tunnel:
	$(PY) tasks.py $@
