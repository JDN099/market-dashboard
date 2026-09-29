"""Interface shared by official economic calendar providers."""

from abc import ABC, abstractmethod


class CalendarProviderError(Exception):
    """Raised when an official calendar provider cannot be read safely."""


class EconomicCalendarProvider(ABC):
    name = "calendar-provider"

    @abstractmethod
    def fetch_events(self):
        """Return normalized events available from the provider."""
