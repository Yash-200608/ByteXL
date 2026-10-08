PY ?= .venv/bin/python
PORT ?= 8000

.PHONY: setup api ui test eval seed samples mongo ollama

setup:
	python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

api:
	$(PY) -m uvicorn app.api.main:app --host 0.0.0.0 --port $(PORT)

ui:
	$(PY) -m streamlit run ui/app.py --server.port 8501

test:
	$(PY) -m pytest -q

eval:
	$(PY) scripts/eval.py

seed:
	$(PY) scripts/seed.py

samples:
	$(PY) scripts/make_samples.py

mongo:
	docker compose up -d mongo
