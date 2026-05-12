from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SupportModel:
    name: str
    phone: str
    category: str
    message: str
