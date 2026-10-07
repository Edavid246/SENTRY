"""On-prem LLM provider stub (SPEC 8.1, docs/STUBS.md).

LocalVLLMProvider occupies the LLMProvider slot the on-prem profile fills in
later. It is deliberately inert: every call fails closed with
ProviderNotConfiguredError, and the gateway never papers over that failure
with the demo response cache.
"""

from app.ai_gateway.base import LLMRequest, LLMResult, ProviderNotConfiguredError


class LocalVLLMProvider:
    provider_name = "local_vllm"

    def __init__(self, *, base_url: str, model: str) -> None:
        self._base_url = base_url
        self._model = model

    def complete(self, request: LLMRequest) -> LLMResult:
        raise ProviderNotConfiguredError(
            "LocalVLLMProvider is a stub (docs/STUBS.md); "
            "the on-prem LLM is not part of the demo build"
        )
