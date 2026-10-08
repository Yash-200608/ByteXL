import json
import re

LAB = {
    "patient_name": "Mr. Rahul Sharma", "age": "45 Y", "sex": "Male", "patient_id": "", "facility": "SUNRISE DIAGNOSTICS PVT. LTD.",
    "referring_doctor": "Dr. Anjali Mehta, MD", "pathologist": "Dr. Sameer Kulkarni, MD (Pathology)",
    "collected_date": "12/03/2024 08:10", "report_date": "12/03/2024 17:45",
    "tests": [
        {"name": "Haemoglobin", "value": "12.1", "unit": "g/dL", "reference_range": "13.0 - 17.0", "flag": "L"},
        {"name": "Total Leucocyte Count", "value": "7800", "unit": "/cumm", "reference_range": "4000 - 11000", "flag": ""},
        {"name": "Platelet Count", "value": "2.4", "unit": "lakh/cumm", "reference_range": "1.5 - 4.5", "flag": ""},
        {"name": "Fasting Blood Sugar", "value": "138", "unit": "mg/dL", "reference_range": "70 - 100", "flag": "H"},
        {"name": "HbA1c", "value": "7.2", "unit": "%", "reference_range": "4.0 - 5.6", "flag": "H"},
        {"name": "Serum Creatinine", "value": "0.9", "unit": "mg/dL", "reference_range": "0.7 - 1.3", "flag": ""},
        {"name": "Total Cholesterol", "value": "232", "unit": "mg/dL", "reference_range": "< 200", "flag": "H"},
        {"name": "HDL Cholesterol", "value": "38", "unit": "mg/dL", "reference_range": "> 40", "flag": "L"},
        {"name": "LDL Cholesterol", "value": "156", "unit": "mg/dL", "reference_range": "< 100", "flag": "H"},
    ],
}

RX = {
    "patient_name": "Rahul Sharma", "age": "45", "sex": "M", "doctor_name": "Dr. Anjali Mehta", "doctor_registration": "MMC 2009/03/5678",
    "clinic": "Mehta Family Clinic", "date": "22/9/24", "complaints": ["fever x 2 days, body ache"],
    "diagnoses": ["Viral fever", "Subclinical hypothyroidism"],
    "medicines": [
        {"name": "Tab Dolo 650", "strength": "650", "dosage": "SOS", "timing": "", "duration": "x 3 days", "instructions": "for fever"},
        {"name": "Tab Glycomet 500", "strength": "500", "dosage": "BD", "timing": "PC", "duration": "x 1 month", "instructions": ""},
        {"name": "Tab Rosuvas 10", "strength": "10", "dosage": "HS", "timing": "", "duration": "x 1 month", "instructions": ""},
    ],
    "advice": ["Plenty of oral fluids."], "follow_up": "after 6 wks with TSH", "handwritten": True,
}


def _data_from(messages):
    text = messages[1]["content"]
    start = text.index("{")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            return json.loads(text[start : i + 1])
    raise ValueError("no json")


def summary_for(messages, lang="en", bad=None):
    data = _data_from(messages)
    hindi = "हिंदी" in messages[0]["content"] or "देवनागरी" in messages[0]["content"]
    if hindi:
        out = {
            "what_this_is": "यह एक मेडिकल दस्तावेज़ है जिसमें जांच और दवाओं की जानकारी है।",
            "key_findings": ["रिपोर्ट में कुछ मान सामान्य सीमा से बाहर हैं।"],
            "out_of_range": [{"name": a["name"], "meaning": "यह आमतौर पर डॉक्टर से चर्चा करने लायक बात है।"} for a in data["abnormal_results"]],
            "questions": ["इन परिणामों का मेरे लिए क्या मतलब है?", "अगली जांच कब करानी चाहिए?"],
        }
    else:
        out = {
            "what_this_is": f"This document is a {data['document_type'].replace('_', ' ')}.",
            "key_findings": ["The report lists several results."],
            "out_of_range": [{"name": a["name"], "meaning": "This generally means the value is worth discussing with the doctor."} for a in data["abnormal_results"]],
            "questions": ["What do these results mean for me?", "When should I repeat these tests?"],
        }
    if bad:
        out["key_findings"].append(bad)
    return json.dumps(out, ensure_ascii=False)


def router(lab=LAB, rx=RX, bad_summary=None):
    def handle(model, messages, schema):
        title = (schema or {}).get("title", "")
        if title == "LabReportLLM":
            return json.dumps(lab)
        if title == "PrescriptionLLM":
            return json.dumps(rx)
        if title == "SummaryLLM":
            return summary_for(messages, bad=bad_summary)
        if title == "ClassifierOutput":
            return json.dumps({"document_type": "lab_report", "reason": "test"})
        raise AssertionError(f"unexpected schema {title}")

    return handle


def text_pdf(lines: list[str]) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 60
    for line in lines:
        page.insert_text((40, y), line, fontsize=10)
        y += 18
    return doc.tobytes()


RX_PDF_LINES = [
    "Dr. Anjali Mehta",
    "MBBS, MD (Medicine) | Reg. No. MMC 2009/03/5678",
    "Mehta Family Clinic, 4 Baner Road, Pune",
    "Name: Rahul Sharma   45/M   Date: 22/9/24",
    "c/o fever x 2 days, body ache",
    "Dx: Viral fever, Subclinical hypothyroidism",
    "Rx",
    "1) Tab Dolo 650   SOS  for fever  x 3 days",
    "2) Tab Glycomet 500  BD  PC  x 1 month",
    "3) Tab Rosuvas 10   HS  x 1 month",
    "Plenty of oral fluids. Review after 6 wks with TSH.",
]
