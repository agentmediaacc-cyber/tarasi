from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserModel:
    full_name: str
    email: str
    phone: str = ""
    town: str = ""
    account_type: str = "Customer"
