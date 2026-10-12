PY ?= .venv/bin/python
PORT ?= 8000
EVAL_TRUTH ?= tests/fixtures/synthetic_truth

.PHONY: setup api ui test test-fast test-slow eval eval-fresh seed samples mongo ollama

setup:
	python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

api:
	$(PY) -m uvicorn app.api.main:app --host 0.0.0.0 --port $(PORT)

ui:
	$(PY) -m streamlit run ui/app.py --server.port 8501

test:
	$(PY) -m pytest -q

test-fast:
	$(PY) -m pytest -q -m "not slow"

test-slow:
	$(PY) -m pytest -q -m slow

eval:
	$(PY) scripts/eval.py --expected-dir $(EVAL_TRUTH)

eval-fresh:
	$(PY) scripts/eval.py --fresh --expected-dir $(EVAL_TRUTH)

seed:
	$(PY) scripts/seed.py

samples:
	$(PY) scripts/make_samples.py

mongo:
	docker compose up -d mongo
