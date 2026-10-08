import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.extract.parse import parse_date, parse_number

LIST_KEYS = {
    "results": "test_name",
    "investigations": "test_name",
    "medications": "name",
    "discharge_medications": "name",
}
SKIP_KEYS = {"document_type"}


def empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, dict):
        return all(empty(x) for x in v.values())
    if isinstance(v, list):
        return all(empty(x) for x in v)
    return False


def fold(s) -> str:
    return re.sub(r"[^a-z0-9%]+", "", str(s).lower())


def same(expected, predicted, key: str = "") -> bool:
    if empty(expected) or empty(predicted):
        return empty(expected) and empty(predicted)
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        p = parse_number(str(predicted)) if not isinstance(predicted, (int, float)) else float(predicted)
        if p is None:
            return False
        return abs(p - expected) <= max(1e-9, abs(expected) * 0.01)
    if key.endswith(("_on", "date")) or key in ("date",):
        de, dp = parse_date(str(expected)), parse_date(str(predicted))
        if de and dp:
            return de == dp
    fe, fp = fold(expected), fold(predicted)
    if fe == fp:
        return True
    return fuzz.ratio(fe, fp) >= 90


@dataclass
class Score:
    expected: int = 0
    predicted: int = 0
    correct: int = 0
    misses: list[str] = field(default_factory=list)

    def add(self, other: "Score"):
        self.expected += other.expected
        self.predicted += other.predicted
        self.correct += other.correct
        self.misses += other.misses

    @property
    def precision(self) -> float:
        return self.correct / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.correct / self.expected if self.expected else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def _scalar(path: str, e, p, key: str) -> Score:
    s = Score()
    if not empty(e):
        s.expected = 1
    if not empty(p):
        s.predicted = 1
    if not empty(e) and not empty(p) and same(e, p, key):
        s.correct = 1
    elif not empty(e) or not empty(p):
        s.misses.append(f"{path}: expected={e!r} got={p!r}")
    return s


def _align(expected: list, predicted: list, keyfn, threshold: float) -> list[tuple]:
    pairs, used = [], set()
    for e in expected:
        best, bi = 0.0, -1
        for i, p in enumerate(predicted):
            if i in used:
                continue
            score = fuzz.ratio(fold(keyfn(e)), fold(keyfn(p)))
            if score > best:
                best, bi = score, i
        if bi >= 0 and best >= threshold:
            used.add(bi)
            pairs.append((e, predicted[bi]))
        else:
            pairs.append((e, None))
    for i, p in enumerate(predicted):
        if i not in used:
            pairs.append((None, p))
    return pairs


def compare(expected, predicted, path: str = "") -> Score:
    total = Score()
    if isinstance(expected, dict):
        for k, ev in expected.items():
            if k in SKIP_KEYS:
                continue
            pv = (predicted or {}).get(k) if isinstance(predicted, dict) else None
            sub = f"{path}.{k}" if path else k
            if isinstance(ev, list):
                total.add(_compare_list(sub, k, ev, pv or []))
            elif isinstance(ev, dict):
                total.add(compare(ev, pv or {}, sub))
            else:
                total.add(_scalar(sub, ev, pv, k))
        return total
    return _scalar(path, expected, predicted, path)


def _compare_list(path: str, key: str, ev: list, pv: list) -> Score:
    total = Score()
    ev = [x for x in ev if not empty(x)]
    pv = [x for x in pv if not empty(x)]
    if key in LIST_KEYS:
        name = LIST_KEYS[key]
        for e, p in _align(ev, pv, lambda x: x.get(name, "") if isinstance(x, dict) else x, 60):
            label = f"{path}[{(e or p).get(name, '')}]"
            if e is None:
                total.add(_unexpected(label, p))
            elif p is None:
                total.add(compare(e, {}, label))
            else:
                total.add(compare(e, p, label))
        return total
    for e, p in _align(ev, pv, lambda x: x, 70):
        total.add(_scalar(f"{path}[]", e, p, key))
    return total


def _unexpected(label: str, p: dict) -> Score:
    s = Score()
    for k, v in p.items():
        if not empty(v):
            s.predicted += 1
            s.misses.append(f"{label}.{k}: unexpected {v!r}")
    return s
