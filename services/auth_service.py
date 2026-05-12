from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import current_app, flash, redirect, request, session, url_for

from .supabase_service import fetch_user, get_supabase_config_status, get_supabase_status, oauth_url, sign_in, sign_out, sign_up


def current_user() -> dict[str, Any] | None:
    return session.get("user")


def save_session(auth_payload: dict[str, Any], provider: str = "email") -> dict[str, Any]:
    user = auth_payload.get("user") or {}
    profile = {
        "user_id": user.get("id"),
        "email": user.get("email"),
        "full_name": user.get("user_metadata", {}).get("full_name") or user.get("email", "Tarasi user"),
        "account_type": user.get("user_metadata", {}).get("account_type", "Customer"),
    }
    session["user"] = profile
    if auth_payload.get("access_token"):
        session["access_token"] = auth_payload["access_token"]
    if auth_payload.get("refresh_token"):
        session["refresh_token"] = auth_payload["refresh_token"]
    return profile


def clear_session() -> None:
    session.pop("user", None)
    session.pop("access_token", None)
    session.pop("refresh_token", None)


def require_auth(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please login to continue.")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def register_user(form_data: dict[str, Any]) -> tuple[bool, str]:
    if form_data.get("password") != form_data.get("confirm_password"):
        return False, "Passwords do not match."
    if not form_data.get("full_name") or not form_data.get("email") or not form_data.get("phone") or not form_data.get("password"):
        return False, "Please complete all required registration fields."
    if not get_supabase_config_status()["configured"]:
        return False, "Supabase setup is required before registration can be used."
    payload = sign_up(
        form_data["email"],
        form_data["password"],
        {
            "full_name": form_data["full_name"],
            "phone": form_data["phone"],
            "account_type": form_data["account_type"],
        },
    )
    if payload.get("session"):
        save_session(payload["session"] | {"user": payload.get("user", {})}, provider="email")
        return True, "Registration successful."
    return True, "Registration created. Please confirm your email before logging in."


def login_user(email: str, password: str) -> tuple[bool, str]:
    if not email or not password:
        return False, "Email and password are required."
    if not get_supabase_config_status()["configured"]:
        return False, "Supabase setup is required before login can be used."
    try:
        payload = sign_in(email, password)
        save_session(payload, provider="email")
        return True, "Welcome back to Tarasi."
    except Exception:
        return False, "Login failed. Check your credentials or confirm your email first."


def logout_user() -> tuple[bool, str]:
    access_token = session.get("access_token")
    try:
        if access_token:
            sign_out(access_token)
    except Exception:
        current_app.logger.info("Supabase logout call failed; clearing local session.")
    clear_session()
    return True, "You have been logged out."


def get_oauth_redirect(provider: str, redirect_to: str) -> str:
    return oauth_url(provider, redirect_to)


def establish_oauth_session(access_token: str, refresh_token: str | None, provider: str) -> tuple[bool, str]:
    if not access_token:
        return False, "No access token was returned from Supabase."
    user = fetch_user(access_token)
    save_session({"access_token": access_token, "refresh_token": refresh_token, "user": user}, provider=provider)
    return True, "OAuth login completed."
