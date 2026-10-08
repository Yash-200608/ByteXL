from typing import Literal

from pydantic import BaseModel, Field


class OcrLine(BaseModel):
    text: str
    confidence: float = 1.0
    box: list[float] = Field(min_length=4, max_length=4)


class PageData(BaseModel):
    index: int
    width: int
    height: int
    image_path: str
    source: Literal["text_layer", "ocr"]
    lines: list[OcrLine] = []
    deskew_angle: float = 0.0
    duration_s: float = 0.0

    @property
    def mean_confidence(self) -> float:
        if not self.lines:
            return 0.0
        return sum(line.confidence for line in self.lines) / len(self.lines)

    @property
    def text(self) -> str:
        return layout_text(self.lines)


def layout_text(lines: list[OcrLine], row_tolerance: float = 0.55) -> str:
    if not lines:
        return ""
    items = sorted(lines, key=lambda l: ((l.box[1] + l.box[3]) / 2, l.box[0]))
    rows: list[list[OcrLine]] = []
    for line in items:
        cy = (line.box[1] + line.box[3]) / 2
        h = max(1.0, line.box[3] - line.box[1])
        if rows:
            last = rows[-1]
            ly = sum((l.box[1] + l.box[3]) / 2 for l in last) / len(last)
            lh = max(1.0, sum(l.box[3] - l.box[1] for l in last) / len(last))
            if abs(cy - ly) <= row_tolerance * min(h, lh):
                last.append(line)
                continue
        rows.append([line])
    out = []
    for row in rows:
        row.sort(key=lambda l: l.box[0])
        out.append("   ".join(l.text.strip() for l in row if l.text.strip()))
    return "\n".join(r for r in out if r)
