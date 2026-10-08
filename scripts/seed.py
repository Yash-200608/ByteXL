import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline import create_document, run_pipeline
from app.patients import create_patient
from app.store import get_repository

ORDER = ["lab_report_2024_03", "prescription_printed_2024_03", "discharge_summary_2024_06", "lab_report_2024_09", "prescription_handwritten_2024_09"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Create a demo patient and ingest every file in samples/")
    ap.add_argument("--name", default="Rahul Sharma")
    ap.add_argument("--sex", default="male")
    ap.add_argument("--birth-year", type=int, default=1979)
    ap.add_argument("--samples", default=str(ROOT / "samples"))
    ap.add_argument("--reset", action="store_true", help="delete existing patients with the same name first")
    args = ap.parse_args(argv)

    repo = get_repository()
    if args.reset:
        for p in repo.find("patients", {"name": args.name}):
            for d in repo.find("documents", {"patient_id": p["_id"]}):
                for coll in ("bundles", "observations_index", "summaries"):
                    repo.delete_many(coll, {"document_id": d["_id"]})
            repo.delete_many("documents", {"patient_id": p["_id"]})
            repo.delete_many("patients", {"_id": p["_id"]})
    patient = create_patient(args.name, args.sex, args.birth_year)
    print(f"patient {patient['_id']}  {patient['name']}  ABHA {patient['abha_number']}  {patient['abha_address']}  (store: {repo.backend})")
    files = sorted(p for p in Path(args.samples).iterdir() if p.is_file() and p.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg"))
    files.sort(key=lambda p: ORDER.index(p.stem) if p.stem in ORDER else len(ORDER))
    for f in files:
        start = time.time()
        doc = create_document(patient["_id"], f.name, f.read_bytes())
        doc = run_pipeline(doc["_id"])
        st = doc["status"]
        method = (doc.get("extraction") or {}).get("meta", {}).get("method")
        print(f"  {f.name:40} {doc.get('document_type') or '-':18} {st['state']:7} method={method} queue={len(doc.get('confirm_queue') or [])} {time.time() - start:6.1f}s"
              + (f"  ({st.get('message')})" if st["state"] == "failed" else ""))
    print(f"done. open the UI and pick '{args.name}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
