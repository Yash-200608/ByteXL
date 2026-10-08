import hashlib
import time
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from app.config import get_settings
from app.ingest.models import OcrLine, PageData
from app.ingest.ocr import ocr_image
from app.ingest.preprocess import preprocess_photo

CONTENT_TYPES = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}


class UnsupportedFile(ValueError):
    pass


def sniff_type(data: bytes) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    raise UnsupportedFile("Only PDF, JPG and PNG files are supported.")


def store_original(data: bytes, document_id: str) -> tuple[Path, str, str]:
    kind = sniff_type(data)
    s = get_settings()
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    path = s.uploads_dir / f"{document_id}.{kind}"
    path.write_bytes(data)
    return path, CONTENT_TYPES[kind], hashlib.sha256(data).hexdigest()


def _page_path(document_id: str, index: int) -> Path:
    s = get_settings()
    s.pages_dir.mkdir(parents=True, exist_ok=True)
    return s.pages_dir / f"{document_id}_{index}.png"


def _text_layer_lines(page: pymupdf.Page, scale: float) -> list[OcrLine]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            lines.append(OcrLine(text=text, confidence=1.0, box=[x0 * scale, y0 * scale, x1 * scale, y1 * scale]))
    return lines


def _ocr_page(image: Image.Image, document_id: str, index: int, photo: bool) -> PageData:
    start = time.time()
    angle = 0.0
    if photo:
        image, angle = preprocess_photo(image)
    else:
        image = image.convert("RGB")
    path = _page_path(document_id, index)
    image.save(path)
    lines = ocr_image(image)
    return PageData(
        index=index,
        width=image.width,
        height=image.height,
        image_path=str(path),
        source="ocr",
        lines=lines,
        deskew_angle=round(angle, 2),
        duration_s=round(time.time() - start, 2),
    )


def ingest_pdf(path: Path, document_id: str) -> list[PageData]:
    s = get_settings()
    scale = s.pdf_dpi / 72
    pages = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc):
            start = time.time()
            text = page.get_text().strip()
            pix = page.get_pixmap(dpi=s.pdf_dpi)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            if len(text) >= s.min_page_chars:
                out = _page_path(document_id, i)
                image.save(out)
                pages.append(
                    PageData(
                        index=i,
                        width=image.width,
                        height=image.height,
                        image_path=str(out),
                        source="text_layer",
                        lines=_text_layer_lines(page, scale),
                        duration_s=round(time.time() - start, 2),
                    )
                )
            else:
                pages.append(_ocr_page(image, document_id, i, photo=True))
    return pages


def ingest_image(path: Path, document_id: str) -> list[PageData]:
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return [_ocr_page(image, document_id, 0, photo=True)]


def ingest_file(path: Path, document_id: str) -> list[PageData]:
    kind = sniff_type(Path(path).read_bytes()[:16])
    if kind == "pdf":
        return ingest_pdf(Path(path), document_id)
    return ingest_image(Path(path), document_id)
