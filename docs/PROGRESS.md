# ByteXL — Progress

Resume point for any new session. Read `CLAUDE.md`, then this file, then `docs/architecture.md`.

## Phase status

| Phase | Status | Commit |
|---|---|---|
| 1 Architecture | done | phase 1 |
| 2 Scaffold | pending | |
| 3 Ingest & OCR | pending | |
| 4 Extraction | pending | |
| 5 Normalization | pending | |
| 6 FHIR & API | pending | |
| 7 Summaries | pending | |
| 8 UI | pending | |
| 9 Hardening & demo | pending | |

## Environment (build machine)

- Cloud container: Ubuntu 24.04, 4 vCPU, 15 GB RAM, no GPU, no Docker daemon.
- Python 3.11 venv at `.venv`.
- Ollama 0.12.6 installed from the GitHub release tarball to `/opt/ollama`, started with `ollama serve`.
  Models pulled: `qwen2.5:7b`, `qwen2.5vl:7b`, `qwen2.5vl:3b`.
- MongoDB 7.0.14 tarball at `/opt/mongo`, started with `mongod --dbpath /tmp/mongo-data --fork`.
- PaddleOCR 3.7 / paddlepaddle 3.3 (CPU). Requires `enable_mkldnn=False` (oneDNN crash in 3.3.1).

## Decisions

1. `CLAUDE.md` did not exist; created it from the master prompt's global rules.
2. `samples/` was empty; created five synthetic documents with `scripts/make_samples.py` (fictional patient
   "Rahul Sharma", fictional facilities): text-layer lab PDF, photographed lab PNG, printed prescription JPG,
   handwriting-style prescription PNG, scanned (image-only) discharge PDF. They exercise every ingest path.
3. FHIR library: `fhir.resources` 7.1 (Pydantic v2). Pure R4 classes only exist in the Pydantic-v1 releases, so the
   `R4B` module is used; it is wire-compatible with R4 4.0.1 for every resource used. Bundles are tagged with NRCeS
   R4 profile URLs.
4. The LLM fills a flat LLM-facing schema; confidence and source boxes are computed deterministically afterwards.
5. Summary medicine instructions, values, flags and disclaimer are injected by code; the LLM writes prose only.
6. Upload pipeline runs as a background job with a polled `status.stage`; `?sync=true` runs inline (tests, seed).

## Deviations

- None yet.

## Known issues

- None yet.

## Next step

Phase 2 — scaffold.
