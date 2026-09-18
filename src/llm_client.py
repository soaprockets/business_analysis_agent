"""
Unified LLM client supporting Anthropic and OpenAI-compatible providers.

OpenAI-compatible mode is used for ByteDance Volcano Engine / Doubao / Ark,
which exposes an OpenAI-style chat completions endpoint.
"""

import os
from typing import Any


# Provider-level output token ceilings.  These are independent of the user's
# requested max_tokens and prevent the underlying API from rejecting the call.
# Values are current as of 2026-09-19 and represent the largest safe value for
# the default model of each provider family.
_PROVIDER_OUTPUT_LIMITS: dict[str, int] = {
    "anthropic": 8192,          # Claude 3.5/3.7 Sonnet default output limit
    "openai": 128000,           # o-series supports up to 100k; keep user request
    "volcano-agent-plan": 32768,  # Ark Agent Plan max_completion_tokens ceiling
}


class LLMClient:
    """
    A thin wrapper around Anthropic and OpenAI-compatible LLM APIs.

    Configuration is read from environment variables:
      - LLM_PROVIDER: "anthropic" or "openai" (default: "anthropic")
      - ANTHROPIC_API_KEY / OPENAI_API_KEY / DOUBAO_API_KEY: API key
      - ANTHROPIC_MODEL / OPENAI_MODEL / DOUBAO_MODEL: model name
      - ANTHROPIC_BASE_URL / OPENAI_BASE_URL / DOUBAO_BASE_URL: custom base URL

    For ByteDance Volcano Ark, choose one of the following:

    1) Anthropic-compatible endpoint (uses ANTHROPIC_API_KEY):
       LLM_PROVIDER=anthropic
       ANTHROPIC_API_KEY=ark-...
       ANTHROPIC_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/anthropic
       ANTHROPIC_MODEL=ark-code-latest

    2) OpenAI-compatible endpoint (uses OPENAI_API_KEY):
       LLM_PROVIDER=openai
       OPENAI_API_KEY=ark-...
       OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
       OPENAI_MODEL=doubao-pro-32k
    """

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if self.provider == "anthropic":
            import anthropic

            api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "Anthropic provider requires ANTHROPIC_API_KEY or api_key"
                )
            base_url = self.base_url or os.getenv("ANTHROPIC_BASE_URL")
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = anthropic.Anthropic(**kwargs)
        elif self.provider == "volcano-agent-plan":
            # ByteDance Volcano Ark "Agent Plan" uses an OpenAI-compatible endpoint.
            from openai import OpenAI

            api_key = (
                self.api_key
                or os.getenv("VOLCANO_AGENT_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or os.getenv("DOUBAO_API_KEY")
            )
            if not api_key:
                raise ValueError(
                    "Volcano Agent Plan provider requires VOLCANO_AGENT_API_KEY / "
                    "OPENAI_API_KEY / DOUBAO_API_KEY or api_key"
                )
            base_url = (
                self.base_url
                or os.getenv("VOLCANO_AGENT_BASE_URL")
                or "https://ark.cn-beijing.volces.com/api/plan/v3"
            )
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = OpenAI(**kwargs)
        elif self.provider == "openai":
            from openai import OpenAI

            api_key = self.api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DOUBAO_API_KEY")
            if not api_key:
                raise ValueError(
                    "OpenAI-compatible provider requires OPENAI_API_KEY / DOUBAO_API_KEY or api_key"
                )
            base_url = self.base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("DOUBAO_BASE_URL")
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = OpenAI(**kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        return self._client

    def _get_model(self) -> str:
        if self.model:
            return self.model
        if self.provider == "anthropic":
            return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        if self.provider == "volcano-agent-plan":
            return (
                os.getenv("VOLCANO_AGENT_MODEL")
                or os.getenv("OPENAI_MODEL")
                or os.getenv("DOUBAO_MODEL")
                or "ark-code-latest"
            )
        return os.getenv("OPENAI_MODEL") or os.getenv("DOUBAO_MODEL") or "gpt-4o"

    def _normalize_max_tokens(self, max_tokens: int) -> int:
        """Clamp max_tokens to the provider's supported output ceiling."""
        ceiling = _PROVIDER_OUTPUT_LIMITS.get(self.provider)
        if ceiling is None:
            return max_tokens
        if max_tokens > ceiling:
            print(
                f"   ⚠️ 请求 max_tokens={max_tokens} 超过 {self.provider} "
                f"上限 {ceiling}，已自动调整为 {ceiling}"
            )
            return ceiling
        return max_tokens

    def chat_completion(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 128000,
        temperature: float = 0.2,
    ) -> str:
        """Call the configured LLM and return the text content."""
        client = self._get_client()
        model = self._get_model()
        effective_max = self._normalize_max_tokens(max_tokens)

        if self.provider == "anthropic":
            response = client.messages.create(
                model=model,
                max_tokens=effective_max,
                system=system or "You are a helpful assistant.",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    return block.text
            raise ValueError(f"No text block found in LLM response: {response.content}")

        # OpenAI-compatible path (includes ByteDance Volcano / Doubao)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Volcano Ark Agent Plan uses max_completion_tokens to control the total
        # answer length; max_tokens defaults to 4096 there and can truncate long
        # structured outputs. For standard OpenAI-compatible providers we keep
        # the traditional max_tokens parameter.
        if self.provider == "volcano-agent-plan":
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_completion_tokens=effective_max,
                    temperature=temperature,
                )
            except TypeError:
                # Older OpenAI SDK may not support max_completion_tokens
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=effective_max,
                    temperature=temperature,
                )
        else:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=effective_max,
                temperature=temperature,
            )

        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            print(
                "   ⚠️ LLM 输出因长度限制被截断，请检查 max_tokens/max_completion_tokens 或缩短 prompt"
            )

        content = choice.message.content
        if content is None:
            raise ValueError("LLM returned empty content")
        return content
