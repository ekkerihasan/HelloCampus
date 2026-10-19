PY ?= python

.PHONY: dev backend frontend scrape ingest validate-locality test smoke tunnel quiz

dev backend frontend scrape ingest validate-locality test smoke tunnel:
	$(PY) tasks.py $@

# Standalone quiz builder: avoids the core task runner while the pivot is mid-change.
quiz:
	$(PY) -m backend.quiz $(QUIZ_ARGS)
