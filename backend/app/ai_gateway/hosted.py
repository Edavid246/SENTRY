"""Hosted LLM provider (SPEC 8.1): Gemini generateContent over HTTPS.

Development profile only. The API key travels in the x-goog-api-key header,
never in the URL, and never appears in exception messages.
"""

import httpx

from app.ai_gateway.base import (
    LLMRequest,
    LLMResult,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TokenUsage,
)

_ROLE_MAP = {"user": "user", "assistant": "model"}


class HostedProvider:
    provider_name = "hosted"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ProviderNotConfiguredError(
                "hosted provider has no API key (set HOSTED_API_KEY or GEMINI_API_KEY)"
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def complete(self, request: LLMRequest) -> LLMResult:
        model = request.model or self._model
        url = f"{self._base_url}/models/{model}:generateContent"
        headers = {"x-goog-api-key": self._api_key, "content-type": "application/json"}
        try:
            response = self._client.post(url, json=self._build_body(request), headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"hosted provider timed out after {self._timeout:g}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"hosted provider unreachable ({type(exc).__name__})"
            ) from exc
        return self._parse(response, model)

    def _build_body(self, request: LLMRequest) -> dict:
        contents: list[dict] = []
        system_parts: list[dict] = []
        if request.system:
            system_parts.append({"text": request.system})
        for message in request.messages:
            if message.role == "system":
                system_parts.append({"text": message.text})
                continue
            contents.append(
                {"role": _ROLE_MAP.get(message.role, "user"), "parts": [{"text": message.text}]}
            )
        body: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_output_tokens,
            },
        }
        if system_parts:
            body["systemInstruction"] = {"parts": system_parts}
        return body

    def _parse(self, response: httpx.Response, model: str) -> LLMResult:
        status = response.status_code
        if status == 429:
            raise ProviderRateLimitError(
                "hosted provider rate limited (HTTP 429)",
                retry_after=_retry_after_seconds(response),
            )
        if status >= 500:
            raise ProviderUnavailableError(f"hosted provider returned HTTP {status}")
        if status >= 400:
            raise ProviderError(
                f"hosted provider returned HTTP {status}: {_safe_detail(response, self._api_key)}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderResponseError("hosted provider returned non-JSON body") from exc
        text = _candidate_text(data)
        if not text:
            raise ProviderResponseError("hosted provider response contained no candidate text")
        usage_data = data.get("usageMetadata") or {}
        return LLMResult(
            text=text,
            provider=self.provider_name,
            model=model,
            model_version=str(data.get("modelVersion") or ""),
            usage=TokenUsage(
                prompt_tokens=int(usage_data.get("promptTokenCount") or 0),
                completion_tokens=int(usage_data.get("candidatesTokenCount") or 0),
                total_tokens=int(usage_data.get("totalTokenCount") or 0),
            ),
        )


def _candidate_text(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(str(part.get("text") or "") for part in parts)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return None


def _safe_detail(response: httpx.Response, api_key: str) -> str:
    try:
        payload = response.json()
        detail = str(((payload.get("error") or {}).get("message")) or "")
    except ValueError:
        detail = ""
    detail = " ".join(detail.split())
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    detail = detail[:200]
    return detail or "no error detail"
