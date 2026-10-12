# PERRY — Your Personal Health Assistant

**All your health records. One intelligent companion.**

Snap a lab report, prescription or discharge summary and PERRY gives you:
- verified structured data;
- an ABDM-ready FHIR R4 record;
- a plain-language summary in English and Hindi;
- one timeline of your health;
- a chat and voice assistant that answers questions about *your own* records in 13 languages: English, Hinglish and 11 Indian languages.

When you run it yourself, everything stays on your machine, with no cloud APIs. The hosted demo below is a different thing: see the table under it.

Built for the Altrix Labs "AI-Powered Personal Health Copilot" hackathon. The project began as **ByteXL**, and that is still
the repository, package and API name; PERRY is the product users see.

**▶ Live demo: https://bytexl-dkbehxqvatgepvl9agprgv.streamlit.app/**
`cloud demo / synthetic patient data / mock responses; not a live model run`

The hosted demo has no GPU and no LLM. Its pre-loaded records are a snapshot captured through the mock Ollama, which replays
reference answers (the stored extraction timings are 0.1–0.2 s), and anything you upload is read by the rule-based
fallbacks. It shows the product, the pipeline and the safety checks, but **none of its numbers measure a model**. The measured
results are in [Results](#results), and the live-AI version runs on your own machine.

| | Cloud demo (hosted) | Local, mock Ollama | Local, rules only | Local, live models |
|---|---|---|---|---|
| Extraction | rule-based reader | replayed reference answers for the 5 bundled samples, rules for anything else | rules | `qwen2.5vl` + OCR |
| Summaries and PERRY chat | templates and rule-based router | summaries composed from the validated JSON by code; PERRY falls back to its rule-based router | templates | `qwen2.5:7b` under safety checks |
| Data | synthetic only | yours stays local | yours stays local | yours stays local |
| Counts as a model run | no | **no** | no | yes |

Details and settings for each column are in [Modes and tested environments](#modes-and-tested-environments).

**Measured with live local models** (`qwen2.5vl:3b` + `qwen2.5:7b`, CPU only, 5 synthetic documents, no held-out split):
field-level F1 **0.96** (precision 0.96, recall 0.97, 227 fields) · document type 5 of 5 · **6 %** of extracted fields
sent to the confirm queue (9 % with the handwriting switch) · about **5 minutes per document** on 4 vCPU · reply-language
detection 39 of 39 across 13 languages. Full breakdown, model digests and the reproduce command: [Results](#results).

![PERRY answering a question, with the avatar in its Explaining state](docs/screenshots/perry_chat.jpg)

| Medications | Timeline |
|---|---|
| ![Medications page](docs/screenshots/medications.jpg) | ![Timeline page](docs/screenshots/timeline.jpg) |

## Setup (≤ 10 commands)

Requires Python 3.11 and [Ollama](https://ollama.com). MongoDB is optional; without it ByteXL stores data as JSON files automatically.

```bash
git clone https://github.com/Yash-200608/ByteXL.git && cd ByteXL
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
ollama pull qwen2.5vl:3b && ollama pull qwen2.5:7b
ollama pull hf.co/fischerman/sarvam-translate-gguf:Q4_K_S   # PERRY in 10+ Indian languages (optional, ~2.4 GB)
docker compose up -d mongo            # optional
make seed                             # demo patient + all files in samples/ (slow on CPU-only machines)
make api                              # terminal 1 → http://localhost:8000/docs
make ui                               # terminal 2 → http://localhost:8501
```

On a GPU machine set `VISION_MODEL=qwen2.5vl:7b` in `.env` for better accuracy. For an instant, LLM-free demo use
`EXTRACTION_MODE=rules SUMMARY_MODE=template make seed` (every field then lands in the confirm queue).

Other commands: `make test` (all of pytest), `make test-fast` (CPU-only, no OCR models, about 2 minutes), `make test-slow` (the OCR tests),
`make eval` (field-level accuracy, [Results](#results)), `make samples` (regenerate synthetic samples).

### Windows

`run.ps1` replaces the Makefile: `.\run.ps1 setup`, `.\run.ps1 seed`, `.\run.ps1 test`, and `.\run.ps1 demo`, which opens the API, the UI and, if Ollama is not running, the mock below in separate windows. Use `.\run.ps1 stop` to close them.

### Mock Ollama (machines that cannot run the models)

`scripts/mock_ollama.py` is a stand-in that serves Ollama's `/api/tags` and `/api/chat` on port 11434. It is **not a model**. For the five bundled samples it replays their reference answers from `tests/fixtures/synthetic_truth/`. For any other document it answers with the rules extractor. Summaries are composed from the validated JSON and still go through every safety check. OCR, normalization, FHIR and the UI all run for real. Health reports `mock-ollama:stand-in` among the installed models. Stop the mock and start real Ollama before the eval numbers or a live demo mean anything.

## Live demo and deployment

PERRY is built to run on the user's own device, so health data never leaves it. That shapes how it is shared:

- **Cloud demo (always on):** https://bytexl-dkbehxqvatgepvl9agprgv.streamlit.app/, hosted free on Streamlit Community Cloud, with the synthetic demo patient pre-loaded.
  - The entry point is `ui/cloud_app.py`. It starts the API inside the Streamlit process, copies `deploy/demo_data/` in
    on first start, and switches PERRY to its no-GPU fallbacks: rules extraction, template summaries, and the rule-based
    chat router, with all safety checks still applied.
  - Its lighter dependency list is `ui/requirements.txt`; PaddleOCR and Whisper are left out, so photo OCR and on-device
    voice recognition are off in the cloud.
  - A banner on every page explains this; the `DEMO_NOTICE` setting holds its text.
  - Deploy: on share.streamlit.io choose this repository, set the main file to `ui/cloud_app.py`, and pick Python 3.12.
  - The same cloud mode also runs as a Docker image (`Dockerfile`, port 7860) on hosts that accept Docker, including the
    full OCR stack.
- **Full version with live AI:** run PERRY on a machine with Ollama and the models (`.\run.ps1 demo`), then run
  `.\deploy\share.ps1`. It opens a public HTTPS link to that machine through Tailscale Funnel; Funnel must be allowed once
  in the Tailscale admin console. The link works while the machine is on; `.\deploy\share.ps1 -Stop` closes it.
- **Self-hosted:** `docker build -t perry . && docker run -p 7860:7860 perry`. Remove the demo `ENV` lines and set
  `OLLAMA_URL` to an Ollama server to use the real models.

Only synthetic data belongs on a public link: the app has no login, so anyone with the URL can see and upload.

## Modes and tested environments

### The four modes

| Mode | How to select it | What reads the document | Needs | Counts as a live model run |
|---|---|---|---|---|
| **Live models** (default) | `.env.example` as shipped: `EXTRACTION_MODE=vision`, `SUMMARY_MODE=llm`, `PERRY_MODE=llm` | PaddleOCR, then `VISION_MODEL` with the page image | Ollama and the model tags below | yes |
| **Mock Ollama** | same settings, with `scripts/mock_ollama.py` (or `.\run.ps1 demo`) on port 11434 | replayed reference answers for the 5 bundled samples; the rules extractor for anything else | `requirements.txt` (OCR), no models | **no**: `/health` lists `mock-ollama:stand-in`, and `scripts/eval.py` prints a warning and stamps the report |
| **Rules only** | `EXTRACTION_MODE=rules SUMMARY_MODE=template PERRY_MODE=template` | the deterministic rules extractor | `requirements.txt` (OCR), no models | no: every field lands in the confirm queue |
| **Cloud demo** | `ui/cloud_app.py` (Streamlit Cloud) or the `Dockerfile` | rules extractor, pre-loaded snapshot of mock-Ollama records | `ui/requirements.txt` | no |

Safety checks, unit normalisation, flags, FHIR and the confirm queue are the same code in every mode. Only the text-reading and
prose-writing steps change.

### Model tags used for the published results

| Role | Setting | Tag | Size | Digest (`ollama list` ID) |
|---|---|---|---|---|
| Vision extraction (default) | `VISION_MODEL` | `qwen2.5vl:3b` | 3.2 GB | `fb90415cde1e` |
| Vision extraction (GPU, optional) | `VISION_FALLBACK_MODEL` | `qwen2.5vl:7b` | about 6 GB | not recorded |
| Text: summaries, PERRY, classifier fallback | `TEXT_MODEL` | `qwen2.5:7b` | 4.7 GB | `845dbda0ea48` |
| Indian-language translation (optional) | `TRANSLATE_MODEL` | `hf.co/fischerman/sarvam-translate-gguf:Q4_K_S` | about 2.4 GB | not recorded |
| OCR | `OCR_DET_MODEL`, `OCR_REC_MODEL` | PaddleOCR 3.x `PP-OCRv5_mobile_det` / `_rec` | small, auto-downloaded | n/a |
| Speech (optional) | `STT_MODEL` | faster-whisper `small`, int8 | downloaded on first voice use | n/a |

Ollama tags can be republished, so the digest is what pins a run. Every `docs/eval_results.md` records the digests it ran with.

### Tested environments

| Environment | Python | What was run | Result |
|---|---|---|---|
| Ubuntu 24.04 container, 4 vCPU, 15 GB RAM, no GPU | 3.11 | `pip install -r ui/requirements.txt pytest`, then `pytest -m "not slow"` | 298 passed, 1 skipped |
| same | 3.12 | same | 297 passed, 1 skipped |
| same | 3.11 | full `requirements.txt`, then the whole suite including `slow` | 311 passed, 1 skipped |
| same | 3.11 | `make eval-fresh` with live `qwen2.5vl:3b` and `qwen2.5:7b` on CPU | [Results](#results) |
| Streamlit Community Cloud | 3.12 | `ui/cloud_app.py` from `ui/requirements.txt` | boots and serves the demo (`docs/PROGRESS.md`, decision 39) |
| Windows dev machine, i5-6500, 4 cores, no GPU, no Ollama | 3.11 | full suite with `run.ps1 test`, mock Ollama | 208 passed, 1 skipped when last run (decision 30); not rerun at this commit |
| GitHub Actions, `ubuntu-24.04` | 3.11 and 3.12 | `.github/workflows/ci.yml`, the same fast suite | defined here; check the Actions tab for the latest run |

Not tested: macOS, ARM, and any GPU run of `qwen2.5vl:7b`.

### CPU-only path and resources

- **Tests need no GPU, no Ollama and no OCR models.** The LLM is a fake in the tests, and the 13 tests that run PaddleOCR are marked `slow`. CI installs
  only `ui/requirements.txt` and runs `pytest -m "not slow"`; the OCR tests are a separate, manually triggered job.
- **Real inference runs on CPU too, slowly.** With the default tags, one page takes about 4–8 minutes on 4 vCPUs (vision prompt evaluation dominates);
  OCR alone is about 20 s per page. A GPU brings that to seconds.
- **Disk:** about 8 GB for the two required models (about 10 GB with the translator), plus about 2.2 GB for the Python environment with PaddleOCR
  and about 0.8 GB for the slim one used by CI and the cloud demo.
- **RAM:** 15 GB is enough for the default tags with OCR. On that machine `qwen2.5vl:7b` was killed by the memory limit when OCR ran alongside it
  (decision 20), so use it only with more RAM or a GPU. `OLLAMA_MAX_LOADED_MODELS=1` keeps a single model resident.
- **GPU:** optional. Nothing in the test suite or the published results used one.

## Architecture

![ByteXL pipeline](docs/architecture.png)

Green steps are deterministic Python, orange steps use a local LLM. The principle: **LLMs read and write words; Python decides facts.** Full design — schemas, normalization rules, FHIR mapping, Mongo collections, API contract, safety design — is in [docs/architecture.md](docs/architecture.md).

| Layer | Tech |
|---|---|
| Ingest & OCR | PyMuPDF text layer → 200 DPI raster + PaddleOCR (PP-OCRv5 mobile) with deskew/contrast |
| Extraction | Ollama `qwen2.5vl` (page image + OCR text) with JSON-schema-constrained output, Pydantic validation, one retry with error feedback, rules fallback |
| Normalization | 51 lab tests → LOINC + sex-specific ranges + unit conversion, 103 Indian brands → generics, Indian dosing grammar parser |
| Health record | FHIR R4 (`fhir.resources`, R4B wire-compatible) collection Bundle per upload, NRCeS profile tags, ABDM document-bundle export |
| Summary | `qwen2.5:7b` prose from validated JSON only, deterministic safety checks, template fallback |
| Store / API / UI | MongoDB or JSON files · FastAPI · Streamlit |

## Features

- **Upload anything common**: text PDFs, scanned PDFs, phone photos (JPG/PNG). Per-stage progress in the UI.
- **Automatic document type** (lab report / prescription / discharge summary): keyword rules with an LLM fallback.
- **Structured extraction with provenance**: every field has a confidence score and the exact box it came from on the page; tap a value to see the crop.
- **Indian prescriptions understood**: `1-0-1`, `½-0-½`, `OD/BD/TDS/QID`, `SOS`, `HS`, `AC/PC`, "empty stomach", "x 5 days", "for 1 week", "once a week", "continue" → structured schedule; brand → generic (Glycomet → metformin).
- **Lab values checked in Python**: printed reference range first, reference-table fallback by sex, mmol/L ↔ mg/dL conversion for glucose and lipids, low / normal / high / critical / unknown.
- **Confirm queue**: low-confidence fields, values not found on the page, flag mismatches, unrecognised tests/medicines, and *every* drug name and dose on handwritten prescriptions need one-tap confirmation. Edits rebuild the FHIR record, trends and summary.
- **Plain-language summary in English and Hindi** (English written by the local LLM under safety checks; Hindi composed from curated Hindi phrases by default): what the document is, key findings, out-of-range values and what they generally indicate, medicines and how to take them *as written*, questions to ask your doctor, fixed disclaimer.
- **Unified timeline and trends**: all documents chronologically; any test over time with the reference band shaded; current medicines with duplicate-medicine alerts ("Metformin appears on 2 of your documents — ask your doctor").
- **ABDM-ready**: mock ABHA number (Verhoeff-valid `91-XXXX-XXXX-XXXX`) and ABHA address on every patient, link-existing-ABHA flow, one-click FHIR export.

## The PERRY interface

- **Layout:** a dark-teal glass dashboard in three columns, with the bundled Kalam and Baloo 2 fonts (OFL), so it works offline.
  - **Sidebar:** PERRY logo; 8 pages (Chat with PERRY, My Reports, Medications, Timeline, Overview, Documents, FHIR Record,
    Pending Items, with a count badge); user card; Settings (profile switcher, model status).
  - **Header:** tagline; "Search your records…" (the search goes through PERRY's own record search); notifications for
    pending confirmations, duplicate medicines and documents still being read; "PERRY ONLINE" status.
  - **Chat panel:**
    - Welcome block and six quick actions: Latest Report, My Medicines, My Timeline, Recent Documents, Pending
      Confirmations, Compare Reports.
    - Timestamped bubbles; High / Low / Normal value tags.
    - Source cards that open the exact document in My Reports; 👍 / 👎 feedback.
    - A composer with 📎 attach and 🎙️ mic.
    - A reply-language picker (auto-detect or pick one of 13) and a **Speak with PERRY** menu for voice settings.
  - **Avatar column:** PERRY on a glowing platform with hologram panels, a speech bubble and three live state cards.
- **One avatar state machine** (`ui/perry_state.py`), driven by what is really happening:

  | State | When | On screen |
  |---|---|---|
  | Waiting | idle | arms crossed, "Ready when you are!" |
  | Listening | the mic is recording | pulsing rings |
  | Thinking | a voice question is being transcribed, or a question is being understood | `?` marks |
  | Searching | PERRY is querying your records | magnifier over a document |
  | Speaking | the browser is reading the answer aloud | sound waves |
  | Explaining | an answer was just given | hologram chart |
  | Celebrating | an upload succeeded | confetti |
  | Confused | something failed | orange alert, "let's try that again" |

  The server sets the state in the session. Listening and speaking come from the browser itself (the mic button and the
  speech engine's start/end events), so the animation matches real activity. Transitions are validated, so
  Waiting → Explaining, for example, is rejected. Animations respect `prefers-reduced-motion`.
- **Mascot art:** the PERRY images in `ui/static/perry/` are fan-art placeholders inspired by Disney's Perry the
  Platypus, used for this non-commercial hackathon demo only. Replace them before any public or commercial use.

## PERRY — the assistant

PERRY is the app's home page: a chat assistant that answers questions about the selected user's own records in English, Hindi
(Devanagari) or Hinglish, for example "What changed in my health records?", "Meri latest report samjhao", or "Which medicine was
prescribed most recently?". It lives in `app/agent/` and reuses the existing record services. It has no database of its own.

- **User-scoped tools only.** The app binds a tool set to the current user (`PerryTools(patient_id)`). The model only picks a tool name
  and its arguments, which are checked against strict schemas that reject extra fields. It can't pass or change a user ID, read
  another user's documents, or run queries, code or shell commands.
- **Tools:**
  - `get_my_overview`, `search_my_records` (fuzzy search across labs, medicines, diagnoses, documents, advice, summaries and
    confirmations)
  - `get_my_labs`, `compare_my_reports`, `get_my_medications`
  - `get_my_documents`, `get_my_timeline`, `get_my_document`, `get_my_summary`
  - `get_pending_confirmations`, `get_my_profile`
- **Loop:**
  1. The local text model plans 1–3 tool calls, with its output constrained to valid tool names.
  2. The tools run.
  3. The model writes the answer.
  4. Every answer is checked like the summaries: no numbers, months or conditions that aren't in the retrieved data, no treatment
     advice or speculation, no internal IDs, and the right language and script. A rejected answer is retried once.
- **Safety net:** if the model is unavailable or keeps failing the checks, a rule-based router and a fixed-phrase composer answer from the
  same tools in English, Hindi or Hinglish. Questions like "should I stop this medicine?" always get the fixed reply: it shows the
  medicine exactly as written and refers the decision to the doctor.
- **Indian languages:** PERRY understands and answers in Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati, Urdu,
  Kannada, Odia and Malayalam, plus Punjabi, English and Hinglish. Detection uses Unicode scripts and marker words; Marathi and
  Hindi are told apart by common words, and Urdu by Perso-Arabic script.
  - Translation runs locally with **Sarvam-Translate** (Sarvam AI, fine-tuned from Gemma 3 4B for 22 Indian languages,
    GPL-3.0), using a community GGUF build pulled through Ollama. There is no API key or extra Python package, and data stays
    on the device.
  - The question is translated to English, PERRY's normal grounded pipeline runs in English, and the checked answer is
    translated back.
  - Numbers, units, dates, medicine names, dose codes such as `1-0-1` or `BD`, lab test names and filenames are replaced
    with placeholders before translation. A line whose placeholders or digits come back changed, or that isn't in the target
    script, stays in English.
  - If the translator isn't installed, PERRY answers in English with a one-line note.
  - Model: `TRANSLATE_MODEL`. `PERRY_INDIC_MODE=translate|llm|english`; `llm` asks the text model to reply directly.
    `PERRY_HINDI_MODE=translate` uses the translator for Hindi too.
- **Voice:** tap the mic in PERRY's chat box to ask out loud. The spoken question goes through the same agent, so all of the
  account-scoping and safety rules still apply. Two speech-recognition engines, switchable under **Speak with PERRY**:
  - *On this device* (default): `faster-whisper` (`STT_MODEL=small`, int8 on CPU) transcribes the recording, which never
    leaves the machine. It takes about 5 seconds per question on a 4-core i5. Endpoints: `POST /patients/{id}/perry/transcribe`
    (transcript only, used by the UI so the avatar can show each step) and `POST /patients/{id}/perry/voice` (transcribe and
    answer in one call); both take WAV up to 60 s. Strongest in English and Hindi.
  - *Browser*: the Chrome/Edge Web Speech API, through a small built-in component. It covers more Indian languages, but the
    browser sends the audio to Google or Microsoft, and the UI says so.
  - Answers are read aloud with the browser's own voices (`speechSynthesis`, in the reply's language): automatically for
    voice questions, and on demand with 🔊 on any reply. If the browser has no voice for that language, PERRY stays silent
    rather than reading in the wrong language.
  - **Indian accent:**
    - PERRY ranks the browser's voices for each reply language: an exact `-IN` locale first (e.g. `en-IN`, `hi-IN`),
      then natural or neural voices, then known Indian voice names such as Neerja, Prabhat, Swara, Madhur and Heera.
    - **Speak with PERRY** has a voice picker, speed and pitch, a "Hear PERRY" preview, and a toggle for online natural voices,
      which are on by default. Edge sends their text to Microsoft, and Chrome to Google.
    - Before speaking, text is rewritten for natural pronunciation: units in words ("mg/dL" → "milligrams per decilitre"),
      dates, Tab → Tablet, dose codes spelled out, `0-1-0` read as numbers.
    - For an offline Indian voice on Windows: Settings → Time & language → Speech → Add voices → English (India) and Hindi.
  - **Understanding Indian accents:** Whisper is primed with the current user's own medicine and test names. Near-miss
    words, such as "raziovas", are then snapped to those names ("Rosuvas"), and only to those. The UI shows each correction.
- **Settings:** `PERRY_MODE=llm|template`; `PERRY_HINDI_MODE=template|llm` controls Devanagari replies (template by default, for the same
  reason as the summaries).
- **Reply language:** auto-detected from the question by default; the composer's language picker overrides it (the
  `language` field, one of `en`, `hinglish` and the 11 Indian language codes). An unknown code is rejected with 422.
- **API:** `POST /patients/{id}/perry` with `{"message": "...", "history": [...], "language": null}`. Each source in the
  reply carries its `document_id`, so the UI can open that record. `POST /patients/{id}/perry/feedback` stores 👍 / 👎 in
  `perry_feedback`. The patient in the path stands in for the logged-in
  user: ByteXL has no login, so the selected patient is treated as the current user.

## Medical safety approach

1. **No LLM decides a fact.** Abnormal flags, units, ranges, dosing schedules, generic names and duplicate-medicine alerts are deterministic and unit-tested.
2. **Summaries come only from validated, normalized JSON** — never from images or raw OCR text.
3. **The LLM only writes prose.** Values, flags, medicine instructions, reconciliation notes and the disclaimer are inserted by code.
4. **Output policing**: no disease may be named unless the document itself states it; banned phrases in English and Hindi ("you have", "may indicate", "stop taking", "increase your dose", "cured", "guaranteed", "दवा बंद करें", …), every number and month must exist in the source data, every abnormal value must be covered, Hindi must be Devanagari. One regeneration, then a deterministic template.
5. **Fixed disclaimer** on every summary (EN + HI): not a diagnosis, do not start/stop/change any medicine, talk to your doctor.
   Real example from this repo's seed run: the first draft for the March lab report said *"Fasting blood sugar and HbA1c are high, suggesting possible diabetes or pre-diabetes"*; the checker rejected it (inference phrase + condition not stated in the document) and the regenerated, accepted line reads *"Fasting blood sugar and HbA1c are high."*
6. **Hallucination guard**: an extracted value that cannot be found in the OCR text gets low confidence and goes to the confirm queue; handwritten drug names and doses are always confirmed.

## ABDM readiness

- FHIR R4 resources: Patient (ABHA number + address identifiers), Practitioner (registration no.), Organization, Encounter (AMB/IMP), DiagnosticReport, Observation (LOINC, UCUM, referenceRange, interpretation), MedicationRequest (dosageInstruction.timing with EventTiming codes, boundsDuration, asNeeded), Condition, DocumentReference.
- `meta.profile` points at NRCeS ABDM profiles; `GET /documents/{id}/fhir?profile=abdm` wraps a bundle as an ABDM `document` Bundle with a Composition (DiagnosticReportRecord / PrescriptionRecord / DischargeSummaryRecord).
- Deterministic resource ids let `GET /patients/{id}/export` merge all records with one Patient and de-duplicated practitioners/organizations.
- Mongo collections: `patients`, `documents`, `bundles`, `observations_index`, `summaries` (see architecture §5).

## Results

The full report, with per-field accuracy, every field error, model digests and the exact command, is
[docs/eval_results.md](docs/eval_results.md). It is written by `scripts/eval.py`, which stamps the commit, the Ollama
version, each model's digest and the hardware into the report, and warns if the mock Ollama answered.

**Setup:** live local models through Ollama 0.12.6 (`qwen2.5vl:3b` digest `fb90415cde1e` at 1024 px; `qwen2.5:7b` digest
`845dbda0ea48`), PaddleOCR `PP-OCRv5_mobile`, Python 3.11, Ubuntu 24.04 container with 4 vCPU, 15 GB RAM and no GPU.

**Data and split:** the five bundled documents, all synthetic (fictional patient and facilities), generated with their ground
truth by `scripts/make_samples.py` (`tests/fixtures/synthetic_truth/`). There is no held-out split. The same five documents
were used while building the rules, for example the medicine tidy-ups in decision 24 of `docs/PROGRESS.md`. Treat these
numbers as in-sample: real photos and real handwriting will score lower.

### Extraction accuracy (field level)

| Document | Path | Fields | Precision | Recall | F1 | Time |
|---|---|---|---|---|---|---|
| Lab report, text PDF | text layer | 56 | 1.00 | 1.00 | 1.00 | 297 s |
| Lab report, phone photo (skewed) | OCR | 48 | 0.98 | 0.98 | 0.98 | 299 s |
| Discharge summary, scanned PDF | OCR | 52 | 0.92 | 0.94 | 0.93 | 339 s |
| Prescription, printed photo | OCR | 37 | 0.97 | 0.97 | 0.97 | 274 s |
| Prescription, handwriting-style | OCR | 34 | 0.91 | 0.94 | 0.93 | 261 s |
| **Overall (micro)** | | **227** | **0.96** | **0.97** | **0.96** | |

Document type was classified correctly for all five. Most errors are the facility name picked up with its address (2 of 5
correct), the attending doctor picked up with a degree suffix, timing text that belongs in another column, and one discharge
medicine name that kept its instructions ("ORS sachet in 1 L water"). Lab values, units and ranges, and every prescription
medicine field, are 95–100 % correct. Two full runs (commits `54e4f8a` and `0aa2660`, same extraction code) gave identical overall counts: 220 correct of 229 predicted
and 227 expected.

### Abstention: what goes to the confirm queue

| Document | Extracted fields | Sent to confirm queue | With handwriting switch on |
|---|---|---|---|
| Lab report, text PDF | 64 | 0 | |
| Lab report, phone photo | 57 | 2 | |
| Discharge summary | 63 | 2 | |
| Prescription, printed photo | 42 | 11 | 11 |
| Prescription, handwriting-style | 40 | 0 | 10 |
| **Overall** | **266** | **15 (6 %)** | **25 (9 %)** |

- **The vision model flagged the printed prescription photo as handwritten.** Its OCR confidence was 0.93, above the 0.90
  threshold, so the flag came from the model. As a result, every drug name and dose on it went to the queue. The error is in
  the safe direction: PERRY asks for more confirmation, not less.
- **The handwriting-style sample was not detected,** because the font is clean enough to read as print (decision 26). In the
  app, the user switch (or `make seed`) marks it, and then all 10 of its drug-name and dose fields are queued; that is the
  last column.
- These counts are for the extraction before the user confirms anything, with no patient profile.

### Latency

Upload to validated extraction (OCR, classification and vision extraction; no summary): median **297 s**, maximum 339 s per
document, on CPU only. OCR alone is about 20 s per page; the vision model's prompt evaluation takes the rest. On a GPU this is
seconds. In rules-only mode only OCR remains: under a second for a text PDF, about 20 s for a photographed page.

### Languages

| What | Result |
|---|---|
| Reply-language detection: 13 languages × 3 questions (`tests/fixtures/language_eval.json`) | 39 / 39; also asserted in `make test` |
| Sarvam-Translate output quality, LLM-written Hindi, Devanagari OCR, speech recognition per language | **not evaluated**: they need the translator model, a bilingual reviewer, Devanagari documents or recorded audio |

The detection questions were written by the maintainers and have not been checked by native speakers. Detection uses the
script and marker words, so it does not depend on fluent phrasing.

### Reproduce

```bash
git checkout <commit in docs/eval_results.md>
make setup
ollama pull qwen2.5vl:3b && ollama pull qwen2.5:7b
make eval-fresh          # = scripts/eval.py --fresh --expected-dir tests/fixtures/synthetic_truth; about 25 min on 4 vCPU
```

`make eval` reuses cached predictions from `data/cache/eval/` (the report says so); `--fresh` re-runs OCR and the models. To
score your own documents, fill `samples/expected/*.json` and run `make eval EVAL_TRUTH=samples/expected`.

## API

Interactive docs at `http://localhost:8000/docs`. Main endpoints: `POST /patients`, `POST /patients/{id}/abha/link`, `POST /patients/{id}/documents`, `GET /documents/{id}`, `GET /documents/{id}/fhir`, `GET /documents/{id}/summary?lang=en|hi`, `POST /documents/{id}/confirm`, `GET /patients/{id}/timeline`, `GET /patients/{id}/trends/{loinc}`, `GET /patients/{id}/medications`, `GET /patients/{id}/overview`, `GET /patients/{id}/export`, `POST /patients/{id}/perry`,
`POST /patients/{id}/perry/transcribe`, `POST /patients/{id}/perry/voice`, `POST /patients/{id}/perry/feedback`, `GET /health`.

## Limitations

- **Speed on CPU-only machines**: with no GPU, one page takes ~4–8 minutes (vision prompt evaluation dominates); on a GPU it is seconds. OCR alone is ~20 s/page on CPU.
- Samples are synthetic (fictional patient and facilities); real-world handwriting is far harder than the handwriting-style font used here.
- Adult reference ranges only; paediatric and pregnancy ranges are out of scope (the printed range is used if present, otherwise the flag is "unknown").
- Lab table has 51 tests and the brand table 103 brands; unknown items are kept as written and sent to the confirm queue. A larger `data/reference/medicines_extended.csv` is merged automatically.
- ABHA numbers are mock values; there is no real ABDM gateway integration (consent, HIP/HIU flows).
- FHIR uses the R4B Python models, which are wire-compatible with R4 for the resources used. Against the official NRCeS
  package (`ndhm.in#6.5.0`, HL7 validator), lab report bundles validate with 0 errors. Prescriptions and discharge
  summaries still have 5–10 errors, all from medicine coding: the profile requires SNOMED CT drug codes, which need the
  licensed SNOMED CT India Drug Extension (see `docs/PROGRESS.md`, decision 31).
- The UI is designed for desktop and laptop screens. Tablet and phone layouts exist but have not been fully checked.
- Hindi summaries use a deterministic Hindi composer by default (curated phrases, same structure) because the 7B model's Hindi was unreliable on test hardware; set `HINDI_SUMMARY_MODE=llm` to have the LLM write Hindi under the same safety checks.
- Hindi OCR (Devanagari) is optional (`OCR_HINDI=true`) and was not part of the evaluated samples.
