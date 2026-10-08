import math
import random
import sys
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples"
FONT_DIR = Path("/usr/share/fonts/truetype")
A4 = (595, 842)
DPI = 200
SCALE = DPI / 72


def font_path(bold=False, italic=False):
    candidates = []
    if italic:
        candidates += ["dejavu/DejaVuSans-Oblique.ttf", "liberation/LiberationSans-Italic.ttf"]
    if bold:
        candidates += ["dejavu/DejaVuSans-Bold.ttf", "liberation/LiberationSans-Bold.ttf"]
    candidates += ["dejavu/DejaVuSans.ttf", "liberation/LiberationSans-Regular.ttf"]
    for c in candidates:
        if (FONT_DIR / c).exists():
            return str(FONT_DIR / c)
    return None


class Page:
    def __init__(self):
        self.ops = []

    def text(self, x, y, s, size=10, bold=False, italic=False):
        self.ops.append(("text", x, y, s, size, bold, italic))

    def line(self, x0, y0, x1, y1, width=0.8):
        self.ops.append(("line", x0, y0, x1, y1, width))

    def table(self, x, y, cols, rows, size=9, row_h=15, header_bold=True):
        for i, h in enumerate(rows[0]):
            self.text(x + cols[i], y, h, size, bold=header_bold)
        self.line(x, y + 4, x + cols[-1] + 120, y + 4)
        yy = y + row_h
        for r in rows[1:]:
            for i, c in enumerate(r):
                self.text(x + cols[i], yy, c, size, bold=(len(r) > 4 and i == 4 and c in ("H", "L")))
            yy += row_h
        return yy


def render_pdf(page, path):
    doc = fitz.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    for op in page.ops:
        if op[0] == "text":
            _, x, y, s, size, bold, italic = op
            fontname = "hebo" if bold else ("heit" if italic else "helv")
            p.insert_text((x, y), s, fontsize=size, fontname=fontname)
        else:
            _, x0, y0, x1, y1, w = op
            p.draw_line((x0, y0), (x1, y1), width=w)
    doc.save(path)


def render_image(page, handwritten=False, seed=7):
    rng = random.Random(seed)
    w, h = int(A4[0] * SCALE), int(A4[1] * SCALE)
    img = Image.new("RGB", (w, h), (252, 251, 247))
    d = ImageDraw.Draw(img)
    cache = {}
    for op in page.ops:
        if op[0] == "text":
            _, x, y, s, size, bold, italic = op
            px = int(size * SCALE * (1.25 if handwritten and not bold else 1.0))
            key = (px, bold, italic or handwritten)
            if key not in cache:
                fp = font_path(bold, italic or handwritten)
                cache[key] = ImageFont.truetype(fp, px) if fp else ImageFont.load_default()
            f = cache[key]
            if handwritten and not bold:
                cx = x * SCALE
                cy = y * SCALE - px
                for ch in s:
                    jy = rng.uniform(-2.5, 2.5)
                    d.text((cx, cy + jy), ch, fill=(20, 30, 90), font=f)
                    cx += d.textlength(ch, font=f) * rng.uniform(0.95, 1.08)
            else:
                d.text((x * SCALE, y * SCALE - px), s, fill=(15, 15, 15), font=f)
        else:
            _, x0, y0, x1, y1, wd = op
            d.line((x0 * SCALE, y0 * SCALE, x1 * SCALE, y1 * SCALE), fill=(40, 40, 40), width=max(1, int(wd * SCALE)))
    return img


def photo_effect(img, angle=1.2, seed=3):
    rng = random.Random(seed)
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(210, 205, 195))
    px = img.load()
    w, h = img.size
    for _ in range(w * h // 300):
        x, y = rng.randrange(w), rng.randrange(h)
        v = rng.randint(150, 230)
        px[x, y] = (v, v, v)
    shade = Image.new("L", img.size)
    sd = ImageDraw.Draw(shade)
    for i in range(0, w, 8):
        val = int(235 + 20 * math.sin(i / w * math.pi))
        sd.rectangle((i, 0, i + 8, h), fill=val)
    img = Image.composite(img, Image.new("RGB", img.size, (180, 175, 165)), shade.point(lambda v: 255 if v > 240 else v + 15))
    return img.filter(ImageFilter.GaussianBlur(0.6))


def header(page, name, sub, phone):
    page.text(40, 50, name, 16, bold=True)
    page.text(40, 66, sub, 9)
    page.text(40, 78, phone, 9)
    page.line(40, 86, 555, 86, 1.2)


def lab_page(title_date, rows, lab_no, collected, reported):
    p = Page()
    header(p, "SUNRISE DIAGNOSTICS PVT. LTD.", "NABL Accredited Laboratory | 12 MG Road, Pune 411001", "Ph: 020-2612 3456 | www.sunrisediag.example")
    p.text(40, 106, "Patient Name : Mr. Rahul Sharma", 10)
    p.text(320, 106, f"Lab No : {lab_no}", 10)
    p.text(40, 121, "Age / Sex : 45 Y / Male", 10)
    p.text(320, 121, f"Collected : {collected}", 10)
    p.text(40, 136, "Ref. By : Dr. Anjali Mehta, MD", 10)
    p.text(320, 136, f"Reported : {reported}", 10)
    p.line(40, 144, 555, 144)
    y = 164
    for section, items in rows:
        p.text(40, y, section, 11, bold=True)
        y += 16
        table = [["Test", "Result", "Unit", "Bio. Ref. Interval", "Flag"]] + items
        y = p.table(40, y, [0, 200, 270, 340, 470], table) + 10
    p.text(40, y + 10, "*** End of Report ***", 9, italic=True)
    p.text(380, 780, "Dr. Sameer Kulkarni, MD (Pathology)", 9, bold=True)
    p.text(380, 792, "Consultant Pathologist | Reg. No. MMC 2011/04/1234", 8)
    return p


def lab_report_march():
    rows = [
        ("HAEMATOLOGY - COMPLETE BLOOD COUNT", [
            ["Haemoglobin", "12.1", "g/dL", "13.0 - 17.0", "L"],
            ["Total Leucocyte Count", "7800", "/cumm", "4000 - 11000", ""],
            ["Platelet Count", "2.4", "lakh/cumm", "1.5 - 4.5", ""],
            ["RBC Count", "4.6", "mill/cumm", "4.5 - 5.5", ""],
            ["PCV", "38.5", "%", "40 - 50", "L"],
        ]),
        ("BIOCHEMISTRY", [
            ["Fasting Blood Sugar", "138", "mg/dL", "70 - 100", "H"],
            ["HbA1c", "7.2", "%", "4.0 - 5.6", "H"],
            ["Serum Creatinine", "0.9", "mg/dL", "0.7 - 1.3", ""],
        ]),
        ("LIPID PROFILE", [
            ["Total Cholesterol", "232", "mg/dL", "< 200", "H"],
            ["Triglycerides", "190", "mg/dL", "< 150", "H"],
            ["HDL Cholesterol", "38", "mg/dL", "> 40", "L"],
            ["LDL Cholesterol", "156", "mg/dL", "< 100", "H"],
        ]),
    ]
    return lab_page("2024-03-12", rows, "SD24031288", "12/03/2024 08:10", "12/03/2024 17:45")


def lab_report_september():
    rows = [
        ("BIOCHEMISTRY", [
            ["Fasting Blood Sugar", "118", "mg/dL", "70 - 100", "H"],
            ["HbA1c", "6.6", "%", "4.0 - 5.6", "H"],
            ["SGPT (ALT)", "42", "U/L", "0 - 41", "H"],
            ["Serum Creatinine", "1.0", "mg/dL", "0.7 - 1.3", ""],
        ]),
        ("LIPID PROFILE", [
            ["Total Cholesterol", "198", "mg/dL", "< 200", ""],
            ["LDL Cholesterol", "124", "mg/dL", "< 100", "H"],
            ["HDL Cholesterol", "41", "mg/dL", "> 40", ""],
        ]),
        ("THYROID & VITAMINS", [
            ["TSH", "5.8", "uIU/mL", "0.4 - 4.5", "H"],
            ["Vitamin D (25-OH)", "18", "ng/mL", "30 - 100", "L"],
            ["Vitamin B12", "210", "pg/mL", "211 - 911", "L"],
        ]),
    ]
    return lab_page("2024-09-20", rows, "SD24092041", "20/09/2024 07:55", "20/09/2024 18:20")


def clinic_header(p):
    p.text(40, 50, "Dr. Anjali Mehta", 16, bold=True)
    p.text(40, 66, "MBBS, MD (Medicine) | Reg. No. MMC 2009/03/5678", 9)
    p.text(40, 78, "Mehta Family Clinic, 4 Baner Road, Pune 411045 | Ph: 98220 12345", 9)
    p.line(40, 86, 555, 86, 1.2)


def prescription_printed():
    p = Page()
    clinic_header(p)
    p.text(40, 108, "Patient: Mr. Rahul Sharma      Age/Sex: 45/M      Date: 15/03/2024", 10)
    p.text(40, 126, "C/O: Routine follow-up, fatigue", 10)
    p.text(40, 141, "Diagnosis: Type 2 Diabetes Mellitus, Dyslipidemia", 10)
    p.text(40, 166, "Rx", 18, bold=True)
    meds = [
        "1. Tab Glycomet 500 mg        1-0-1   after food     x 30 days",
        "2. Tab Atorva 10 mg           0-0-1   at bedtime     x 30 days",
        "3. Tab Telma 40 mg            1-0-0   before breakfast  x 30 days",
        "4. Cap Uprise-D3 60K          once a week  after food   x 8 weeks",
        "5. Tab Pan 40 mg              OD  AC   x 14 days",
    ]
    y = 190
    for m in meds:
        p.text(50, y, m, 10)
        y += 20
    p.text(40, y + 15, "Advice: Low sugar, low fat diet. Brisk walk 30 min daily.", 10)
    p.text(40, y + 31, "Follow up after 6 months with FBS, HbA1c, Lipid profile, TSH, Vit D.", 10)
    p.text(400, 760, "Dr. Anjali Mehta", 10, bold=True)
    return p


def prescription_handwritten():
    p = Page()
    clinic_header(p)
    p.text(40, 112, "Name: Rahul Sharma   45/M   Date: 22/9/24", 11)
    p.text(40, 134, "c/o fever x 2 days, body ache", 11)
    p.text(40, 154, "Dx: Viral fever, Subclinical hypothyroidism", 11)
    p.text(40, 182, "Rx", 18, bold=True)
    meds = [
        "1) Tab Dolo 650   SOS  for fever  x 3 days",
        "2) Tab Thyronorm 25 mcg  OD  empty stomach  x 6 wks",
        "3) Tab Glycomet 500  BD  PC  x 1 month",
        "4) Tab Rosuvas 10   HS  x 1 month",
        "5) Tab Ecosprin 75  0-1-0  PC",
    ]
    y = 210
    for m in meds:
        p.text(48, y, m, 11)
        y += 26
    p.text(40, y + 12, "Plenty of oral fluids. Review after 6 wks with TSH.", 11)
    p.text(400, 760, "Dr. A. Mehta", 10, bold=True)
    return p


def discharge_summary():
    p = Page()
    header(p, "CITY CARE HOSPITAL", "Multispeciality Hospital | Shivaji Nagar, Pune 411005", "Ph: 020-2553 0000 | NABH Accredited")
    p.text(200, 104, "DISCHARGE SUMMARY", 13, bold=True)
    p.text(40, 124, "Patient Name: Mr. Rahul Sharma        Age/Sex: 45 Y / M       UHID: CCH-778812", 10)
    p.text(40, 139, "Date of Admission: 01/06/2024          Date of Discharge: 05/06/2024", 10)
    p.text(40, 154, "Consultant: Dr. Vikram Rao, MD (Medicine)     Ward: General Ward", 10)
    p.line(40, 162, 555, 162)
    p.text(40, 180, "Final Diagnosis:", 10, bold=True)
    p.text(60, 195, "1. Acute gastroenteritis with moderate dehydration", 10)
    p.text(60, 210, "2. Type 2 Diabetes Mellitus (known case)", 10)
    p.text(40, 230, "Presenting Complaints:", 10, bold=True)
    p.text(60, 245, "Loose stools and vomiting for 2 days, weakness.", 10)
    p.text(40, 265, "Course in Hospital:", 10, bold=True)
    p.text(60, 280, "Patient was managed with IV fluids, antiemetics and supportive care.", 10)
    p.text(60, 295, "Symptoms improved. Tolerating orally at discharge. Vitals stable.", 10)
    p.text(40, 318, "Investigations (01/06/2024):", 10, bold=True)
    table = [
        ["Test", "Result", "Unit", "Ref. Range", "Flag"],
        ["Serum Sodium", "132", "mmol/L", "135 - 145", "L"],
        ["Serum Potassium", "3.3", "mmol/L", "3.5 - 5.1", "L"],
        ["Serum Creatinine", "1.4", "mg/dL", "0.7 - 1.3", "H"],
        ["Haemoglobin", "13.5", "g/dL", "13.0 - 17.0", ""],
        ["Random Blood Sugar", "212", "mg/dL", "70 - 140", "H"],
    ]
    y = p.table(60, 336, [0, 160, 220, 290, 400], table) + 10
    p.text(40, y + 6, "Medications on Discharge:", 10, bold=True)
    meds = [
        "1. Tab Ondem 4 mg        TDS  x 3 days",
        "2. ORS sachet in 1 L water   SOS after each loose stool",
        "3. Tab Pantocid 40 mg    OD before breakfast  x 7 days",
        "4. Cap Sporlac           BD  x 5 days",
        "5. Tab Glycomet 500 mg   1-0-1  after food  (continue)",
    ]
    y += 22
    for m in meds:
        p.text(60, y, m, 10)
        y += 16
    p.text(40, y + 12, "Follow-up: Review in OPD after 1 week with Serum Electrolytes, Creatinine.", 10)
    p.text(40, y + 27, "Advice: Soft diet, adequate oral fluids.", 10)
    p.text(380, 780, "Dr. Vikram Rao", 10, bold=True)
    p.text(380, 792, "Consultant Physician", 8)
    return p


def image_to_pdf(img, path):
    doc = fitz.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    tmp = path.with_suffix(".tmp.jpg")
    img.save(tmp, quality=80)
    page.insert_image(page.rect, filename=str(tmp))
    doc.save(path)
    tmp.unlink()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    render_pdf(lab_report_march(), OUT / "lab_report_2024_03.pdf")
    photo_effect(render_image(lab_report_september()), angle=1.4).convert("RGB").save(OUT / "lab_report_2024_09.png")
    photo_effect(render_image(prescription_printed()), angle=-0.8, seed=5).convert("RGB").save(OUT / "prescription_printed_2024_03.jpg", quality=85)
    render_image(prescription_handwritten(), handwritten=True, seed=11).save(OUT / "prescription_handwritten_2024_09.png")
    image_to_pdf(render_image(discharge_summary()).convert("L").convert("RGB"), OUT / "discharge_summary_2024_06.pdf")
    print("\n".join(sorted(p.name for p in OUT.iterdir() if p.is_file())))


if __name__ == "__main__":
    sys.exit(main())
