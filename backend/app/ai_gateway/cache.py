"""Pre-canned LLM response cache (demo only — docs/PRODUCTION_DEBT.md).

The cache key is the SHA-256 of the canonical full request shape:
model, messages (including any system prompt), temperature and
max_output_tokens. A pre-filled entry can therefore never be replayed under
different generation settings without changing the key.
"""

import hashlib
import json
from pathlib import Path

from app.ai_gateway.base import LLMRequest, TokenUsage


class LLMResponseCache:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def key(request: LLMRequest) -> str:
        messages: list[list[str]] = []
        if request.system:
            messages.append(["system", request.system])
        messages.extend([message.role, message.text] for message in request.messages)
        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_output_tokens": request.max_output_tokens,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict | None:
        return self._load().get(key)

    def record(
        self,
        request: LLMRequest,
        *,
        text: str,
        model_version: str = "",
        usage: TokenUsage | None = None,
    ) -> str:
        entries = self._load()
        key = self.key(request)
        entries[key] = {
            "request": {
                "model": request.model,
                "messages": [[message.role, message.text] for message in request.messages],
                "system": request.system,
                "temperature": request.temperature,
                "max_output_tokens": request.max_output_tokens,
            },
            "response": {
                "text": text,
                "model_version": model_version,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(entries, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        # Bytes + replace: LF endings on Windows and no half-written cache file.
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_bytes(blob.encode("utf-8"))
        tmp.replace(self._path)
        return key

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
