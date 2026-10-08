from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.ingest.classify import classify, rule_scores
from app.ingest.ingest import UnsupportedFile, ingest_file, sniff_type
from app.ingest.models import OcrLine, layout_text
from app.ingest.preprocess import enhance_contrast, estimate_skew, to_gray
from tests.conftest import SAMPLES

SAMPLE_FILES = sorted(p for p in SAMPLES.iterdir() if p.is_file())
EXPECTED_TYPES = {
    "lab_report_2024_03.pdf": "lab_report",
    "lab_report_2024_09.png": "lab_report",
    "prescription_printed_2024_03.jpg": "prescription",
    "prescription_handwritten_2024_09.png": "prescription",
    "discharge_summary_2024_06.pdf": "discharge_summary",
}


@pytest.fixture(scope="session")
def ingested(tmp_path_factory):
    import os

    from app.config import get_settings

    os.environ["DATA_DIR"] = str(tmp_path_factory.mktemp("ingest"))
    get_settings.cache_clear()
    out = {f.name: ingest_file(f, f.stem) for f in SAMPLE_FILES}
    del os.environ["DATA_DIR"]
    get_settings.cache_clear()
    return out


def test_samples_present():
    assert len(SAMPLE_FILES) >= 5


@pytest.mark.slow
@pytest.mark.parametrize("name", [f.name for f in SAMPLE_FILES])
def test_every_sample_yields_text_with_boxes(ingested, name):
    pages = ingested[name]
    assert pages
    page = pages[0]
    assert len(page.text) > 100
    assert page.lines
    for line in page.lines:
        x0, y0, x1, y1 = line.box
        assert 0 <= x0 < x1 <= page.width + 1
        assert 0 <= y0 < y1 <= page.height + 1
        assert 0 <= line.confidence <= 1
    assert Path(page.image_path).exists()


@pytest.mark.slow
def test_ingest_paths(ingested):
    assert ingested["lab_report_2024_03.pdf"][0].source == "text_layer"
    assert ingested["discharge_summary_2024_06.pdf"][0].source == "ocr"
    assert ingested["lab_report_2024_09.png"][0].source == "ocr"
    assert abs(ingested["lab_report_2024_09.png"][0].deskew_angle) > 0.5


@pytest.mark.slow
@pytest.mark.parametrize("name,expected", sorted(EXPECTED_TYPES.items()))
def test_rule_classifier_on_samples(ingested, name, expected, fake_llm):
    result = classify(ingested[name][0].text)
    assert result.document_type == expected
    assert result.method == "rules"


@pytest.mark.slow
def test_key_values_survive_ocr(ingested):
    text = ingested["lab_report_2024_09.png"][0].text
    for token in ["HbA1c", "6.6", "TSH", "5.8", "Vitamin D"]:
        assert token in text
    rx = ingested["prescription_handwritten_2024_09.png"][0].text
    for token in ["Dolo", "Thyronorm", "Glycomet", "SOS"]:
        assert token in rx


def test_classifier_llm_fallback(fake_llm):
    fake_llm.responses.append('{"document_type": "prescription", "reason": "medicine list"}')
    result = classify("Mr X\nsome ambiguous text")
    assert result.method == "llm"
    assert result.document_type == "prescription"


def test_classifier_fallback_when_llm_invalid(fake_llm):
    fake_llm.responses += ['{"document_type": "x-ray"}', '{"document_type": "radiology"}']
    result = classify("ambiguous")
    assert result.method == "rules_low_margin"


def test_rule_scores_keywords():
    s = rule_scores("DISCHARGE SUMMARY\nDate of Admission: 1/6/24\nCourse in Hospital")
    assert max(s, key=s.get) == "discharge_summary"


def test_sniff_type():
    assert sniff_type(b"%PDF-1.7") == "pdf"
    assert sniff_type(b"\x89PNG\r\n\x1a\n....") == "png"
    assert sniff_type(b"\xff\xd8\xff\xe0") == "jpg"
    with pytest.raises(UnsupportedFile):
        sniff_type(b"GIF89a")


def test_layout_text_groups_rows():
    lines = [
        OcrLine(text="12.1", box=[300, 100, 340, 120]),
        OcrLine(text="Haemoglobin", box=[10, 101, 120, 121]),
        OcrLine(text="Platelets", box=[10, 140, 120, 160]),
    ]
    assert layout_text(lines) == "Haemoglobin   12.1\nPlatelets"


def _text_image(angle):
    im = Image.new("L", (1400, 900), 255)
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    except OSError:
        f = ImageFont.load_default()
    for i in range(12):
        d.text((80, 60 + i * 60), "Haemoglobin 12.1 g/dL 13.0 - 17.0 reference", fill=0, font=f)
    return im.rotate(angle, expand=False, fillcolor=255).convert("RGB")


@pytest.mark.parametrize("angle", [0.0, 2.0, -3.0])
def test_deskew_estimate(angle):
    est = estimate_skew(to_gray(_text_image(angle)))
    assert abs(est + angle) < 0.6


def test_contrast_stretch():
    arr = np.full((50, 50), 120, np.uint8)
    arr[10:20, 10:40] = 140
    out = enhance_contrast(arr)
    assert out.max() - out.min() > 20
