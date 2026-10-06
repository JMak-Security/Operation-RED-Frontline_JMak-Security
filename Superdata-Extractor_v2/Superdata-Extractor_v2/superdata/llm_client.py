"""
Unified LLM client for Ollama and OpenAI-compatible commercial APIs.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("superdata")

DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"
# Faster Colab default — dolphin:8b often times out on architecture JSON after ORF
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"


def detect_provider(
    api_base: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    explicit = (provider or os.getenv("LLM_PROVIDER") or "").strip().lower()
    if explicit in ("ollama", "openai"):
        return explicit

    base = (api_base or os.getenv("OLLAMA_API_BASE") or DEFAULT_OLLAMA_BASE).rstrip("/")
    key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or ""

    markers = (
        "openai.com",
        "azure.com",
        "openrouter.ai",
        "groq.com",
        "together.xyz",
        "fireworks.ai",
        "googleapis.com",
        "anthropic.com",
        "deepseek.com",
        "mistral.ai",
    )
    if any(m in base for m in markers) or base.endswith("/v1") or "/openai/" in base:
        return "openai"
    if key and "11434" not in base:
        return "openai"
    return "ollama"


def normalize_openai_base(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base[: -len("/chat/completions")]
    return base


def resolve_api_key(api_key: Optional[str] = None) -> str:
    return (
        api_key
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("TARGET_API_KEY")
        or ""
    ).strip()


def openai_headers(api_key: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    if azure_key:
        headers["api-key"] = azure_key
        if "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {azure_key}"
    return headers


def configure_llm(api_base: Optional[str] = None) -> str:
    base = (api_base or os.getenv("OLLAMA_API_BASE") or DEFAULT_OLLAMA_BASE).rstrip("/")
    os.environ["OLLAMA_API_BASE"] = base
    return base


# Back-compat
configure_ollama = configure_llm


def normalize_model(model: str) -> str:
    if model.startswith("ollama/"):
        return model[len("ollama/") :]
    if model.startswith("openai/"):
        return model[len("openai/") :]
    return model


normalize_ollama_model = normalize_model
ollama_model_tag = normalize_model


def check_llm_reachable(
    api_base: Optional[str] = None,
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 5.0,
) -> Tuple[bool, str]:
    import requests

    base = (api_base or os.getenv("OLLAMA_API_BASE") or DEFAULT_OLLAMA_BASE).rstrip("/")
    prov = detect_provider(base, provider, api_key)
    key = resolve_api_key(api_key)

    try:
        if prov == "ollama":
            resp = requests.get(f"{base}/api/tags", timeout=timeout)
            if resp.status_code == 200:
                return True, f"Ollama reachable at {base}"
            return False, f"Ollama returned HTTP {resp.status_code} at {base}"

        check_base = normalize_openai_base(base)
        resp = requests.get(
            f"{check_base}/models",
            headers=openai_headers(key),
            timeout=timeout,
        )
        if resp.status_code == 200:
            return True, f"OpenAI-compatible API reachable at {check_base}"
        if resp.status_code in (401, 403):
            return False, f"API auth failed HTTP {resp.status_code} at {check_base}"
        if resp.status_code == 404 and key:
            return True, f"OpenAI-compatible API configured at {check_base}"
        return False, f"API returned HTTP {resp.status_code} at {check_base}"
    except Exception as exc:
        return False, f"LLM unreachable at {base}: {exc}"


check_ollama_reachable = check_llm_reachable


def chat_completion_sync(
    *,
    api_base: str,
    model: str,
    messages: List[Dict[str, str]],
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    json_mode: bool = False,
    timeout: float = 600.0,
    keep_alive: str = "10m",
) -> str:
    import requests

    prov = detect_provider(api_base, provider, api_key)
    key = resolve_api_key(api_key)
    model_tag = normalize_model(model)
    base = api_base.rstrip("/")

    if prov == "ollama":
        url = f"{base}/api/chat"
        payload: Dict[str, Any] = {
            "model": model_tag,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        headers = {"Content-Type": "application/json"}
    else:
        url = f"{normalize_openai_base(base)}/chat/completions"
        payload = {
            "model": model_tag,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = openai_headers(key)

    logger.info("Calling LLM (%s / %s @ %s)...", prov, model_tag, base)
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if prov == "ollama":
        raw = ((data.get("message") or {}).get("content") or "").strip()
    else:
        choices = data.get("choices") or []
        raw = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    if not raw:
        raise ValueError("LLM returned an empty response.")
    return raw
