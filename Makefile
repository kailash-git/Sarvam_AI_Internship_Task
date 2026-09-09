.PHONY: install migrate seed reset run eval test walkthrough clean

PY ?= python

install:
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

migrate:
	$(PY) -m app.db.migrate

seed:
	$(PY) -m app.db.seed

reset:
	$(PY) -m cli.kivi reset

run:
	$(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

eval:
	$(PY) -m eval.run

test:
	$(PY) -m pytest -q

walkthrough:
	$(PY) -m cli.kivi walkthrough

clean:
	rm -f kivi.db kivi.db-* eval/_eval.db eval/_eval.db-*
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
