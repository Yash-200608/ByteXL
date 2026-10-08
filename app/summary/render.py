from app.normalize.dosing import describe
from app.schemas import Dosage

HI_WHEN = {
    "AC": "खाने से पहले", "PC": "खाने के बाद", "ACM": "नाश्ते से पहले", "PCM": "नाश्ते के बाद", "ACD": "दोपहर के खाने से पहले",
    "PCD": "दोपहर के खाने के बाद", "ACV": "रात के खाने से पहले", "PCV": "रात के खाने के बाद", "HS": "सोते समय",
}
HI_UNIT = {"tsp": "चम्मच", "tbsp": "बड़ा चम्मच", "mL": "mL", "tablet": "गोली", "capsule": "कैप्सूल", "puff": "पफ", "drop": "बूंद",
           "unit": "यूनिट", "sachet": "पाउच"}


def _fmt(n: float) -> str:
    return "½" if n == 0.5 else f"{n:g}"


def describe_hi(d: Dosage) -> str:
    bits = []
    unit = f" {HI_UNIT.get(d.dose_unit, d.dose_unit)}" if d.dose_unit else ""
    night_label = "सोते समय" if "HS" in d.when else "रात"
    slots = [("सुबह", d.morning), ("दोपहर", d.afternoon), ("शाम", d.evening), (night_label, d.night)]
    if d.single_dose:
        bits.append("केवल एक खुराक")
    elif any(v for _, v in slots) and d.period_unit == "d" and d.period == 1:
        bits.append(", ".join(f"{label} {_fmt(v)}{unit}" for label, v in slots if v))
    elif d.frequency:
        unit_word = {"d": "दिन", "wk": "हफ्ते", "mo": "महीने", "h": "घंटे"}[d.period_unit]
        times = {1: "एक बार", 2: "दो बार", 3: "तीन बार", 4: "चार बार"}.get(d.frequency, f"{d.frequency} बार")
        bits.append(f"हर {_fmt(d.period)} {unit_word} में {times}" if d.period != 1 else f"{unit_word} में {times}")
    if d.dose_quantity and not any(v for _, v in slots) and not d.single_dose:
        bits.insert(0, f"{_fmt(d.dose_quantity)}{unit}")
    if d.as_needed:
        bits.append("केवल ज़रूरत होने पर")
    food = [HI_WHEN[w] for w in d.when if w in HI_WHEN and not (w == "HS" and d.night)]
    if food:
        bits.append(", ".join(food))
    if d.duration_value:
        u = {"d": "दिन", "wk": "हफ्ते", "mo": "महीने"}[d.duration_unit]
        bits.append(f"{_fmt(d.duration_value)} {u} तक")
    if d.continue_indefinitely:
        bits.append("डॉक्टर के अगले निर्देश तक जारी")
    return " · ".join(bits)


def how_to_take(d: Dosage | None, lang: str) -> str:
    if d is None:
        return ""
    return describe_hi(d) if lang == "hi" else (d.text or describe(d))


FLAG_WORD = {
    "en": {"low": "Low", "high": "High", "critical": "Far outside range", "normal": "Normal", "unknown": "No range"},
    "hi": {"low": "कम", "high": "अधिक", "critical": "सीमा से बहुत बाहर", "normal": "सामान्य", "unknown": "सीमा उपलब्ध नहीं"},
}

HEADINGS = {
    "en": {
        "what": "What this document is", "findings": "Key findings", "out": "Values outside the reference range",
        "meds": "Medicines and how to take them (as written)", "questions": "Questions to ask your doctor", "notes": "Please note",
        "disclaimer": "Disclaimer", "none_out": "No values were outside the reference range.", "as_written": "as written",
    },
    "hi": {
        "what": "यह दस्तावेज़ क्या है", "findings": "मुख्य बातें", "out": "सामान्य सीमा से बाहर के मान",
        "meds": "दवाएं और उन्हें कैसे लेना है (जैसा लिखा है)", "questions": "अपने डॉक्टर से पूछने के लिए सवाल", "notes": "कृपया ध्यान दें",
        "disclaimer": "अस्वीकरण", "none_out": "कोई भी मान सामान्य सीमा से बाहर नहीं है।", "as_written": "जैसा लिखा है",
    },
}


def to_markdown(summary: dict, lang: str) -> str:
    h = HEADINGS[lang]
    lines = [f"### {h['what']}", summary["what_this_is"], ""]
    if summary.get("key_findings"):
        lines += [f"### {h['findings']}"] + [f"- {k}" for k in summary["key_findings"]] + [""]
    if summary.get("has_results"):
        lines.append(f"### {h['out']}")
        if summary.get("out_of_range"):
            for o in summary["out_of_range"]:
                flag = FLAG_WORD[lang].get(o["flag"], o["flag"])
                rng = f" ({o['range']})" if o.get("range") else ""
                lines.append(f"- **{o['name']}: {o['value']}** — {flag}{rng}. {o['meaning']}")
        else:
            lines.append(h["none_out"])
        lines.append("")
    if summary.get("medicines"):
        lines.append(f"### {h['meds']}")
        for m in summary["medicines"]:
            generic = f" ({m['generic']})" if m.get("generic") else ""
            written = f" — _{h['as_written']}: {m['as_written']}_" if m.get("as_written") else ""
            lines.append(f"- **{m['name']}**{generic}: {m['how_to_take']}{written}")
        lines.append("")
    if summary.get("questions"):
        lines += [f"### {h['questions']}"] + [f"- {q}" for q in summary["questions"]] + [""]
    if summary.get("notes"):
        lines += [f"### {h['notes']}"] + [f"- {n}" for n in summary["notes"]] + [""]
    lines += [f"> **{h['disclaimer']}:** {summary['disclaimer']}"]
    return "\n".join(lines)
