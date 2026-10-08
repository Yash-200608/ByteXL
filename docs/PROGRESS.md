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
| 9 Hardening & demo | done | phase 9 |

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
25. Condition grounding in summaries (found on the first real-model run, which said "suggesting possible diabetes"
    for a lab report): LLM prose may name a disease only if the document itself states it (doctor's diagnosis /
    hospital course), or inside a value's meaning when our curated hint for that test mentions it. Added inference
    phrases ("may indicate", "suggesting", "risk of", "signs of", …) to the banned list.
26. Handwriting detection = LLM `handwritten` flag OR low OCR confidence on an OCR'd prescription, plus an explicit
    user switch (`POST /documents/{id}/handwritten`, toggle on the Document page) that forces the always-confirm rule.
    The synthetic handwriting sample is a clean italic font that both qwen2.5vl:3b and PaddleOCR read as print, so the
    seed marks it via the switch. (A real handwriting font could not be downloaded: GitHub raw fonts returned 403
    from this environment's egress policy.)
27. Summary checks extended after reviewing real outputs: hedged-inference patterns (may/might/could + indicate,
    suggest, affect, pose, show…; "indicating possible"), and month grounding (a month next to a number must match a
    date in the source; the 7B Hindi draft turned 20 Sep 2024 into "2024 मई 20").
28. **Deviation — Hindi summaries default to a deterministic Hindi composer** (`HINDI_SUMMARY_MODE=template`): curated
    Hindi meanings from `lab_tests.csv`, Hindi dosing renderer, per-type Hindi questions, same section structure,
    medicine/test names and numbers unchanged. Reason: qwen2.5:7b Hindi on this setup transliterated test names,
    mangled the lab name, translated "liver" as "लिफ्ट" and produced a wrong month. LLM Hindi (with all checks) is one
    setting away: `HINDI_SUMMARY_MODE=llm`.
29. Upload pipeline runs as a background job with a polled `status.stage`; `?sync=true` runs inline (tests, seed).
30. Windows dev machine (i5-6500, 4 cores, GT 730 2 GB, no Ollama/Mongo/Docker): `run.ps1` replaces the Makefile;
    text file I/O is explicitly UTF-8 (cp1252 default broke Hindi); default URLs use `127.0.0.1` because `localhost`
    resolves to IPv6 first on Windows and every call to an IPv4-only server waited ~2 s. `scripts/mock_ollama.py`
    stands in for Ollama there (reference answers for the bundled samples, rules extractor otherwise). PaddleOCR
    runs natively at ~30 s/page; full test suite passes (208 passed, 1 skipped).
31. First validation against the official NRCeS package (`ndhm.in#6.5.0`, HL7 `validator_cli.jar`, tx.fhir.org):
    every bundle failed (28–71 errors each). Fixed without SNOMED access:
    - Practitioner and Organization identifiers: a medical-council registration is filed as `MD` under
      `urn:bytexl:medical-council-registration` (it was wrongly under the HPR system); otherwise a local
      `OIN` identifier.
    - `Bundle.meta.versionId`; the source file is embedded in `DocumentReference` at export time (`embed_source`),
      and becomes a `Binary` in ABDM prescriptions.
    - `DiagnosticReport.resultsInterpreter` (pathologist, else lab or hospital) and a deterministic `conclusion`
      labelled "Software-computed flags, not a clinical interpretation".
    - Composition sections follow each profile's layout and fixed SNOMED section codes. Encounter diagnoses are
      linked via `Encounter.diagnosis`, with no `use`, because NRCeS fixes `use` to SNOMED.
    - The collection export no longer claims the DocumentBundle profile.
    - Observations carry the official LOINC display (new `loinc_display` column, looked up from tx.fhir.org, LOINC
      2.82); the printed name stays in `code.text`.
    Then the fixed SNOMED constants:
    - Composition.type is 440545006 Prescription record and 373942005 Discharge summary (both fixed by the
      profiles), and 4241000179101 Laboratory report (the code NRCeS's own lab example uses).
    - `DiagnosticReport.category` is 708184003 Clinical pathology service.
    - All codes were checked on tx.fhir.org.
    Result:
    - **Lab report bundles validate with 0 errors** (both exports).
    - Prescriptions have 5 errors (collection export) / 10 (ABDM export); the discharge summary 5 / 10.
    - All remaining errors are the medicine coding (`urn:bytexl:generic`, which the profile requires to be
      SNOMED CT) and the MedicationRequest profile mismatches it causes. Fixing them needs the SNOMED CT India
      Drug Extension (MLDS licence).
    - Remaining warnings are mostly best-practice: no narrative (dom-6), the local generic code system, and
      inactive SNOMED 409586006 (Complaint) on complaint Conditions.
32. Flaky summary tests on Windows were a JSON-store bug, not a summary race.
    - The atomic write `tmp.replace(path)` intermittently raised `PermissionError [WinError 5]`. Windows refuses to
      replace a file while another handle (Defender, the search indexer, or a second process such as `seed.py`
      next to the API) has it open.
    - The pipeline then failed mid-run, so whichever summary test was running saw no LLM calls.
    - `_replace_with_retry` retries up to 20 times with linear backoff (about 5 s worst case), then re-raises.
    - The fast suite went from 1 failure in 2 runs to 0 in 8.
33. PERRY assistant (`app/agent/`, `ui/views/perry.py`, `ui/perry_mascot.py`, `POST /patients/{id}/perry`).
    - Tools are bound to a patient at construction; arguments are `extra="forbid"` Pydantic models, so a model-supplied
      `patient_id` is rejected.
    - Planner: `OllamaClient.structured` with a `Plan` schema whose tool name is a Literal enum.
    - Answer: plain chat, then `check_answer`, which reuses the summary safety functions plus a PERRY-specific banned
      list, an internal-id check and a script check. One retry with feedback, then the deterministic composer.
    - Treatment-decision questions never reach the answer LLM.
    - A planner that returns no calls for a data question is overridden by the router, so PERRY never answers account
      questions without retrieving.
    - Language: Unicode script ranges plus Hinglish marker words (no new dependency).
    - Devanagari Hindi answers default to the composer (`PERRY_HINDI_MODE=template`), as with the summaries; Hinglish uses
      the LLM.
    - Other Indic scripts are detected and the LLM is asked to answer in them; the composer falls back to English with a
      note.
    - Voice is not built (P2).
    - The mascot is an original SVG with CSS states for idle, thinking and error.
    - Tests: 45 in `tests/test_perry.py`.

## Deviations

- Vision model default `qwen2.5vl:3b` instead of `qwen2.5vl:7b` (per the >90 s/page rule; see decision 20).
- Hindi summaries default to the deterministic Hindi composer instead of LLM-generated Hindi (decision 28).
- FHIR models are `fhir.resources.R4B` (R4-wire-compatible) because pure-R4 classes need Pydantic v1 (decision 3).
- Samples are synthetic (the repo had none); `samples/expected/` left empty for hand-filling; synthetic ground truth
  in `tests/fixtures/synthetic_truth/`.

## Known issues

- On CPU-only hardware one document takes ~4–8 min end to end with the real models (vision prompt evaluation
  dominates). The UI shows per-stage progress; the seed script is the fastest way to prepare a demo.
- Automatic handwriting detection is weak on neat handwriting; the user switch is the safety net.
- PaddlePaddle 3.3.1 crashes with oneDNN enabled; `enable_mkldnn=False` is set in `app/ingest/ocr.py`.

## Next step

All phases done. Remaining by hand:
1. Fill `samples/expected/*.json` for any real documents you add to `samples/`, then `make eval`.
2. Fill the hardware line in the master prompt; on a GPU set `VISION_MODEL=qwen2.5vl:7b` and rerun `make eval`.
3. Optional: try `HINDI_SUMMARY_MODE=llm` on stronger hardware and review Hindi output before demoing it.

State of the build machine at hand-off: MongoDB seeded with demo patient "Rahul Sharma" (5 documents, real-model
extraction, English LLM summaries), 209 tests passing (`.venv/bin/pytest -q`), real-model eval overall F1 0.96.
