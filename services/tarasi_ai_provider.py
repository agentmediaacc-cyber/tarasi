from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SYSTEM_PROMPT_PATH = Path("data/bot_knowledge/tarasi_ai_system_prompt.txt")

LAST_AI_STATUS: dict[str, Any] = {
    "provider": os.getenv("TARASI_AI_PROVIDER", "ollama").strip().lower() or "ollama",
    "available": False,
    "model": "",
    "fallback_mode": "template",
    "last_error": "",
    "response_time_ms": 0,
    "last_check": 0,
}


def _load_system_prompt() -> str:
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return (
            "You are Tarasi Assistant, a premium Namibia transport concierge. Use backend facts only. "
            "Never invent prices, drivers, invoices, tickets, or availability."
        )


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 3) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    # 3 second strict timeout for bot responsiveness
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _safe_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=True)
    except Exception:
        return "{}"


def _prompt_payload(
    user_message: str,
    system_context: dict[str, Any],
    conversation_state: dict[str, Any],
    business_result: dict[str, Any],
) -> str:
    system_prompt = _load_system_prompt()
    return (
        f"{system_prompt}\n\n"
        f"User message: {user_message}\n"
        f"System context: {_safe_json(system_context)}\n"
        f"Conversation state: {_safe_json(conversation_state)}\n"
        f"Business result facts: {_safe_json(business_result)}\n\n"
        "Rewrite the business facts into one short premium human reply. "
        "Use only the provided facts. "
        "Do not invent prices, drivers, bookings, invoices, payment status, ticket numbers, or availability. "
        "Ask one next best question. "
        "Return plain text only."
    )


def _configured_provider() -> tuple[str, str]:
    provider = os.getenv("TARASI_AI_PROVIDER", "ollama").strip().lower() or "ollama"
    model = {
        "ollama": os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip() or "qwen2.5:7b",
        "openrouter": os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free",
        "gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
    }.get(provider, "")
    return provider, model


def _mark_status(provider: str, model: str, available: bool, fallback_mode: str, last_error: str = "", response_time_ms: int = 0) -> None:
    LAST_AI_STATUS.update(
        {
            "provider": provider,
            "model": model,
            "available": available,
            "fallback_mode": fallback_mode,
            "last_error": last_error,
            "response_time_ms": response_time_ms,
            "last_check": time.time(),
        }
    )


def _call_ollama(prompt: str, model: str) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4},
    }
    data = _post_json(f"{base_url}/api/generate", payload)
    return str(data.get("response") or "").strip()


def _call_openrouter(prompt: str, model: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _load_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    data = _post_json(
        "https://openrouter.ai/api/v1/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    choices = data.get("choices") or []
    if not choices:
        return ""
    return str((((choices[0] or {}).get("message") or {}).get("content")) or "").strip()


def _call_gemini(prompt: str, model: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }
    data = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        payload,
    )
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    return " ".join(str(part.get("text") or "").strip() for part in parts).strip()


def generate_human_reply(
    user_message: str,
    system_context: dict[str, Any],
    conversation_state: dict[str, Any],
    business_result: dict[str, Any],
) -> dict[str, Any]:
    provider, model = _configured_provider()
    prompt = _prompt_payload(user_message, system_context, conversation_state, business_result)
    start_time = time.time()
    try:
        if provider == "ollama":
            text = _call_ollama(prompt, model)
        elif provider == "openrouter":
            text = _call_openrouter(prompt, model)
        elif provider == "gemini":
            text = _call_gemini(prompt, model)
        else:
            raise RuntimeError(f"Unsupported AI provider: {provider}")
        
        duration = int((time.time() - start_time) * 1000)
        if not text:
            raise RuntimeError("AI provider returned an empty response.")
        
        _mark_status(provider, model, True, "ai", "", duration)
        return {"ok": True, "reply": text, "provider": provider, "model": model, "fallback_mode": "ai", "error": "", "response_time_ms": duration}
    except (HTTPError, URLError, RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        duration = int((time.time() - start_time) * 1000)
        _mark_status(provider, model, False, "template", str(exc), duration)
        return {"ok": False, "reply": "", "provider": provider, "model": model, "fallback_mode": "template", "error": str(exc), "response_time_ms": duration}


def get_ai_status(force_check: bool = False) -> dict[str, Any]:
    provider, model = _configured_provider()
    
    # If forced or first time or provider changed, do a lightweight health check
    now = time.time()
    if force_check or LAST_AI_STATUS.get("provider") != provider or (now - LAST_AI_STATUS.get("last_check", 0)) > 300:
        start_time = time.time()
        try:
            if provider == "ollama":
                base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
                request = Request(f"{base_url}/api/tags", method="GET")
                with urlopen(request, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    models = [m.get("name") for m in data.get("models", [])]
                    if model not in models and model + ":latest" not in models:
                        # If model not found, we still mark available if API works, but with error
                        _mark_status(provider, model, True, "ai", f"Model {model} not found in Ollama tags", int((time.time() - start_time) * 1000))
                    else:
                        _mark_status(provider, model, True, "ai", "", int((time.time() - start_time) * 1000))
            else:
                # For others, just use last known or do a dummy check if needed
                # Here we just keep the status or rely on the next generation to update it
                _mark_status(provider, model, LAST_AI_STATUS.get("available", False), LAST_AI_STATUS.get("fallback_mode", "template"), LAST_AI_STATUS.get("last_error", ""))
        except Exception as exc:
            _mark_status(provider, model, False, "template", str(exc), int((time.time() - start_time) * 1000))

    return {
        "provider": LAST_AI_STATUS.get("provider"),
        "model": LAST_AI_STATUS.get("model"),
        "available": LAST_AI_STATUS.get("available"),
        "fallback": LAST_AI_STATUS.get("fallback_mode") == "template",
        "last_error": LAST_AI_STATUS.get("last_error"),
        "response_time_ms": LAST_AI_STATUS.get("response_time_ms"),
    }

