import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.extract.evaluate import Score, compare, empty
from app.extract.extract import extract
from app.extract.flatten import to_flat
from app.ingest.classify import classify
from app.ingest.ingest import ingest_file
from app.ingest.models import PageData


def predict(sample: Path, cache_dir: Path, fresh: bool, mode: str | None) -> dict:
    cache = cache_dir / f"{sample.stem}.json"
    if cache.exists() and not fresh:
        return json.loads(cache.read_text(encoding="utf-8"))
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
        "attempts": ex.meta.attempts,
        "seconds": round(time.time() - start, 1),
        "prediction": to_flat(ex),
    }
    cache.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Field-level extraction accuracy against expected JSON")
    ap.add_argument("--expected-dir", default=str(ROOT / "samples" / "expected"))
    ap.add_argument("--samples-dir", default=str(ROOT / "samples"))
    ap.add_argument("--fresh", action="store_true", help="ignore cached predictions")
    ap.add_argument("--mode", choices=["vision", "text"], default=None)
    ap.add_argument("--out", default=str(ROOT / "docs" / "eval_results.md"))
    ap.add_argument("--only", default=None, help="substring filter on sample name")
    args = ap.parse_args(argv)

    s = get_settings()
    expected_dir = Path(args.expected_dir)
    cache_dir = s.data_dir / "cache" / "eval" / (args.mode or s.extraction_mode)
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

    lines = [
        "# Extraction evaluation",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · expected: `{Path(args.expected_dir).relative_to(ROOT) if Path(args.expected_dir).is_relative_to(ROOT) else args.expected_dir}` · "
        f"mode: `{args.mode or s.extraction_mode}` · vision model: `{s.vision_model}` · text model: `{s.text_model}`",
        "",
        "Field-level scores. Precision = correct / predicted non-empty fields; recall = correct / expected non-empty fields. "
        "Numbers match within 1 %, dates after day-first parsing, strings after case/punctuation folding or fuzzy ratio ≥ 90.",
        "",
        "| Document | Type ok | Method | Expected | Predicted | Correct | Precision | Recall | F1 | Seconds |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, pred, sc, type_ok in rows:
        lines.append(f"| {name} | {'yes' if type_ok else 'no'} | {pred['method']} ({pred['model']}) | {sc.expected} | {sc.predicted} | {sc.correct} | {sc.precision:.2f} | {sc.recall:.2f} | {sc.f1:.2f} | {pred['seconds']} |")
    if rows:
        lines.append(f"| **Overall (micro)** | | | {overall.expected} | {overall.predicted} | {overall.correct} | **{overall.precision:.2f}** | **{overall.recall:.2f}** | **{overall.f1:.2f}** | |")
    if skipped:
        lines += ["", "Skipped:", ""] + [f"- `{n}` — {w}" for n, w in skipped]
    if details:
        lines += ["", "## Field errors", ""]
        for name, misses in details:
            lines.append(f"<details><summary>{name} — {len(misses)} mismatches</summary>\n")
            lines += [f"- `{m}`" for m in misses] or ["- none"]
            lines.append("\n</details>\n")
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
