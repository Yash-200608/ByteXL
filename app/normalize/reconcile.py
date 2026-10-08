from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.config import get_settings
from app.normalize.dosing import total_days
from app.schemas import MedicationItem

DOC_LABEL = {"prescription": "prescription", "discharge_summary": "discharge summary", "lab_report": "lab report"}
DOC_LABEL_HI = {"prescription": "पर्चा", "discharge_summary": "डिस्चार्ज सारांश", "lab_report": "लैब रिपोर्ट"}


@dataclass
class MedEntry:
    document_id: str
    document_type: str
    document_date: date | None
    item: MedicationItem
    index: int = 0

    @property
    def components(self) -> list[str]:
        n = self.item.normalized
        if not n or not n.generic:
            return []
        return [c.strip() for c in n.generic.split("+") if c.strip()]

    @property
    def label(self) -> str:
        return self.item.name.value or (self.item.normalized.generic if self.item.normalized else "") or "medicine"


@dataclass
class ReconciliationNote:
    generic: str
    entries: list[MedEntry] = field(default_factory=list)

    def text(self, lang: str = "en") -> str:
        parts = []
        for e in self.entries:
            when = e.document_date.strftime("%d %b %Y") if e.document_date else ("तारीख नहीं" if lang == "hi" else "undated")
            kind = (DOC_LABEL_HI if lang == "hi" else DOC_LABEL).get(e.document_type, e.document_type)
            parts.append(f"{e.label} — {kind}, {when}")
        n = len({e.document_id for e in self.entries})
        if lang == "hi":
            where = f"आपके {n} दस्तावेज़ों में" if n > 1 else "एक ही दस्तावेज़ में दो बार"
            return f"{self.generic} {where} है ({'; '.join(parts)})। कृपया अपने डॉक्टर से पूछें कि क्या ये सभी साथ में लेनी हैं।"
        where = f"appears on {n} of your documents" if n > 1 else "appears twice on the same document"
        return f"{self.generic.capitalize()} {where} ({'; '.join(parts)}). Please ask your doctor whether all of these should be taken together."

    def to_dict(self) -> dict:
        return {
            "generic": self.generic,
            "documents": sorted({e.document_id for e in self.entries}),
            "medicines": [{"name": e.label, "document_id": e.document_id, "date": e.document_date.isoformat() if e.document_date else None} for e in self.entries],
            "text": self.text("en"),
            "text_hi": self.text("hi"),
        }


def is_active(entry: MedEntry, as_of: date) -> bool:
    start = entry.document_date
    n = entry.item.normalized
    if start is None or start > as_of:
        return start is None
    dosage = n.dosage if n else None
    if dosage and dosage.continue_indefinitely:
        return True
    days = total_days(dosage) if dosage else None
    if days is not None:
        return start + timedelta(days=days) >= as_of
    return start >= as_of - timedelta(days=get_settings().active_med_default_days)


def active_medications(entries: list[MedEntry], as_of: date) -> list[MedEntry]:
    return [e for e in entries if is_active(e, as_of)]


def reconcile(entries: list[MedEntry], as_of: date) -> list[ReconciliationNote]:
    groups: dict[str, list[MedEntry]] = defaultdict(list)
    for e in active_medications(entries, as_of):
        for comp in e.components:
            groups[comp].append(e)
    notes = []
    for generic, items in sorted(groups.items()):
        if len(items) > 1:
            notes.append(ReconciliationNote(generic=generic, entries=items))
    return notes
