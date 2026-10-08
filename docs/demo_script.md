# ByteXL — 3-minute demo script

**Before the demo** (do this an hour ahead on CPU-only machines):

```bash
make seed      # creates "Rahul Sharma" and ingests all 5 samples with the real models
make api       # terminal 1
make ui        # terminal 2 → http://localhost:8501, pick "Rahul Sharma" in the sidebar
```

Keep `samples/lab_report_2024_03.pdf` ready for the live upload (text-layer PDF: OCR is instant, so only extraction runs live). If the machine has no GPU, start the live upload at 0:00 and come back to it at 2:15, or run the backup with `EXTRACTION_MODE=rules`.

Judging weights: extraction accuracy + summary quality 35 · architecture + ABDM schema 25 · UX 20 · medical safety 10 · demo 10.

| Time | Click / action | Say | Criterion |
|---|---|---|---|
| 0:00–0:15 | Open **Upload**. Point at the patient header. | "ByteXL turns any medical paper into a verified, explained, ABDM-ready health record — fully local, no cloud APIs. Every patient gets an ABHA number and address; this one is a mock with a valid check digit." | Demo, ABDM |
| 0:15–0:30 | Drag `lab_report_2024_03.pdf` into the uploader → **Process document**. | "Each stage shows live: OCR, document-type detection, extraction by a local vision model, normalization, FHIR, summary." | UX |
| 0:30–1:05 | Sidebar → **Document**, pick *Lab report · 2024-09-20* (the photographed report). Choose *HbA1c: 6.6 %* in **Show where a value came from**. | "Every field carries a confidence score and the exact box it came from on the page — here's the crop. Flags like 'High' are computed in Python from the printed range or our LOINC reference table with unit conversion, never by the LLM." | Extraction accuracy, safety |
| 1:05–1:30 | Scroll to **Plain-language summary**, toggle **हिंदी**, then back to English. | "Summaries are written only from validated JSON. The model writes prose; values, medicines and the disclaimer are inserted by code. A filter blocks phrases like 'you have' or 'stop taking', checks every number exists in the source, and every abnormal value is covered — otherwise it regenerates once, then falls back to a template. Hindi is generated natively; medicine names and numbers stay unchanged." | Summary quality, safety |
| 1:30–1:55 | Sidebar → **Confirm**, pick the handwritten prescription. Tap **✓ Accept** on *Tab Dolo 650 · Medicine*; edit one dosage and **Save edit**. | "Handwritten drug names and doses always need a human tap. Edits rebuild the FHIR bundle, the trends index and the summary instantly." | Safety, UX |
| 1:55–2:20 | Sidebar → **Timeline**. Point at **Current medicines** and the red alert. Then filter pills to *Lab report*. | "One timeline across labs, prescriptions and a hospital stay. Prescriptions in 1-0-1 / BD / SOS grammar are parsed into schedules. ByteXL noticed metformin on both the discharge summary and the new prescription — it never tells you to stop anything, it says: ask your doctor." | UX, extraction |
| 2:20–2:40 | Sidebar → **Trends**, choose *HbA1c*. | "Values from different labs are normalized to one unit and plotted against the reference band." | UX |
| 2:40–2:55 | Header → **Prepare FHIR export** → **Download FHIR Bundle**; open `http://localhost:8000/docs` → `GET /documents/{id}/fhir?profile=abdm`. | "Every upload is a FHIR R4 bundle with LOINC-coded Observations, MedicationRequests with timing, Conditions and a DocumentReference, tagged with NRCeS profiles; the ABDM profile wraps it as a document bundle with a Composition, ready for an ABHA-linked exchange." | Architecture + ABDM |
| 2:55–3:00 | Back to **Upload**: show the live upload finished. | "Local models, verified data, safe explanations. That's ByteXL." | Demo |

**Backup answers**

- *Accuracy?* Show `docs/eval_results.md` — field-level precision/recall per document against ground truth.
- *What if the model is down?* `/health` shows it; uploads still OCR and fall back to a deterministic reader with every field queued for confirmation.
- *Does the safety filter ever fire?* Yes — on the seed run the model's first draft said "suggesting possible diabetes"; it was rejected and regenerated as "Fasting blood sugar and HbA1c are high." (`summaries` collection keeps the rejection reasons in `errors`).
- *Hallucinations?* Any value not found in the OCR text drops to low confidence and goes to the confirm queue.
