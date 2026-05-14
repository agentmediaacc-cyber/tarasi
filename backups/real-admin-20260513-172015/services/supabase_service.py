from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key


def _env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def get_supabase_config() -> dict[str, str | None]:
    service_key = _env("SUPABASE_SERVICE_ROLE_KEY") or _env("SUPABASE_SERVICE_KEY")
    return {
        "url": _env("SUPABASE_URL"),
        "anon_key": _env("SUPABASE_ANON_KEY"),
        "service_key": service_key,
    }


def get_supabase_config_status() -> dict[str, Any]:
    config = get_supabase_config()
    return {
        "configured": bool(config["url"] and config["anon_key"]),
        "url_exists": bool(config["url"]),
        "anon_key_exists": bool(config["anon_key"]),
        "service_key_exists": bool(config["service_key"]),
    }


def get_supabase_status() -> dict[str, Any]:
    status = get_supabase_config_status()
    missing = []
    if not status["url_exists"]:
        missing.append("url")
    if not status["anon_key_exists"]:
        missing.append("anon_key")
    if not status["service_key_exists"]:
        missing.append("service_key")
    status["missing"] = missing
    return status


def get_supabase_client(use_service_role: bool = False) -> SupabaseClient:
    config = get_supabase_config()
    key = config["service_key"] if use_service_role else config["anon_key"]
    if not config["url"] or not key:
        raise RuntimeError("Supabase environment variables are not configured.")
    return SupabaseClient(config["url"], key)


def _request(path: str, payload: dict[str, Any] | None = None, method: str = "POST", bearer: str | None = None, use_service_role: bool = False) -> dict[str, Any]:
    client = get_supabase_client(use_service_role=use_service_role)
    url = f"{client.url}{path}"
    headers = {
        "apikey": client.key,
        "Content-Type": "application/json",
    }
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    else:
        headers["Authorization"] = f"Bearer {client.key}"
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            message = {"message": raw or str(exc)}
        raise RuntimeError(message.get("msg") or message.get("message") or str(exc)) from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to Supabase: {exc.reason}") from exc


def get_supabase_health() -> dict[str, Any]:
    status = get_supabase_config_status()
    if not status["configured"]:
        return {
            **status,
            "connected": False,
            "error": "Supabase is not fully configured.",
        }
    try:
        _request("/auth/v1/settings", None, method="GET")
        return {
            **status,
            "connected": True,
            "error": None,
        }
    except Exception as exc:
        return {
            **status,
            "connected": False,
            "error": str(exc),
        }


def sign_up(email: str, password: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return _request("/auth/v1/signup", {"email": email, "password": password, "data": metadata}, method="POST")


def sign_in(email: str, password: str) -> dict[str, Any]:
    return _request("/auth/v1/token?grant_type=password", {"email": email, "password": password}, method="POST")


def sign_out(access_token: str) -> None:
    _request("/auth/v1/logout", {}, method="POST", bearer=access_token)


def fetch_user(access_token: str) -> dict[str, Any]:
    return _request("/auth/v1/user", None, method="GET", bearer=access_token)


def oauth_url(provider: str, redirect_to: str) -> str:
    client = get_supabase_client(use_service_role=False)
    query = urlencode({"provider": provider, "redirect_to": redirect_to})
    return f"{client.url}/auth/v1/authorize?{query}"
