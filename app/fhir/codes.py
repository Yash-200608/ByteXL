LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
NRCES = "https://nrces.in/ndhm/fhir/r4/StructureDefinition"
ABHA_SYSTEM = "https://healthid.ndhm.gov.in"
ABHA_ADDRESS_SYSTEM = "https://healthid.ndhm.gov.in/health-id"
GENERIC_SYSTEM = "urn:bytexl:generic"

DOC_TYPE_LOINC = {
    "lab_report": ("11502-2", "Laboratory report"),
    "prescription": ("57833-6", "Prescription for medication"),
    "discharge_summary": ("18842-5", "Discharge summary"),
}

COMPOSITION_PROFILE = {
    "lab_report": "DiagnosticReportRecord",
    "prescription": "PrescriptionRecord",
    "discharge_summary": "DischargeSummaryRecord",
}

INTERPRETATION = {
    "low": ("L", "Low"),
    "high": ("H", "High"),
    "normal": ("N", "Normal"),
    "critical": ("AA", "Critical abnormal"),
}

UCUM_CODES = {
    "mg/dL": "mg/dL", "g/dL": "g/dL", "g/L": "g/L", "%": "%", "/µL": "/uL", "10^3/µL": "10*3/uL", "10^6/µL": "10*6/uL",
    "µIU/mL": "u[IU]/mL", "ng/mL": "ng/mL", "pg/mL": "pg/mL", "U/L": "U/L", "mmol/L": "mmol/L", "µmol/L": "umol/L",
    "fL": "fL", "pg": "pg", "mm/h": "mm/h", "/hpf": "/[HPF]", "mg/L": "mg/L", "µg/dL": "ug/dL", "ng/dL": "ng/dL",
    "nmol/L": "nmol/L", "pmol/L": "pmol/L", "pH": "[pH]",
}

UCUM_TIME = {"d": "d", "wk": "wk", "mo": "mo", "h": "h"}
