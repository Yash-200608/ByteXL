import re

from rapidfuzz import fuzz

from app.config import get_settings
from app.ingest.models import OcrLine, PageData
from app.schemas import SourceBox


def norm(s: str) -> str:
    s = s.lower().replace(",", "")
    s = re.sub(r"[^a-z0-9.%/<>\-ऀ-ॿ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class Locator:
    def __init__(self, pages: list[PageData]):
        self.items: list[tuple[int, OcrLine, str]] = []
        for p in pages:
            for line in p.lines:
                self.items.append((p.index, line, norm(line.text)))

    def _score(self, value: str, text: str) -> float:
        if not value or not text:
            return 0.0
        if re.fullmatch(r"[<>]?-?\d+(\.\d+)?", value):
            pattern = r"(?<![\d.])" + re.escape(value.lstrip("<>")) + r"(?![\d])"
            return 100.0 if re.search(pattern, text) else 0.0
        if len(value) <= 3:
            return 100.0 if re.search(r"(?<![a-z0-9])" + re.escape(value) + r"(?![a-z0-9])", text) else 0.0
        if len(text) < 0.8 * len(value):
            return float(fuzz.ratio(value, text))
        return float(fuzz.partial_ratio(value, text))

    def _row(self, anchor: tuple[int, OcrLine]) -> list[int]:
        page, line = anchor
        cy = (line.box[1] + line.box[3]) / 2
        h = max(1.0, line.box[3] - line.box[1])
        out = []
        for i, (p, other, _) in enumerate(self.items):
            if p != page:
                continue
            oy = (other.box[1] + other.box[3]) / 2
            if abs(oy - cy) <= 0.6 * max(h, other.box[3] - other.box[1]):
                out.append(i)
        return out

    def locate(self, value, anchor: tuple[int, OcrLine] | None = None) -> tuple[float, tuple[int, OcrLine] | None, SourceBox | None]:
        if value is None:
            return 0.0, None, None
        v = norm(str(value) if not isinstance(value, float) else f"{value:g}")
        if not v:
            return 0.0, None, None
        indices = self._row(anchor) if anchor else []
        best = self._best(v, indices) if indices else (0.0, -1)
        if best[0] < get_settings().box_match_min_score:
            best = self._best(v, range(len(self.items)))
        score, idx = best
        if idx < 0 or score <= 0:
            return 0.0, None, None
        page, line, text = self.items[idx]
        return score / 100.0, (page, line), self._sub_box(page, line, text, v)

    def _best(self, v: str, indices) -> tuple[float, int]:
        best = (0.0, -1)
        best_len = 10**9
        for i in indices:
            s = self._score(v, self.items[i][2])
            ln = len(self.items[i][2])
            if s > best[0] or (s == best[0] and s > 0 and ln < best_len):
                best = (s, i)
                best_len = ln
        return best

    @staticmethod
    def _sub_box(page: int, line: OcrLine, text: str, v: str) -> SourceBox:
        x0, y0, x1, y1 = line.box
        start = text.find(v)
        if start >= 0 and len(text) > 0 and len(v) < len(text):
            w = x1 - x0
            sx0 = x0 + w * start / len(text)
            sx1 = x0 + w * (start + len(v)) / len(text)
            pad = 0.01 * w
            return SourceBox(page=page, x0=round(max(x0, sx0 - pad), 1), y0=round(y0, 1), x1=round(min(x1, sx1 + pad), 1), y1=round(y1, 1))
        return SourceBox(page=page, x0=round(x0, 1), y0=round(y0, 1), x1=round(x1, 1), y1=round(y1, 1))


def field_confidence(match: float, ocr_conf: float, retried: bool, low: bool) -> float:
    s = get_settings()
    if match >= s.box_match_min_score / 100.0:
        conf = 0.55 * match + 0.45 * ocr_conf
    else:
        conf = 0.35
    if retried:
        conf *= 0.85
    if low:
        conf = min(conf, 0.30)
    return round(max(0.0, min(1.0, conf)), 3)
