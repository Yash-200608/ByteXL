import argparse
import json
import platform
import shlex
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from app.agent.language import detect_language
from app.config import get_settings
from app.extract.evaluate import Score, compare, empty
from app.extract.extract import extract
from app.extract.flatten import to_flat
from app.ingest.classify import classify
from app.ingest.ingest import ingest_file
from app.ingest.models import PageData
from app.normalize import normalize_extraction
from app.normalize.confirm import apply_confirmation_rules, iter_fields
from app.pipeline import _is_handwritten
from app.schemas import Prescription

LANGUAGE_FIXTURE = ROOT / "tests" / "fixtures" / "language_eval.json"
MOCK_MARKER = "mock-ollama"
NOT_EVALUATED = [
    ("Sarvam-Translate output quality (10 Indian languages)", "needs the translator model and a bilingual reviewer"),
    ("LLM-written Hindi summaries (`HINDI_SUMMARY_MODE=llm`)", "default is the deterministic Hindi composer"),
    ("Hindi / Devanagari OCR (`OCR_HINDI=true`)", "no Devanagari documents in the sample set"),
    ("Speech recognition per language (faster-whisper)", "no recorded audio in the sample set"),
]


def git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def repo_state() -> dict:
    dirty = git("status", "--porcelain", "--", ".", ":(exclude)docs/eval_results.md")
    return {"commit": git("rev-parse", "HEAD") or "unknown", "branch": git("rev-parse", "--abbrev-ref", "HEAD") or "unknown", "dirty": bool(dirty)}


def ollama_state(base_url: str, wanted: list[str]) -> dict:
    out = {"reachable": False, "version": "", "models": {}, "mock": False}
    try:
        with httpx.Client(timeout=3.0) as client:
            tags = client.get(f"{base_url}/api/tags").json().get("models", [])
            out["reachable"] = True
            try:
                out["version"] = client.get(f"{base_url}/api/version").json().get("version", "")
            except (httpx.HTTPError, ValueError):
                pass
    except (httpx.HTTPError, ValueError):
        return out
    names = [t.get("name", "") for t in tags]
    out["mock"] = any(MOCK_MARKER in n for n in names)
    for tag in tags:
        name = tag.get("name", "")
        if name in wanted:
            d = tag.get("details") or {}
            out["models"][name] = {
                "digest": (tag.get("digest") or "")[:12],
                "size": d.get("parameter_size", ""),
                "quant": d.get("quantization_level", ""),
            }
    return out


def hardware_line(override: str | None) -> str:
    if override:
        return override
    import os

    return f"{platform.system()} {platform.machine()}, {os.cpu_count()} logical CPUs, GPU not recorded"


def review_stats(ex, pages: list[PageData], marked_handwritten: bool = False) -> dict:
    copy = ex.model_copy(deep=True)
    normalize_extraction(copy, sex=None)
    queue = apply_confirmation_rules(copy, handwritten=marked_handwritten or _is_handwritten(copy, pages))
    total = sum(1 for _, f in iter_fields(copy) if f.value is not None)
    reasons: dict[str, int] = {}
    for q in queue:
        for r in q["reasons"]:
            key = r.split(":")[0].split("(")[0].strip()
            reasons[key] = reasons.get(key, 0) + 1
    return {"fields": total, "flagged": len(queue), "paths": [q["path"] for q in queue], "reasons": reasons}


def predict(sample: Path, cache_dir: Path, fresh: bool, mode: str | None) -> dict:
    cache = cache_dir / f"{sample.stem}.json"
    if cache.exists() and not fresh:
        out = json.loads(cache.read_text(encoding="utf-8"))
        out["cached"] = True
        return out
    start = time.time()
    pages_cache = cache_dir / f"{sample.stem}.pages.json"
    if pages_cache.exists() and not fresh:
        pages = [PageData(**p) for p in json.loads(pages_cache.read_text(encoding="utf-8"))]
    else:
        pages = ingest_file(sample, f"eval_{sample.stem}")
        pages_cache.write_text(json.dumps([p.model_dump() for p in pages]), encoding="utf-8")
    text = "\n".join(p.text for p in pages)
    cls = classify(text)
    ex = extract(cls.document_type, pages, mode=mode)
    out = {
        "classified_as": cls.document_type,
        "classification_method": cls.method,
        "method": ex.meta.method,
        "model": ex.meta.model,
        "low_confidence": ex.meta.low_confidence,
        "handwritten_detected": _is_handwritten(ex, pages),
        "attempts": ex.meta.attempts,
        "seconds": round(time.time() - start, 1),
        "review": review_stats(ex, pages),
        "review_marked_handwritten": review_stats(ex, pages, True) if isinstance(ex, Prescription) else None,
        "prediction": to_flat(ex),
    }
    cache.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    out["cached"] = False
    return out


def language_eval(fixture: Path = LANGUAGE_FIXTURE) -> list[tuple[str, int, int, list[str]]]:
    items = json.loads(fixture.read_text(encoding="utf-8"))["items"]
    order: list[str] = []
    stats: dict[str, list] = {}
    for item in items:
        code = item["code"]
        if code not in stats:
            order.append(code)
            stats[code] = [0, 0, []]
        got = detect_language(item["text"]).code
        stats[code][0] += 1
        if got == code:
            stats[code][1] += 1
        else:
            stats[code][2].append(f"{item['text']!r} -> {got}")
    return [(code, stats[code][0], stats[code][1], stats[code][2]) for code in order]


def pct(n: int, d: int) -> str:
    return f"{n / d:.2f}" if d else "n/a"


def field_table(overall: Score) -> list[str]:
    lines = ["| Field | Expected | Predicted | Correct | Precision | Recall |", "|---|---|---|---|---|---|"]
    for key in sorted(overall.fields):
        e, p, c = overall.fields[key]
        lines.append(f"| `{key}` | {e} | {p} | {c} | {pct(c, p)} | {pct(c, e)} |")
    return lines


def build_report(ctx: dict) -> list[str]:
    rows, overall, skipped, details = ctx["rows"], ctx["overall"], ctx["skipped"], ctx["details"]
    state, ollama, s = ctx["state"], ctx["ollama"], ctx["settings"]
    mode = ctx["mode"]
    cached = [name for name, pred, *_ in rows if pred.get("cached")]
    lines = [
        "# Extraction evaluation",
        "",
        "## Provenance",
        "",
        "| | |",
        "|---|---|",
        f"| Generated | {ctx['when']} |",
        f"| Commit | `{state['commit']}`{' (working tree had uncommitted changes)' if state['dirty'] else ''}{'' if state['branch'] == 'HEAD' else ' on `' + state['branch'] + '`'} |",
        f"| Command | `{ctx['command']}` |",
        f"| Extraction mode | `{mode}` |",
        f"| Vision model | `{s.vision_model}`{ctx['model_note'](s.vision_model)} |",
        f"| Text model | `{s.text_model}`{ctx['model_note'](s.text_model)} |",
        f"| Ollama | {ctx['ollama_note']} |",
        f"| Hardware | {ctx['hardware']} |",
        f"| Python | {platform.python_version()} |",
        f"| Predictions | {'all fresh' if not cached else 'cached from an earlier run: ' + ', '.join(cached) + ' (rerun with `--fresh`; timings are from the earlier run)'} |",
        "",
    ]
    if ollama["mock"]:
        lines += ["> **Mock Ollama was detected.** These numbers replay reference answers and are not a live model run.", ""]
    lines += [
        "## Dataset and split",
        "",
        f"- Ground truth: `{ctx['expected_label']}`; samples: `{ctx['samples_label']}`.",
        f"- Documents scored: {len(rows)}; expected fields: {overall.expected}. All documents are synthetic (fictional patient and facilities), generated by `scripts/make_samples.py`.",
        "- There is no held-out split: the five documents are also the development set (rules such as the medicine tidy-ups in `docs/PROGRESS.md` decision 24 were tuned on them), so treat the scores as in-sample.",
        "- Nothing is trained: the models are used as downloaded.",
        "",
        "## Extraction accuracy",
        "",
        "Precision = correct / predicted non-empty fields; recall = correct / expected non-empty fields. "
        "Numbers match within 1 %, dates after day-first parsing, strings after case/punctuation folding or fuzzy ratio ≥ 90.",
        "",
        "| Document | Type ok | Method | Expected | Predicted | Correct | Precision | Recall | F1 | Seconds |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, pred, sc, type_ok in rows:
        lines.append(f"| {name} | {'yes' if type_ok else 'no'} | {pred['method']} ({pred['model']}) | {sc.expected} | {sc.predicted} | {sc.correct} | {sc.precision:.2f} | {sc.recall:.2f} | {sc.f1:.2f} | {pred['seconds']} |")
    if rows:
        lines.append(f"| **Overall (micro)** | | | {overall.expected} | {overall.predicted} | {overall.correct} | **{overall.precision:.2f}** | **{overall.recall:.2f}** | **{overall.f1:.2f}** | |")
        lines += ["", "### Per-field accuracy", "", "Fields are grouped by name across documents (list items collapse to their column).", ""]
        lines += field_table(overall)

    reviewed = [(name, pred["review"], pred.get("review_marked_handwritten")) for name, pred, *_ in rows if pred.get("review")]
    lines += ["", "## Abstention / review queue", ""]
    if reviewed:
        lines += [
            "A field is *abstained on* when PERRY does not trust it and sends it to the confirm queue instead of presenting it as fact "
            "(low confidence, value not found in the page text, flag mismatch, unrecognised test or medicine, handwritten drug name or dose). "
            "Measured on the extraction before any user confirmation, with no patient profile (sex is unknown, so sex-specific ranges are not applied).",
            "",
            "The handwriting rule (every drug name and dose is confirmed) fires on the LLM's `handwritten` flag or low OCR confidence. "
            "A clean handwriting-style font is read as print and so is not detected (`docs/PROGRESS.md`, decision 26); the app's seed marks such a "
            "document with the user switch. The last column shows the queue with that switch on, for prescriptions.",
            "",
            "| Document | Extracted fields | Sent to confirm queue | Rate | Queue with handwriting switch on |",
            "|---|---|---|---|---|",
        ]
        tf = tq = tqm = 0
        for name, r, m in reviewed:
            tf += r["fields"]
            tq += r["flagged"]
            tqm += (m or r)["flagged"]
            marked = f"{m['flagged']} ({pct(m['flagged'], m['fields'])})" if m else "same"
            lines.append(f"| {name} | {r['fields']} | {r['flagged']} | {pct(r['flagged'], r['fields'])} | {marked} |")
        lines.append(f"| **Overall** | **{tf}** | **{tq}** | **{pct(tq, tf)}** | **{tqm} ({pct(tqm, tf)})** |")
        lines.append(f"\nDocuments with at least one queued field: {sum(1 for _, r, _ in reviewed if r['flagged'])} of {len(reviewed)}.")
        detected = [name for name, pred, *_ in rows if pred.get("handwritten_detected")]
        if any("handwritten_detected" in pred for _, pred, *_ in rows):
            lines.append(f"\nDetected as handwritten without the switch: {', '.join(detected) if detected else 'none'}.")
        why: dict[str, int] = {}
        for _, r, _ in reviewed:
            for k, v in (r.get("reasons") or {}).items():
                why[k] = why.get(k, 0) + v
        if why:
            lines += ["", "Reasons (a field can have several):", ""]
            lines += [f"- {k}: {v}" for k, v in sorted(why.items(), key=lambda kv: -kv[1])]
        missing = [name for name, pred, *_ in rows if not pred.get("review")]
        if missing:
            lines.append(f"\nNot recorded for {', '.join(missing)} (cached from a run that predates this metric; rerun with `--fresh`).")
    else:
        lines.append("Not recorded: every prediction came from a cache that predates this metric. Rerun with `--fresh`.")

    timed = [pred["seconds"] for _, pred, *_ in rows]
    lines += ["", "## Latency", ""]
    if timed:
        lines += [
            f"Per document, upload to validated extraction (OCR + classification + extraction; no summary or FHIR build): "
            f"median {statistics.median(timed):.1f} s, max {max(timed):.1f} s, total {sum(timed):.1f} s over {len(timed)} documents on {ctx['hardware']}.",
            "Per-document values are in the accuracy table. With `EXTRACTION_MODE=rules` there is no model call and these drop to seconds.",
        ]

    lines += ["", "## Language evaluation", ""]
    lang = ctx["language"]
    total_n = sum(n for _, n, _, _ in lang)
    total_ok = sum(k for _, _, k, _ in lang)
    lines += [
        f"Reply-language detection (`app/agent/language.py`) on {total_n} labelled questions in 13 languages, 3 per language "
        f"(`tests/fixtures/language_eval.json`). Detection uses Unicode scripts and marker words, runs on CPU in milliseconds and is also asserted in `make test`. "
        "The questions were written by the maintainers and have not been reviewed by native speakers; detection depends on script, not on phrasing.",
        "",
        "| Language | Questions | Correct | Accuracy |",
        "|---|---|---|---|",
    ]
    for code, n, k, _ in lang:
        lines.append(f"| `{code}` | {n} | {k} | {pct(k, n)} |")
    lines.append(f"| **All** | **{total_n}** | **{total_ok}** | **{pct(total_ok, total_n)}** |")
    wrong = [w for _, _, _, ws in lang for w in ws]
    if wrong:
        lines += ["", "Misdetected:", ""] + [f"- {w}" for w in wrong]
    lines += ["", "Not evaluated:", ""] + [f"- {what}: {why}." for what, why in NOT_EVALUATED]

    lines += ["", "## Reproduce", "", "```bash", "git checkout " + state["commit"], "make setup", ctx["repro"], "```"]
    if skipped:
        lines += ["", "Skipped:", ""] + [f"- `{n}` — {w}" for n, w in skipped]
    if details:
        lines += ["", "## Field errors", ""]
        for name, misses in details:
            lines.append(f"<details><summary>{name} — {len(misses)} mismatches</summary>\n")
            lines += [f"- `{m}`" for m in misses] or ["- none"]
            lines.append("\n</details>\n")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Field-level extraction accuracy against expected JSON")
    ap.add_argument("--expected-dir", default=str(ROOT / "samples" / "expected"))
    ap.add_argument("--samples-dir", default=str(ROOT / "samples"))
    ap.add_argument("--fresh", action="store_true", help="ignore cached predictions")
    ap.add_argument("--mode", choices=["vision", "text"], default=None)
    ap.add_argument("--out", default=str(ROOT / "docs" / "eval_results.md"))
    ap.add_argument("--only", default=None, help="substring filter on sample name")
    ap.add_argument("--hardware", default=None, help="free-text hardware description for the report")
    args = ap.parse_args(argv)

    s = get_settings()
    expected_dir = Path(args.expected_dir)
    mode = args.mode or s.extraction_mode
    cache_dir = s.data_dir / "cache" / "eval" / mode
    cache_dir.mkdir(parents=True, exist_ok=True)
    samples = sorted(p for p in Path(args.samples_dir).iterdir() if p.is_file() and p.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg"))
    rows, overall, skipped, details = [], Score(), [], []
    for sample in samples:
        if args.only and args.only not in sample.name:
            continue
        exp_path = expected_dir / f"{sample.stem}.json"
        if not exp_path.exists():
            skipped.append((sample.name, "no expected JSON"))
            continue
        expected = json.loads(exp_path.read_text(encoding="utf-8"))
        if empty({k: v for k, v in expected.items() if k != "document_type"}):
            skipped.append((sample.name, "expected JSON still empty"))
            continue
        pred = predict(sample, cache_dir, args.fresh, args.mode)
        score = compare(expected, pred["prediction"])
        overall.add(score)
        type_ok = pred["classified_as"] == expected.get("document_type")
        rows.append((sample.name, pred, score, type_ok))
        details.append((sample.name, score.misses))

    header = f"{'document':40} {'type':5} {'method':7} {'exp':>4} {'pred':>4} {'ok':>4} {'P':>6} {'R':>6} {'F1':>6} {'sec':>6}"
    print(header)
    print("-" * len(header))
    for name, pred, sc, type_ok in rows:
        print(f"{name:40} {'ok' if type_ok else 'BAD':5} {pred['method']:7} {sc.expected:4} {sc.predicted:4} {sc.correct:4} {sc.precision:6.2f} {sc.recall:6.2f} {sc.f1:6.2f} {pred['seconds']:6.1f}")
    if rows:
        print("-" * len(header))
        print(f"{'OVERALL (micro)':40} {'':5} {'':7} {overall.expected:4} {overall.predicted:4} {overall.correct:4} {overall.precision:6.2f} {overall.recall:6.2f} {overall.f1:6.2f}")
    for name, why in skipped:
        print(f"skipped {name}: {why}")

    wanted = [s.vision_model, s.text_model]
    ollama = ollama_state(s.ollama_url, wanted)
    if ollama["mock"]:
        print("WARNING: mock Ollama detected; these numbers are not a live model run.")

    def model_note(tag: str) -> str:
        info = ollama["models"].get(tag)
        if not info:
            return " (digest unavailable: Ollama not reachable or model not installed)"
        extra = ", ".join(x for x in (info["size"], info["quant"]) if x)
        return f" (digest `{info['digest']}`{', ' + extra if extra else ''})"

    if not ollama["reachable"]:
        ollama_note = "not reachable when the report was generated"
    else:
        ollama_note = f"{ollama['version'] or 'version unknown'}" + (" — **mock stand-in**" if ollama["mock"] else "")

    def rel(p: Path) -> str:
        return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)

    reproduce_flags = f" --expected-dir {rel(expected_dir)}" if rel(expected_dir) != "samples/expected" else ""
    if args.mode:
        reproduce_flags += f" --mode {args.mode}"
    pulls = " && ".join(f"ollama pull {m}" for m in dict.fromkeys(wanted))
    command = shlex.join(["python", "scripts/eval.py", *(argv if argv is not None else sys.argv[1:])])
    ctx = {
        "rows": rows, "overall": overall, "skipped": skipped, "details": details,
        "state": repo_state(), "ollama": ollama, "settings": s, "mode": mode,
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "command": command.strip(),
        "model_note": model_note, "ollama_note": ollama_note,
        "hardware": hardware_line(args.hardware),
        "expected_label": rel(expected_dir), "samples_label": rel(Path(args.samples_dir)),
        "language": language_eval(),
        "repro": f"{pulls}\n.venv/bin/python scripts/eval.py --fresh{reproduce_flags}",
    }
    Path(args.out).write_text("\n".join(build_report(ctx)) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
