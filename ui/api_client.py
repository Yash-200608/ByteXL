import os

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")


class ApiError(RuntimeError):
    pass


def _req(method: str, path: str, timeout: float = 30.0, **kw):
    try:
        r = httpx.request(method, f"{API_URL}{path}", timeout=timeout, **kw)
    except httpx.HTTPError as exc:
        raise ApiError(f"Cannot reach the ByteXL API at {API_URL}. Is it running? ({exc.__class__.__name__})") from exc
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:200]
        raise ApiError(str(detail))
    ctype = r.headers.get("content-type", "")
    return r.json() if "json" in ctype else r.content


def get(path: str, **kw):
    return _req("GET", path, **kw)


def post(path: str, **kw):
    return _req("POST", path, **kw)


def health():
    return get("/health", timeout=10)
