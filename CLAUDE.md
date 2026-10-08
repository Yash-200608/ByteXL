# ByteXL — Project Rules

ByteXL is a local-first personal health copilot: upload a medical document → OCR → structured extraction → FHIR R4 → plain-language summary (English + Hindi) → unified timeline.

## Stack
- Python 3.11, FastAPI, Streamlit, MongoDB (JSON-file fallback), PaddleOCR, PyMuPDF, fhir.resources, Pydantic v2, pytest
- Local LLMs via Ollama only: `qwen2.5vl:7b` (vision), `qwen2.5:7b` (text). No paid APIs, no API keys.

## Hard rules
1. No code comments in source files.
2. Every LLM output is validated against a Pydantic schema; on failure, retry once with the validation error fed back; if it still fails, mark the result low confidence.
3. Abnormal flags (low / normal / high / critical / unknown) are computed in Python only, never by an LLM.
4. Summaries are generated only from validated, normalized JSON, never from raw images or OCR text.
5. No diagnosis, no dosage changes, no treatment advice in any user-facing text. Every summary carries the fixed disclaimer.
6. Configuration lives in `.env` and `app/config.py`. Model names and thresholds are never hardcoded elsewhere.
7. Drug name and dosage on handwritten prescriptions always require user confirmation.

## Workflow
- After every phase: run tests, fix failures, update `docs/PROGRESS.md`, then `git add -A && git commit -m "phase N: <summary>"`.
- `docs/PROGRESS.md` is the resume point: phase status, decisions, deviations, known issues, next step.
- Decisions that are not covered here are made autonomously and logged in `docs/PROGRESS.md`.

## Commands
- `make api` / `make ui` / `make test` / `make eval` / `make seed`
- Tests: `.venv/bin/pytest -q`
