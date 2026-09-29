"""Calendar refresh coordination, validation and stale fallback."""

import re
import threading
from datetime import date, datetime, timedelta, timezone

from services.economic_calendar.models import CalendarResult
from services.economic_calendar.providers.base import CalendarProviderError


CALENDAR_FRESHNESS = timedelta(hours=6)
MAX_CALENDAR_RANGE_DAYS = 31
SUPPORTED_COUNTRIES = ("US",)
SUPPORTED_IMPORTANCES = ("high", "medium", "low")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


class CalendarUnavailable(Exception):
    """Raised when neither current nor stale calendar data can be served."""


def parse_iso_date(value, parameter_name):
    text = str(value or "").strip()
    if not DATE_PATTERN.fullmatch(text):
        raise ValueError(f"{parameter_name.capitalize()} date must use YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{parameter_name.capitalize()} date is invalid") from exc


def parse_filter_values(values, supported_values, parameter_name, defaults):
    parsed = []
    for raw_value in values:
        for value in str(raw_value).split(","):
            normalized = value.strip().upper() if parameter_name == "country" else value.strip().lower()
            if normalized and normalized not in parsed:
                parsed.append(normalized)
    if not parsed:
        return tuple(defaults)
    unsupported = [value for value in parsed if value not in supported_values]
    if unsupported:
        raise ValueError(f"Unsupported {parameter_name} filter: {unsupported[0]}")
    return tuple(parsed)


def validate_date_range(start_date, end_date):
    if end_date < start_date:
        raise ValueError("End date must be on or after start date")
    if (end_date - start_date).days + 1 > MAX_CALENDAR_RANGE_DAYS:
        raise ValueError(f"Date range cannot exceed {MAX_CALENDAR_RANGE_DAYS} days")


def current_week(today=None):
    current_date = today or datetime.now(timezone.utc).date()
    start_date = current_date - timedelta(days=current_date.weekday())
    return start_date, start_date + timedelta(days=6)


class CalendarService:
    def __init__(self, provider, store, freshness=CALENDAR_FRESHNESS, now=None):
        self.provider = provider
        self.store = store
        self.freshness = freshness
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._refresh_lock = threading.Lock()

    def get_events(self, start_date, end_date, countries, importances):
        try:
            stored_events = self.store.get_events(
                start_date,
                end_date,
                countries,
                importances,
            )
            state = self.store.get_provider_state(self.provider.name)
        except Exception as exc:
            raise CalendarUnavailable("Economic calendar storage is unavailable") from exc

        if self._is_fresh(state):
            return self._result(stored_events, state, stale=False)

        with self._refresh_lock:
            try:
                with self.store.refresh_lock(self.provider.name):
                    state = self.store.get_provider_state(self.provider.name)
                    if self._is_fresh(state):
                        refreshed_events = self.store.get_events(
                            start_date,
                            end_date,
                            countries,
                            importances,
                        )
                        return self._result(refreshed_events, state, stale=False)
                    return self._refresh(
                        start_date,
                        end_date,
                        countries,
                        importances,
                        stored_events,
                        state,
                    )
            except CalendarUnavailable:
                raise
            except Exception as exc:
                raise CalendarUnavailable("Economic calendar storage is unavailable") from exc

    def _refresh(self, start_date, end_date, countries, importances, stored_events, previous_state):
        attempted_at = self.now().astimezone(timezone.utc)
        try:
            self.store.record_refresh_attempt(self.provider.name, attempted_at)
            events = self.provider.fetch_events()
            self.store.save_refresh(self.provider.name, events, attempted_at)
            refreshed_events = self.store.get_events(
                start_date,
                end_date,
                countries,
                importances,
            )
            state = {
                "last_successful_refresh": attempted_at,
                "last_attempted_refresh": attempted_at,
                "latest_error": None,
            }
            return self._result(refreshed_events, state, stale=False)
        except CalendarProviderError as exc:
            try:
                self.store.record_refresh_failure(
                    self.provider.name,
                    attempted_at,
                    "Official provider refresh failed",
                )
            except Exception:
                pass
            if stored_events:
                return self._result(
                    stored_events,
                    previous_state,
                    stale=True,
                    warning="Official calendar refresh failed; showing stored events.",
                )
            raise CalendarUnavailable("Economic calendar data is unavailable") from exc

    def _is_fresh(self, state):
        if not state or not state.get("last_successful_refresh"):
            return False
        last_refresh = state["last_successful_refresh"]
        if last_refresh.tzinfo is None:
            last_refresh = last_refresh.replace(tzinfo=timezone.utc)
        return self.now().astimezone(timezone.utc) - last_refresh < self.freshness

    def _result(self, events, state, stale, warning=None):
        last_updated = state.get("last_successful_refresh") if state else None
        return CalendarResult(
            events=events,
            providers=[self.provider.name],
            last_updated=last_updated,
            stale=stale,
            warning=warning,
        )
