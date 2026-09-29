"""Economic calendar service composition and public API."""

from services.economic_calendar.models import CalendarEvent, CalendarResult
from services.economic_calendar.providers.base import CalendarProviderError
from services.economic_calendar.providers.bls import BlsCalendarProvider
from services.economic_calendar.service import (
    CalendarService,
    CalendarUnavailable,
    parse_filter_values,
    parse_iso_date,
)
from services.economic_calendar.store import EconomicCalendarStore


economic_calendar_service = CalendarService(
    provider=BlsCalendarProvider(),
    store=EconomicCalendarStore(),
)

__all__ = [
    "BlsCalendarProvider",
    "CalendarEvent",
    "CalendarProviderError",
    "CalendarResult",
    "CalendarService",
    "CalendarUnavailable",
    "EconomicCalendarStore",
    "economic_calendar_service",
    "parse_filter_values",
    "parse_iso_date",
]
