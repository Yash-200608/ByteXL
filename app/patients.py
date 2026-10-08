import random
import re
import uuid
from datetime import datetime, timezone

from app.store import get_repository

ABHA_NUMBER_RE = re.compile(r"^\d{2}-\d{4}-\d{4}-\d{4}$")
ABHA_ADDRESS_RE = re.compile(r"^[a-z0-9][a-z0-9._]{2,30}[a-z0-9]@(abdm|sbx)$")

_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_digit(digits: str) -> int:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return _INV[c]


def verhoeff_valid(digits: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def format_abha(digits: str) -> str:
    return f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}-{digits[10:14]}"


def generate_abha_number(rng: random.Random | None = None) -> str:
    rng = rng or random.SystemRandom()
    body = "91" + "".join(str(rng.randint(0, 9)) for _ in range(11))
    return format_abha(body + str(verhoeff_digit(body)))


def valid_abha_number(value: str) -> bool:
    if not ABHA_NUMBER_RE.match(value or ""):
        return False
    return verhoeff_valid(value.replace("-", ""))


def generate_abha_address(name: str, rng: random.Random | None = None) -> str:
    rng = rng or random.SystemRandom()
    slug = re.sub(r"[^a-z0-9]+", ".", (name or "user").lower()).strip(".")[:20] or "user"
    return f"{slug}{rng.randint(1000, 9999)}@abdm"


def valid_abha_address(value: str) -> bool:
    return bool(ABHA_ADDRESS_RE.match((value or "").lower()))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_patient(name: str, sex: str | None = None, birth_year: int | None = None) -> dict:
    doc = {
        "_id": f"pat_{uuid.uuid4().hex[:12]}",
        "name": name.strip(),
        "sex": sex,
        "birth_year": birth_year,
        "abha_number": generate_abha_number(),
        "abha_address": generate_abha_address(name),
        "abha_linked": False,
        "abha_mock": True,
        "created_at": now(),
    }
    return get_repository().insert("patients", doc)


def link_abha(patient_id: str, abha_number: str, abha_address: str | None = None) -> dict:
    if not valid_abha_number(abha_number):
        raise ValueError("ABHA number must look like 91-1234-5678-9012 and pass the check digit.")
    if abha_address and not valid_abha_address(abha_address):
        raise ValueError("ABHA address must look like name@abdm.")
    patch = {"abha_number": abha_number, "abha_linked": True, "abha_mock": True, "abha_linked_at": now()}
    if abha_address:
        patch["abha_address"] = abha_address.lower()
    return get_repository().update("patients", patient_id, patch)
