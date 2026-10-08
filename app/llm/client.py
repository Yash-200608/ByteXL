import base64
import io
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TypeVar

import httpx
from PIL import Image
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class LLMResult:
    obj: BaseModel | None
    attempts: int
    errors: list[str] = field(default_factory=list)
    model: str = ""
    duration_s: float = 0.0
    raw: str = ""


def encode_image(image: Image.Image, max_side: int) -> str:
    im = image.convert("RGB")
    if max(im.size) > max_side:
        im = im.copy()
        im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _short_errors(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:12]]


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        s = get_settings()
        self.base_url = (base_url or s.ollama_url).rstrip("/")
        self.settings = s

    def is_up(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/api/tags", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def models(self) -> list[str]:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return [m["name"] for m in r.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            return []

    def chat(self, model: str, messages: list[dict], schema: dict | None = None, num_predict: int | None = None) -> str:
        options = {"temperature": self.settings.llm_temperature, "num_ctx": self.settings.llm_num_ctx}
        if num_predict:
            options["num_predict"] = num_predict
        body = {"model": model, "messages": messages, "stream": False, "options": options, "keep_alive": "30m"}
        if schema is not None:
            body["format"] = schema
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.settings.llm_timeout_s)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(str(exc)) from exc
        if r.status_code != 200:
            raise LLMUnavailable(f"ollama {r.status_code}: {r.text[:200]}")
        return r.json()["message"]["content"]

    def structured(
        self,
        model: str,
        schema_model: type[M],
        system: str,
        user: str,
        images: list[Image.Image] | None = None,
        extra_check=None,
        num_predict: int | None = None,
    ) -> LLMResult:
        start = time.time()
        user_msg: dict = {"role": "user", "content": user}
        if images:
            user_msg["images"] = [encode_image(im, self.settings.vision_max_side) for im in images]
        messages = [{"role": "system", "content": system}, user_msg]
        schema = schema_model.model_json_schema()
        errors: list[str] = []
        raw = ""
        for attempt in (1, 2):
            raw = self.chat(model, messages, schema=schema, num_predict=num_predict)
            problems: list[str] = []
            obj = None
            try:
                obj = schema_model.model_validate(json.loads(raw))
            except json.JSONDecodeError as exc:
                problems = [f"invalid JSON: {exc}"]
            except ValidationError as exc:
                problems = _short_errors(exc)
            if obj is not None and extra_check is not None:
                problems = list(extra_check(obj))
            if not problems:
                return LLMResult(obj, attempt, errors, model, time.time() - start, raw)
            errors.extend(problems)
            log.info("LLM output rejected (attempt %s): %s", attempt, problems)
            messages = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": "Your previous answer was rejected for these reasons:\n- "
                    + "\n- ".join(problems)
                    + "\nReturn corrected JSON only, following the same schema and rules.",
                },
            ]
        return LLMResult(None, 2, errors, model, time.time() - start, raw)


_client = None
_lock = threading.Lock()


def get_llm():
    global _client
    with _lock:
        if _client is None:
            _client = OllamaClient()
        return _client


def set_llm(client) -> None:
    global _client
    with _lock:
        _client = client
