from __future__ import annotations

from functools import wraps

MASTER_ADMIN_EMAILS = {"magnus@tarasi.com", "kasera@tarasi.com"}

def is_master_admin_email(email):
    return str(email or "").lower().strip() in MASTER_ADMIN_EMAILS

from typing import Any, Callable

from flask import current_app, flash, redirect, request, session, url_for

from .supabase_service import fetch_user, get_supabase_config_status, get_supabase_status, oauth_url, sign_in, sign_out, sign_up


def current_user() -> dict[str, Any] | None:
    return session.get("user")


def _normalize_email(email: Any) -> str:
    return str(email or "").strip().lower()


def _extract_auth_email(auth_payload: dict[str, Any], user: dict[str, Any]) -> str:
    candidates = [
        user.get("email"),
        user.get("user_metadata", {}).get("email"),
        auth_payload.get("email"),
        auth_payload.get("user_email"),
    ]
    identities = user.get("identities") or []
    for identity in identities:
        if isinstance(identity, dict):
            identity_data = identity.get("identity_data") or {}
            candidates.extend(
                [
                    identity.get("email"),
                    identity_data.get("email"),
                ]
            )
    for candidate in candidates:
        normalized = _normalize_email(candidate)
        if normalized:
            return normalized
    return ""


def save_session(auth_payload: dict[str, Any], provider: str = "email") -> dict[str, Any]:
    user = auth_payload.get("user") or {}
    email = _extract_auth_email(auth_payload, user)

    metadata = user.get("user_metadata", {}) or {}
    account_type = metadata.get("account_type")
    role = metadata.get("role") or "user"
    is_admin = bool(metadata.get("is_admin"))

    if is_master_admin_email(email):
        account_type = "Admin"
        role = "owner"
        is_admin = True
    elif account_type == "Admin":
        is_admin = True
        role = metadata.get("role") or "admin"
    elif account_type == "Driver":
        role = metadata.get("role") or "driver"
    elif not account_type:
        account_type = "Customer"

    profile = {
        "user_id": user.get("id"),
        "email": email,
        "full_name": metadata.get("full_name") or email or "Tarasi user",
        "account_type": account_type,
        "is_admin": is_admin,
        "role": role,
    }

    session["user"] = profile
    if auth_payload.get("access_token"):
        session["access_token"] = auth_payload["access_token"]
    if auth_payload.get("refresh_token"):
        session["refresh_token"] = auth_payload["refresh_token"]
    return profile


def get_login_redirect() -> str:
    user = current_user()
    if not user:
        return url_for("auth.login")

    email = _normalize_email(user.get("email"))
    account_type = user.get("account_type")
    role = user.get("role")
    is_admin = user.get("is_admin") is True

    if account_type == "Admin" or is_admin or is_master_admin_email(email):
        return url_for("admin.dashboard")
    if account_type == "Driver" or role == "driver":
        return url_for("driver.dashboard")

    return url_for("auth.dashboard")


def require_driver(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please login to continue.")
            return redirect(url_for("auth.login", next=request.path))
        if user.get("account_type") != "Driver":
            flash("Driver access only.")
            return redirect(get_login_redirect())
        return view(*args, **kwargs)

    return wrapped


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


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please login to continue.")
            return redirect(url_for("auth.login", next=request.path))

        email = _normalize_email(user.get("email"))
        allowed = (
            user.get("account_type") == "Admin"
            or user.get("is_admin") is True
            or is_master_admin_email(email)
        )

        if not allowed:
            flash("You do not have permission to access this area.")
            return redirect(url_for("auth.login"))

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
        _normalize_email(form_data["email"]),
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
    import os
    import requests
    from flask import session

    email = str(email or "").lower().strip()
    password = str(password or "")

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    anon_key = (
        os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_KEY")
    )

    if not supabase_url or not anon_key:
        return False, "Supabase is not configured."

    try:
        res = requests.post(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers={
                "apikey": anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
            timeout=20,
        )

        if res.status_code >= 400:
            return False, "Login failed. Check your credentials or confirm your email first."

        payload = res.json()
        user = payload.get("user") or {}
        metadata = user.get("user_metadata") or {}

        admin_emails = {"magnus@tarasi.com", "kasera@tarasi.com"}
        is_admin = email in admin_emails or metadata.get("is_admin") is True
        account_type = "Admin" if is_admin else metadata.get("account_type", "Customer")
        role = "owner" if is_admin else metadata.get("role", "user")

        session["user"] = {
            "user_id": user.get("id"),
            "email": email,
            "full_name": metadata.get("full_name") or email,
            "account_type": account_type,
            "role": role,
            "is_admin": bool(is_admin),
        }
        session["access_token"] = payload.get("access_token")
        session["refresh_token"] = payload.get("refresh_token")
        session["provider"] = "email"

        return True, "Login successful."

    except Exception as exc:
        return False, f"Login failed: {exc}"


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
