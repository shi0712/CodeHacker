"""Configuration and client adapter for OpenAI-compatible LLM endpoints."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse


class TextLLM(Protocol):
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
    ) -> str:
        """Return one text completion."""


@dataclass(frozen=True)
class LLMConfig:
    """LLM settings loaded from environment variables or an optional .env file."""

    api_key: str = field(repr=False)
    base_url: str
    model: str
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(
        cls,
        *,
        dotenv_path: str | Path = ".env",
        load_dotenv_file: bool = True,
    ) -> "LLMConfig":
        dotenv_file = Path(dotenv_path)
        if load_dotenv_file and dotenv_file.is_file():
            try:
                from dotenv import load_dotenv
            except ImportError as exc:  # pragma: no cover - dependency boundary
                raise RuntimeError(
                    'A .env file exists, but python-dotenv is not installed. '
                    'Run: python -m pip install -e ".[llm]"'
                ) from exc
            load_dotenv(dotenv_file, override=False)

        api_key = _first_env("LLM_API_KEY", "OPENAI_API_KEY")
        base_url = _first_env("LLM_BASE_URL", "OPENAI_BASE_URL")
        model = _first_env("LLM_MODEL", "OPENAI_MODEL")

        missing = [
            name
            for name, value in (
                ("LLM_API_KEY", api_key),
                ("LLM_BASE_URL", base_url),
                ("LLM_MODEL", model),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing LLM configuration: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in the values."
            )

        assert api_key is not None
        assert base_url is not None
        assert model is not None
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("LLM_BASE_URL must be an absolute http(s) URL")

        timeout_text = os.getenv("LLM_TIMEOUT_SECONDS", "120")
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise ValueError("LLM_TIMEOUT_SECONDS must be a number") from exc
        if timeout_seconds <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS must be greater than zero")

        return cls(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            model=model,
            timeout_seconds=timeout_seconds,
        )


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


class OpenAICompatibleLLM:
    """Small adapter around the official OpenAI Python client's chat API.

    ``base_url`` makes the adapter usable with providers that implement the
    OpenAI-compatible Chat Completions protocol.
    """

    def __init__(self, config: LLMConfig, *, client: Any | None = None) -> None:
        self.config = config
        if client is not None:
            self._client = client
            return

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency boundary
            raise RuntimeError(
                'The LLM client is not installed. Run: '
                'python -m pip install -e ".[llm]"'
            ) from exc

        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=(
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ),
            temperature=temperature,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM returned an empty text response")
        return content.strip()
