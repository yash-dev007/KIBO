from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ProactiveEvent:
    type: str
    source_data: dict[str, Any]


@dataclass(frozen=True)
class ProactiveDecision:
    approved: bool
    reason: str
    event: ProactiveEvent


@dataclass(frozen=True)
class ProactiveUtterance:
    text: str
    category: str
    priority: str
    expiry: datetime
    delivery_mode: str
    bypass_cap: bool
