# ByteXL — Progress

Resume point for any new session. Read `CLAUDE.md`, then this file, then `docs/architecture.md`.

## Phase status

| Phase | Status | Commit |
|---|---|---|
| 1 Architecture | done | phase 1 |
| 2 Scaffold | done | phase 2 |
| 3 Ingest & OCR | done | phase 3 |
| 4 Extraction | done | phase 4 |
| 5 Normalization | done | phase 5 |
| 6 FHIR & API | done | phase 6 |
| 7 Summaries | done | phase 7 |
| 8 UI | done | phase 8 |
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
6. Store selection: `STORE_BACKEND=auto` tries Mongo (1.5 s timeout) and falls back to `data/store/*.json`.
7. LLM access goes through `app/llm/client.py` (`OllamaClient.structured`): JSON-schema-constrained output, Pydantic
   validation, one retry with the errors fed back. Tests inject a `FakeLLM` via `set_llm`.
8. OCR uses PaddleOCR `PP-OCRv5_mobile_det/rec` by default (configurable `OCR_DET_MODEL`/`OCR_REC_MODEL`):
   ~20 s/page on this CPU vs ~60 s for the PP-OCRv6 medium default, mean confidence 0.97 vs 0.99, and it
   returns cell-level boxes (better source boxes). Set the medium models on a GPU machine.
9. Text-layer PDF pages keep PyMuPDF line boxes scaled to the 200 DPI page raster so all boxes share one coordinate
   space. Photo/scan pages are deskewed + contrast-stretched before OCR and the processed image is what is stored.
10. Document classifier: weighted keyword rules; accepted when top score ≥ 4 and margin ≥ 3, else text-LLM
    fallback, else best rule score (`rules_low_margin`). All five samples classify by rules.
11. LLM-facing schemas are flat strings ("as printed"); dates, numbers, age and sex are parsed in Python (day-first
    dates). The JSON schema sent to Ollama marks every property required (otherwise grammar-constrained decoding
    silently skips optional header fields — observed with qwen2.5:7b).
12. Extraction chain: configured mode (`vision` → `VISION_MODEL`) → `text` mode (OCR text → `TEXT_MODEL`) if the
    vision call is unavailable → deterministic rules extractor (`app/extract/rules.py`) marked low confidence.
13. Field confidence = 0.55·fuzzy match to OCR + 0.45·OCR line confidence (×0.85 after a retry, ≤0.30 for rules);
    values not found in the OCR text get a reason and go to the confirm queue (hallucination guard).
14. Synthetic ground truth for the generated samples lives in `tests/fixtures/synthetic_truth/` (emitted by
    `scripts/make_samples.py`). `samples/expected/` skeletons stay empty for hand-filling, as requested.
15. Normalization: 51 lab tests (`data/reference/lab_tests.csv`, LOINC, sex-specific adult ranges, critical limits,
    curated EN/HI plain meanings), 103 brands (`medicines.csv`, optional `medicines_extended.csv` merged). Combination
    products are reconciled per component (Ecosprin AV + Atorva → atorvastatin twice).
16. Active-medicine window for reconciliation is anchored to the patient's most recent document date
    (`RECONCILE_AS_OF=latest_document`) because uploads are usually historical; set `today` for live use.
17. FHIR: deterministic uuid5 fullUrls (patient/practitioner/organization dedupe across bundles on export);
    Observations carry canonical-unit values (printed value kept in `note` when converted); `?profile=abdm` wraps a
    bundle as an ABDM `document` Bundle with a Composition.
18. Mock ABHA numbers are 14 digits `91-XXXX-XXXX-XXXX` with a Verhoeff check digit; addresses `name1234@abdm`.
19. Summaries: the LLM writes only prose sections (what/key findings/meanings/questions). Medicines (EN + HI
    renderers), values, flags, reconciliation notes and the disclaimer are injected by code. Checks: banned phrases
    (EN+HI), number grounding, abnormal coverage, Devanagari ratio for Hindi → one regeneration → template.
    English summary is generated during upload; Hindi on first request; both cached by extraction hash.
20. Vision default switched to `qwen2.5vl:3b` at 1024 px (per the >90 s rule): on this CPU-only box qwen2.5vl:7b took
    252 s for a single prescription crop and was OOM-killed (memory cgroup) when OCR ran alongside; 3b took 201–264 s
    with F1 0.82 vs text-mode qwen2.5:7b 177 s / F1 0.78 on the handwritten prescription. Ollama runs with
    `OLLAMA_MAX_LOADED_MODELS=1`. On a GPU machine set `VISION_MODEL=qwen2.5vl:7b`.
21. `EXTRACTION_MODE=rules` and `SUMMARY_MODE=template` give a fully offline, LLM-free demo mode (fast, low
    confidence everywhere, so every field lands in the confirm queue).
22. UI: Streamlit `st.navigation` with pages in `ui/views/` (a `pages/` folder triggers Streamlit's legacy
    auto-navigation on cold direct loads). Source crops via table row selection plus a "Show where a value came
    from" picker (works on touch and is testable). Document labels are de-duplicated because Streamlit resolves
    selectbox values by label.
23. Missing document dates stay `null` (never the upload date) so historical documents never look current.
24. Medicine fields get grounded, deterministic tidy-ups after extraction: strength re-attached to the name only if
    the combined text appears verbatim in the OCR, duration-shaped "timing" moved to duration, trailing AC/PC/HS
    split from the dosage, "Reg. No." prefixes stripped. Lifted prescription F1 from 0.77–0.81 to 0.96–0.97.
25. Upload pipeline runs as a background job with a polled `status.stage`; `?sync=true` runs inline (tests, seed).

## Deviations

- None yet.

## Known issues

- On CPU-only hardware one document takes ~4–8 min end to end with the real models (vision prompt evaluation
  dominates). The UI shows per-stage progress; the seed script is the fastest way to prepare a demo.
- PaddlePaddle 3.3.1 crashes with oneDNN enabled; `enable_mkldnn=False` is set in `app/ingest/ocr.py`.

## Next step

Phase 9 — seed, eval results, README, demo script, architecture image.
