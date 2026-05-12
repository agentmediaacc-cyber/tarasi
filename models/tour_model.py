from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TourModel:
    slug: str
    title: str
    destination: str = ""
    duration: str = ""
