from pydantic import BaseModel, Field


class LabTestLLM(BaseModel):
    name: str = Field(description="test name exactly as printed")
    value: str = Field(description="result exactly as printed, e.g. 12.1 or Nil")
    unit: str = ""
    reference_range: str = Field("", description="reference interval exactly as printed")
    flag: str = Field("", description="H or L only if printed next to the result, else empty")


class LabReportLLM(BaseModel):
    patient_name: str = ""
    age: str = ""
    sex: str = ""
    patient_id: str = ""
    facility: str = Field("", description="laboratory name")
    referring_doctor: str = ""
    pathologist: str = ""
    collected_date: str = Field("", description="as printed")
    report_date: str = Field("", description="as printed")
    tests: list[LabTestLLM]


class MedicineLLM(BaseModel):
    name: str = Field(description="medicine as written including form, e.g. Tab Glycomet 500 mg")
    strength: str = ""
    dosage: str = Field("", description="frequency as written, e.g. 1-0-1, BD, OD, SOS, once a week")
    timing: str = Field("", description="food or time instruction as written, e.g. after food, HS, AC")
    duration: str = Field("", description="as written, e.g. x 5 days")
    instructions: str = ""


class PrescriptionLLM(BaseModel):
    patient_name: str = ""
    age: str = ""
    sex: str = ""
    doctor_name: str = ""
    doctor_registration: str = ""
    clinic: str = ""
    date: str = Field("", description="as printed")
    complaints: list[str] = []
    diagnoses: list[str] = []
    medicines: list[MedicineLLM]
    advice: list[str] = []
    follow_up: str = ""
    handwritten: bool = False


class DischargeSummaryLLM(BaseModel):
    patient_name: str = ""
    age: str = ""
    sex: str = ""
    patient_id: str = ""
    hospital: str = ""
    doctor: str = ""
    admission_date: str = Field("", description="as printed")
    discharge_date: str = Field("", description="as printed")
    diagnoses: list[str] = []
    presenting_complaints: list[str] = []
    hospital_course: str = ""
    procedures: list[str] = []
    investigations: list[LabTestLLM] = []
    discharge_medicines: list[MedicineLLM] = []
    follow_up: str = ""
    advice: list[str] = []


LLM_SCHEMAS: dict[str, type[BaseModel]] = {
    "lab_report": LabReportLLM,
    "prescription": PrescriptionLLM,
    "discharge_summary": DischargeSummaryLLM,
}
