"""LLM client – thin wrapper around the Anthropic SDK."""

from __future__ import annotations

import logging

import anthropic

from llm_judge.config import Settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper that calls the configured LLM provider to produce judge verdicts."""

    def __init__(self, config: Settings) -> None:
        self._config = config
        provider = config.judge_llm_provider.lower()
        if provider != "anthropic":
            raise NotImplementedError(
                f"Provider {provider!r} is not supported; only 'anthropic' is implemented."
            )
        kwargs: dict = {"api_key": config.judge_llm_api_key}
        if config.judge_llm_base_url:
            kwargs["base_url"] = config.judge_llm_base_url
        self._client = anthropic.Anthropic(**kwargs)
        logger.debug(
            "LLMClient initialised with provider=%s model=%s api_key=...%s",
            provider,
            config.judge_model,
            config.masked_api_key()[-4:],
        )

    def judge(self, system: str, user: str) -> str:
        """Send a judge request and return the raw text response."""
        response = self._client.messages.create(
            model=self._config.judge_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
