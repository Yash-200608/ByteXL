from datetime import date

import pytest

from app.normalize import normalize_extraction
from app.normalize.confirm import apply_confirmation_rules, get_field
from app.normalize.dosing import parse_dosage, total_days
from app.normalize.labs import classify_value, load_lab_reference, normalize_lab, parse_range, resolve_lab
from app.normalize.medicines import load_medicines, resolve_medicine
from app.normalize.reconcile import MedEntry, is_active, reconcile
from app.normalize.units import convert, mgdl_to_mmol, mmol_to_mgdl, normalize_unit
from app.schemas import Field, LabReport, LabResult, MedicationItem, Prescription


def F(v, conf=0.95):
    return Field(value=v, confidence=conf)


def lab(name, value, unit="", rng="", flag=""):
    return LabResult(test_name=F(name), value=F(value), unit=F(unit), reference_range=F(rng), printed_flag=F(flag or None))


def med(name, dosage="", timing="", duration=""):
    return MedicationItem(name=F(name), dosage=F(dosage or None), timing=F(timing or None), duration=F(duration or None))



@pytest.mark.parametrize("sig,m,a,n,freq", [
    ("1-0-1", 1, 0, 1, 2), ("1-1-1", 1, 1, 1, 3), ("0-0-1", 0, 0, 1, 1), ("1-0-0", 1, 0, 0, 1), ("0-1-0", 0, 1, 0, 1),
    ("2-0-2", 2, 0, 2, 2), ("½-0-½", 0.5, 0, 0.5, 2), ("1/2-0-1/2", 0.5, 0, 0.5, 2), ("1 - 0 - 1", 1, 0, 1, 2),
    ("1–0–1", 1, 0, 1, 2),
])
def test_slot_patterns(sig, m, a, n, freq):
    d = parse_dosage(sig)
    assert (d.morning, d.afternoon, d.night, d.frequency) == (m, a, n, freq)
    assert not d.conflicts and not d.unparsed


def test_four_slots():
    d = parse_dosage("1-1-1-1")
    assert d.frequency == 4 and d.evening == 1 and d.when[:4] == ["MORN", "AFT", "EVE", "NIGHT"]


@pytest.mark.parametrize("sig,freq,slots", [
    ("OD", 1, (0, 0, 0)), ("once daily", 1, (0, 0, 0)), ("BD", 2, (1, 0, 1)), ("BID", 2, (1, 0, 1)), ("twice daily", 2, (1, 0, 1)),
    ("TDS", 3, (1, 1, 1)), ("TID", 3, (1, 1, 1)), ("thrice daily", 3, (1, 1, 1)), ("QID", 4, (0, 0, 0)), ("qds", 4, (0, 0, 0)),
    ("8 hourly", 3, (1, 1, 1)),
])
def test_abbreviations(sig, freq, slots):
    d = parse_dosage(sig)
    assert d.frequency == freq
    assert (d.morning, d.afternoon, d.night) == slots


def test_sos_prn():
    for sig in ("SOS", "PRN", "as needed", "when required", "s.o.s"):
        d = parse_dosage(sig)
        assert d.as_needed, sig
    assert "only when needed" in parse_dosage("SOS").text


def test_hs_bedtime():
    d = parse_dosage("HS")
    assert d.night == 1 and d.frequency == 1 and "HS" in d.when
    assert parse_dosage("0-0-1", "at bedtime").text.startswith("1 at bedtime")


@pytest.mark.parametrize("timing,code", [
    ("AC", "AC"), ("before food", "AC"), ("before meals", "AC"), ("PC", "PC"), ("after food", "PC"), ("after meals", "PC"),
    ("before breakfast", "ACM"), ("empty stomach", "ACM"), ("after breakfast", "PCM"), ("after dinner", "PCV"),
])
def test_meal_timing(timing, code):
    assert code in parse_dosage("OD", timing).when


def test_specific_timing_replaces_generic():
    d = parse_dosage("1-0-0", "before breakfast")
    assert "ACM" in d.when and "AC" not in d.when


@pytest.mark.parametrize("dur,value,unit", [
    ("x 5 days", 5, "d"), ("x5d", 5, "d"), ("for 5 days", 5, "d"), ("5 days", 5, "d"), ("for 1 week", 1, "wk"),
    ("x 2 wks", 2, "wk"), ("x 8 weeks", 8, "wk"), ("x 1 month", 1, "mo"), ("for 3 months", 3, "mo"), ("for one week", 1, "wk"),
    ("x 6 wks", 6, "wk"), ("× 10 days", 10, "d"),
])
def test_durations(dur, value, unit):
    d = parse_dosage("1-0-1", dur)
    assert (d.duration_value, d.duration_unit) == (value, unit)


def test_total_days():
    assert total_days(parse_dosage("x 2 wks")) == 14
    assert total_days(parse_dosage("x 1 month")) == 30
    assert total_days(parse_dosage("OD")) is None


def test_weekly_and_alternate():
    d = parse_dosage("once a week", "after food", "x 8 weeks")
    assert d.frequency == 1 and d.period_unit == "wk" and d.duration_value == 8
    assert d.text == "once a week · after food · for 8 weeks"
    d = parse_dosage("alternate day")
    assert d.period == 2 and d.frequency == 1


def test_continue_and_stat():
    assert parse_dosage("1-0-1", "continue").continue_indefinitely
    assert parse_dosage("(continue)").continue_indefinitely
    assert parse_dosage("stat").single_dose


def test_conflict_detected():
    d = parse_dosage("1-0-1 TDS")
    assert d.conflicts
    assert not parse_dosage("1-0-1 BD").conflicts
    assert not parse_dosage("1-0-1 daily").conflicts


def test_quantity():
    d = parse_dosage("2 tsp TDS")
    assert d.dose_quantity == 2 and d.dose_unit == "tsp" and d.morning == 2
    assert parse_dosage("10 units before breakfast").text == "10 units in the morning · before breakfast"


def test_unparsed_reported():
    assert parse_dosage("1-0-1 xyzzy").unparsed == ["xyzzy"]


def test_full_sentences():
    assert parse_dosage("1-0-1", "after food", "x 30 days").text == "1 in the morning, 1 at night · after food · for 30 days"
    assert parse_dosage("OD", "AC", "x 14 days").text == "once a day · before food · for 14 days"



def test_unit_normalization():
    assert normalize_unit("mg/dl") == "mg/dL"
    assert normalize_unit("gm%") == "g/dL"
    assert normalize_unit("uIU/ml") == "µIU/mL"
    assert normalize_unit("mIU/L") == "µIU/mL"
    assert normalize_unit("ulU/mL") == "µIU/mL"
    assert normalize_unit("lakh/cumm") == "lakh/µL"
    assert normalize_unit("/cumm") == "/µL"
    assert normalize_unit("mill/cumm") == "10^6/µL"
    assert normalize_unit("umol/L") == "µmol/L"
    assert normalize_unit("") is None


def test_glucose_conversion():
    assert convert(7.0, "mmol/L", "mg/dL", "1558-6") == pytest.approx(126.1, abs=0.1)
    assert convert(126, "mg/dL", "mmol/L", "1558-6") == pytest.approx(6.99, abs=0.01)
    assert mmol_to_mgdl(5.5, "glucose") == pytest.approx(99.1, abs=0.1)
    assert mgdl_to_mmol(180, "glucose") == pytest.approx(9.99, abs=0.01)


def test_cholesterol_conversion():
    assert convert(5.17, "mmol/L", "mg/dL", "2093-3") == pytest.approx(199.9, abs=0.1)
    assert convert(200, "mg/dL", "mmol/L", "13457-7") == pytest.approx(5.17, abs=0.01)
    assert convert(1.7, "mmol/L", "mg/dL", "2571-8") == pytest.approx(150.6, abs=0.1)


def test_other_conversions():
    assert convert(88.42, "µmol/L", "mg/dL", "2160-0") == pytest.approx(1.0)
    assert convert(120, "g/L", "g/dL") == pytest.approx(12.0)
    assert convert(2.4, "lakh/µL", "/µL") == pytest.approx(240000)
    assert convert(7.8, "10^3/µL", "/µL") == pytest.approx(7800)
    assert convert(75, "nmol/L", "ng/mL", "62292-8") == pytest.approx(30.05, abs=0.05)
    assert convert(5, "mmol/L", "mg/dL", "718-7") is None
    assert convert(5, "furlongs", "mg/dL") is None



def test_reference_table_size_and_loinc():
    refs = load_lab_reference()
    assert len(refs) >= 40
    assert all(r.loinc for r in refs)
    assert len({r.loinc for r in refs}) == len(refs)


@pytest.mark.parametrize("name,loinc", [
    ("Haemoglobin", "718-7"), ("Hb", "718-7"), ("HbA1c", "4548-4"), ("Glycated Haemoglobin", "4548-4"),
    ("Fasting Blood Sugar", "1558-6"), ("FBS", "1558-6"), ("S. Creatinine", "2160-0"), ("Serum Creatinine", "2160-0"),
    ("SGPT (ALT)", "1742-6"), ("SGOT", "1920-8"), ("LDL Cholesterol", "13457-7"), ("HDL Cholesterol", "2085-9"),
    ("Total Cholesterol", "2093-3"), ("TSH", "3016-3"), ("Vitamin D (25-OH)", "62292-8"), ("Vitamin B12", "2132-9"),
    ("Total Leucocyte Count", "6690-2"), ("Platelet Count", "777-3"), ("PCV", "4544-3"), ("Serum Sodium", "2951-2"),
    ("Random Blood Sugar", "2345-7"), ("Triglycerides", "2571-8"), ("Haemoglobln", "718-7"), ("LDL Cholesterol (Calculated)", "13457-7"),
])
def test_resolve_lab(name, loinc):
    ref, score = resolve_lab(name)
    assert ref is not None and ref.loinc == loinc, (name, score)


def test_resolve_unknown():
    assert resolve_lab("Flux Capacitance")[0] is None


@pytest.mark.parametrize("text,expected", [
    ("13.0 - 17.0", (13.0, 17.0)), ("13-17", (13.0, 17.0)), ("< 200", (None, 200.0)), ("<200", (None, 200.0)),
    ("> 40", (40.0, None)), ("Upto 41", (None, 41.0)), ("4000 - 11000", (4000.0, 11000.0)), ("0.4 – 4.5", (0.4, 4.5)),
    ("Desirable: < 200", (None, 200.0)), ("≤ 5.6", (None, 5.6)), ("200 max", (None, 200.0)), ("70 to 100", (70.0, 100.0)),
    ("", None), ("see note", None),
])
def test_parse_range(text, expected):
    assert parse_range(text) == expected


def test_classify_value():
    assert classify_value(5, 10, 20) == "low"
    assert classify_value(25, 10, 20) == "high"
    assert classify_value(15, 10, 20) == "normal"
    assert classify_value(15, None, 20) == "normal"
    assert classify_value(1, 10, 20, 2, 50) == "critical"
    assert classify_value(60, 10, 20, 2, 50) == "critical"


def test_flag_from_printed_range_first():
    n = normalize_lab(lab("Haemoglobin", 12.1, "g/dL", "11.0 - 15.0"), "male")
    assert n.range_source == "printed" and n.flag == "normal"
    n = normalize_lab(lab("Haemoglobin", 12.1, "g/dL", "13.0 - 17.0"), "male")
    assert n.flag == "low" and n.loinc == "718-7"


def test_flag_table_fallback_by_sex():
    assert normalize_lab(lab("Haemoglobin", 12.5, "g/dL"), "male").flag == "low"
    assert normalize_lab(lab("Haemoglobin", 12.5, "g/dL"), "female").flag == "normal"
    n = normalize_lab(lab("Haemoglobin", 12.5, "g/dL"), "female")
    assert n.range_source == "reference_table" and (n.ref_low, n.ref_high) == (12.0, 15.5)


def test_flag_with_unit_conversion():
    n = normalize_lab(lab("Fasting Blood Sugar", 7.0, "mmol/L"), "male")
    assert n.unit == "mg/dL" and n.value == pytest.approx(126.1, abs=0.1)
    assert n.flag == "high" and n.range_source == "reference_table"
    assert n.conversion.startswith("mmol/L→mg/dL")
    n = normalize_lab(lab("Total Cholesterol", 4.5, "mmol/L"), "female")
    assert n.flag == "normal" and n.value == pytest.approx(174.0, abs=0.1)


def test_printed_range_in_other_unit_converts_bounds():
    n = normalize_lab(lab("Fasting Blood Sugar", 7.0, "mmol/L", "3.9 - 5.6"), "male")
    assert n.flag == "high" and n.range_source == "printed"
    assert n.ref_high == pytest.approx(100.9, abs=0.1)


def test_platelets_lakh():
    n = normalize_lab(lab("Platelet Count", 2.4, "lakh/cumm", "1.5 - 4.5"))
    assert n.flag == "normal" and n.value == 240000 and n.unit == "/µL" and n.ref_low == 150000


def test_critical_and_unknown():
    assert normalize_lab(lab("Serum Potassium", 6.8, "mmol/L", "3.5 - 5.1")).flag == "critical"
    assert normalize_lab(lab("Haemoglobin", 6.0, "g/dL"), "female").flag == "critical"
    assert normalize_lab(lab("Mystery Marker", 3.2, "U/L")).flag == "unknown"
    assert normalize_lab(lab("Haemoglobin", 12.0, "furlongs"), "male").flag == "unknown"
    assert normalize_lab(lab("Haemoglobin", None, "g/dL")).flag == "unknown"


def test_paediatric_without_printed_range_unknown():
    assert normalize_lab(lab("Haemoglobin", 10.5, "g/dL"), "male", age=8).flag == "unknown"


def test_hdl_low_only():
    assert normalize_lab(lab("HDL Cholesterol", 38, "mg/dL"), "male").flag == "low"
    assert normalize_lab(lab("HDL Cholesterol", 45, "mg/dL"), "female").flag == "low"
    assert normalize_lab(lab("HDL Cholesterol", 70, "mg/dL"), "female").flag == "normal"



def test_medicine_table_size():
    assert len({r.brand for r in load_medicines().values()}) >= 50


@pytest.mark.parametrize("name,generic", [
    ("Tab Glycomet 500 mg", "metformin"), ("Tab Glycornet 500", "metformin"), ("Tab Atorva 10 mg", "atorvastatin"),
    ("Tab Telma 40 mg", "telmisartan"), ("Cap Uprise-D3 60K", "cholecalciferol"), ("Tab Pan 40 mg", "pantoprazole"),
    ("Tab Dolo 650", "paracetamol"), ("Tab Thyronorm 25 mcg", "levothyroxine"), ("Tab Rosuvas 10", "rosuvastatin"),
    ("Tab Ecosprin 75", "aspirin"), ("Tab Ondem 4 mg", "ondansetron"), ("Tab Pantocid 40 mg", "pantoprazole"),
    ("Cap Sporlac", "lactic acid bacillus"), ("ORS sachet", "oral rehydration salts"), ("Tab Pan D", "pantoprazole + domperidone"),
    ("Tab Telma H", "telmisartan + hydrochlorothiazide"), ("Tab Metformin 500", "metformin"),
])
def test_brand_to_generic(name, generic):
    ref, _ = resolve_medicine(name)
    assert ref is not None and ref.generic == generic


def test_extended_csv_merged(tmp_path, monkeypatch):
    from app.config import get_settings

    ext = get_settings().reference_dir / "medicines_extended.csv"
    assert not ext.exists()
    load_medicines.cache_clear()
    try:
        ext.write_text("brand,generic,strength,form,drug_class\nZzymed,zzyamine,5 mg,tablet,test\n")
        load_medicines.cache_clear()
        assert resolve_medicine("Tab Zzymed 5")[0].generic == "zzyamine"
    finally:
        ext.unlink()
        load_medicines.cache_clear()



def _entry(doc, d, name, dosage="", timing="", duration=""):
    m = med(name, dosage, timing, duration)
    from app.normalize.medicines import normalize_medication

    m.normalized = normalize_medication(m)
    return MedEntry(doc, "prescription", d, m)


def test_reconcile_same_generic_across_documents():
    entries = [
        _entry("d1", date(2024, 6, 5), "Tab Glycomet 500 mg", "1-0-1", "after food", "continue"),
        _entry("d2", date(2024, 9, 22), "Tab Glycomet 500", "BD", "PC", "x 1 month"),
        _entry("d3", date(2024, 3, 15), "Tab Atorva 10 mg", "0-0-1", "", "x 30 days"),
        _entry("d2", date(2024, 9, 22), "Tab Rosuvas 10", "HS", "", "x 1 month"),
    ]
    notes = reconcile(entries, as_of=date(2024, 9, 22))
    assert [n.generic for n in notes] == ["metformin"]
    text = notes[0].text("en")
    assert "ask your doctor" in text.lower()
    assert "stop" not in text.lower()
    assert "डॉक्टर" in notes[0].text("hi")


def test_reconcile_combination_component():
    entries = [
        _entry("d1", date(2024, 9, 1), "Tab Ecosprin AV 75", "0-0-1"),
        _entry("d2", date(2024, 9, 10), "Tab Atorva 10", "0-0-1"),
    ]
    assert [n.generic for n in reconcile(entries, date(2024, 9, 20))] == ["atorvastatin"]


def test_is_active_rules():
    assert not is_active(_entry("d", date(2024, 3, 15), "Tab Pan 40", "OD", "", "x 14 days"), date(2024, 9, 1))
    assert is_active(_entry("d", date(2024, 9, 1), "Tab Pan 40", "OD", "", "x 14 days"), date(2024, 9, 10))
    assert is_active(_entry("d", date(2023, 1, 1), "Tab Glycomet", "BD", "", "continue"), date(2024, 9, 10))
    assert is_active(_entry("d", date(2024, 8, 1), "Tab Ecosprin 75", "OD"), date(2024, 9, 10))
    assert not is_active(_entry("d", date(2024, 1, 1), "Tab Ecosprin 75", "OD"), date(2024, 9, 10))



def test_handwritten_always_confirms_name_and_dosage():
    rx = Prescription(medications=[med("Tab Dolo 650", "SOS"), med("Tab Glycomet 500", "BD", "PC", "x 1 month")], is_handwritten=True)
    normalize_extraction(rx)
    queue = apply_confirmation_rules(rx)
    paths = {q["path"] for q in queue}
    assert {"medications.0.name", "medications.0.dosage", "medications.1.name", "medications.1.dosage"} <= paths
    assert all(F_.needs_confirmation for F_ in (rx.medications[0].name, rx.medications[1].dosage))


def test_printed_typed_rx_high_confidence_not_queued():
    rx = Prescription(medications=[med("Tab Glycomet 500", "1-0-1", "after food", "x 30 days")])
    normalize_extraction(rx)
    assert apply_confirmation_rules(rx) == []


def test_confirm_rules_labs():
    rep = LabReport(results=[
        lab("Haemoglobin", 12.1, "g/dL", "13.0 - 17.0", "H"),
        lab("Serum Potassium", 6.9, "mmol/L", "3.5 - 5.1"),
        lab("Flux Capacitance", 1.0, "U/L"),
        LabResult(test_name=F("HbA1c"), value=F(7.2, conf=0.4), unit=F("%")),
    ])
    rep.patient.sex = F("male")
    normalize_extraction(rep)
    queue = {q["path"]: q for q in apply_confirmation_rules(rep)}
    assert "disagrees" in " ".join(queue["results.0.value"]["reasons"])
    assert "critical" in " ".join(queue["results.1.value"]["reasons"])
    assert "not recognised" in " ".join(queue["results.2.test_name"]["reasons"])
    assert "low confidence" in " ".join(queue["results.3.value"]["reasons"])
    assert queue["results.0.value"]["label"] == "Haemoglobin · Result"


def test_unrecognised_medicine_and_unparsed_dosage():
    rx = Prescription(medications=[med("Tab Xyzzy 10", "1-0-1 blah")])
    normalize_extraction(rx)
    queue = {q["path"]: q for q in apply_confirmation_rules(rx)}
    assert "medications.0.name" in queue and "medications.0.dosage" in queue


def test_confirmed_fields_not_requeued():
    rx = Prescription(medications=[med("Tab Dolo 650", "SOS")], is_handwritten=True)
    rx.medications[0].name.confirmed = True
    rx.medications[0].dosage.confirmed = True
    normalize_extraction(rx)
    assert apply_confirmation_rules(rx) == []
    assert get_field(rx, "medications.0.name").value == "Tab Dolo 650"
