"""Provider-independent economic calendar data models."""

from dataclasses import dataclass
from datetime import datetime, timezone


def utc_iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    provider: str
    name: str
    country: str
    currency: str
    scheduled_at: datetime
    importance: str
    reporting_period: str | None
    actual: str | None
    forecast: str | None
    previous: str | None
    source: str
    source_url: str
    status: str = "scheduled"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "country": self.country,
            "currency": self.currency,
            "scheduled_at": utc_iso(self.scheduled_at),
            "importance": self.importance,
            "reporting_period": self.reporting_period,
            "actual": self.actual,
            "forecast": self.forecast,
            "previous": self.previous,
            "source": self.source,
            "source_url": self.source_url,
            "status": self.status,
        }


@dataclass(frozen=True)
class CalendarResult:
    events: list[CalendarEvent]
    providers: list[str]
    last_updated: datetime | None
    stale: bool = False
    warning: str | None = None
