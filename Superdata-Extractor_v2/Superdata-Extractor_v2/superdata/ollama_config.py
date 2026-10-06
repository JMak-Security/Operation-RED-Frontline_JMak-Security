"""Ollama connectivity helpers — re-exports from llm_client."""

from __future__ import annotations

from .llm_client import (  # noqa: F401
    DEFAULT_OLLAMA_BASE,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OPENAI_BASE,
    check_llm_reachable,
    check_ollama_reachable,
    configure_llm,
    configure_ollama,
    detect_provider,
    normalize_model,
    normalize_ollama_model,
    ollama_model_tag,
    resolve_api_key,
)
