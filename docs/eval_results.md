# Extraction evaluation

Generated 2026-10-08 08:42 UTC · expected: `tests/fixtures/synthetic_truth` · mode: `vision` · vision model: `qwen2.5vl:3b` · text model: `qwen2.5:7b`

Field-level scores. Precision = correct / predicted non-empty fields; recall = correct / expected non-empty fields. Numbers match within 1 %, dates after day-first parsing, strings after case/punctuation folding or fuzzy ratio ≥ 90.

| Document | Type ok | Method | Expected | Predicted | Correct | Precision | Recall | F1 | Seconds |
|---|---|---|---|---|---|---|---|---|---|
| discharge_summary_2024_06.pdf | yes | vision (qwen2.5vl:3b) | 52 | 53 | 48 | 0.91 | 0.92 | 0.91 | 482.1 |
| lab_report_2024_03.pdf | yes | vision (qwen2.5vl:3b) | 56 | 56 | 56 | 1.00 | 1.00 | 1.00 | 371.3 |
| lab_report_2024_09.png | yes | vision (qwen2.5vl:3b) | 48 | 48 | 47 | 0.98 | 0.98 | 0.98 | 375.4 |
| prescription_handwritten_2024_09.png | yes | vision (qwen2.5vl:3b) | 34 | 35 | 33 | 0.94 | 0.97 | 0.96 | 269.5 |
| prescription_printed_2024_03.jpg | yes | vision (qwen2.5vl:3b) | 37 | 37 | 36 | 0.97 | 0.97 | 0.97 | 268.7 |
| **Overall (micro)** | | | 227 | 229 | 220 | **0.96** | **0.97** | **0.96** | |

## Field errors

<details><summary>discharge_summary_2024_06.pdf — 6 mismatches</summary>

- `facility: expected='CITY CARE HOSPITAL' got='City Care Hospital, Shivaji Nagar, Pune 411005'`
- `attending_doctor: expected='Dr. Vikram Rao' got='Dr. Vikram Rao, MD(Medicine)'`
- `discharge_medications[ORS sachet].name: expected='ORS sachet' got='ORS sachet in 1 L water'`
- `discharge_medications[ORS sachet].timing: expected='' got='after each loose stool'`
- `discharge_medications[Cap Sporlac].timing: expected='' got='x 5 days'`
- `discharge_medications[Cap Sporlac].duration: expected='x 5 days' got=''`

</details>

<details><summary>lab_report_2024_03.pdf — 0 mismatches</summary>

- none

</details>

<details><summary>lab_report_2024_09.png — 1 mismatches</summary>

- `results[TSH].unit: expected='uIU/mL' got='ulU/mL'`

</details>

<details><summary>prescription_handwritten_2024_09.png — 2 mismatches</summary>

- `facility: expected='Mehta Family Clinic' got='Mehta Family Clinic, 4 Baner Road, Pune 411045'`
- `medications[Tab Dolo 650].timing: expected='' got='for fever'`

</details>

<details><summary>prescription_printed_2024_03.jpg — 1 mismatches</summary>

- `facility: expected='Mehta Family Clinic' got='Mehta Family Clinic, 4 Baner Road, Pune 411045'`

</details>

