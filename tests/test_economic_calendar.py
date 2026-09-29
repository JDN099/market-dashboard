import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import app
from services.economic_calendar.models import CalendarEvent, CalendarResult
from services.economic_calendar.providers.base import CalendarProviderError
from services.economic_calendar.providers.bls import (
    BLS_SCHEDULE_URL,
    BlsCalendarProvider,
    classify_bls_impact,
    parse_bls_ics,
    unescape_ical_text,
)
from services.economic_calendar.service import (
    CalendarService,
    CalendarUnavailable,
    SUPPORTED_IMPORTANCES,
    parse_filter_values,
    parse_iso_date,
    validate_date_range,
)
from services.economic_calendar.store import EconomicCalendarStore


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bls_calendar.ics"
FIXTURE_TEXT = FIXTURE_PATH.read_text(encoding="utf-8")


def sample_event(event_id="bls-sample", scheduled_at=None, importance="high"):
    return CalendarEvent(
        id=event_id,
        provider="bls",
        name="Consumer Price Index",
        country="US",
        currency="USD",
        scheduled_at=scheduled_at or datetime(2026, 9, 29, 12, 30, tzinfo=timezone.utc),
        importance=importance,
        reporting_period="August 2026",
        actual=None,
        forecast=None,
        previous=None,
        source="Bureau of Labor Statistics",
        source_url="https://www.bls.gov/news.release/cpi.nr0.htm",
    )


class BlsParserTests(unittest.TestCase):
    def test_parser_normalizes_events_and_reporting_periods(self):
        events = parse_bls_ics(FIXTURE_TEXT)
        cpi = next(event for event in events if event.name == "Consumer Price Index")

        self.assertTrue(cpi.id.startswith("bls-"))
        self.assertEqual(cpi.reporting_period, "December 2025")
        self.assertEqual(cpi.country, "US")
        self.assertEqual(cpi.currency, "USD")
        self.assertEqual(cpi.importance, "high")
        self.assertIsNone(cpi.actual)

    def test_eastern_timezone_observes_standard_and_daylight_time(self):
        events = parse_bls_ics(FIXTURE_TEXT)
        cpi = next(event for event in events if event.name == "Consumer Price Index")
        jobs = next(event for event in events if event.name == "Employment Situation")

        self.assertEqual(cpi.scheduled_at.isoformat(), "2026-01-15T13:30:00+00:00")
        self.assertEqual(jobs.scheduled_at.isoformat(), "2026-07-02T12:30:00+00:00")

    def test_folded_lines_escapes_duplicates_and_malformed_events(self):
        events = parse_bls_ics(FIXTURE_TEXT)

        self.assertEqual(len(events), 6)
        duplicates = [event for event in events if event.name == "Producer Price Index"]
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].scheduled_at.minute, 30)
        self.assertEqual(unescape_ical_text(r"value\, one\; two\nnext"), "value, one; two\nnext")

    def test_missing_or_unsafe_urls_use_official_schedule(self):
        events = parse_bls_ics(FIXTURE_TEXT)
        real_earnings = next(event for event in events if event.name == "Real Earnings")
        other_release = next(event for event in events if event.name == "County Employment and Wages")

        self.assertEqual(real_earnings.source_url, BLS_SCHEDULE_URL)
        self.assertEqual(other_release.source_url, BLS_SCHEDULE_URL)

    def test_impact_rules_are_centralized(self):
        high_names = [
            "Consumer Price Index",
            "Employment Situation",
            "Nonfarm Payrolls",
            "Producer Price Index",
            "Employment Cost Index",
        ]
        medium_names = [
            "JOLTS",
            "Productivity and Costs",
            "U.S. Import and Export Price Indexes",
            "Real Earnings",
        ]
        for name in high_names:
            self.assertEqual(classify_bls_impact(name), "high")
        for name in medium_names:
            self.assertEqual(classify_bls_impact(name), "medium")
        self.assertEqual(classify_bls_impact("County Employment and Wages"), "low")

    def test_provider_wraps_network_errors(self):
        def failing_opener(_request, timeout):
            self.assertEqual(timeout, 10)
            raise OSError("network detail")

        provider = BlsCalendarProvider(opener=failing_opener)
        with self.assertRaisesRegex(CalendarProviderError, "BLS calendar feed is unavailable"):
            provider.fetch_events()


class FakeProvider:
    name = "bls"

    def __init__(self, events=None, delay=0):
        self.events = events or []
        self.delay = delay
        self.calls = 0
        self.fail = False
        self.lock = threading.Lock()

    def fetch_events(self):
        with self.lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise CalendarProviderError("private upstream detail")
        return self.events


class FakeStore:
    def __init__(self, events=None, state=None):
        self.events = list(events or [])
        self.state = state
        self.save_calls = 0
        self.failure_calls = 0

    def refresh_lock(self, _provider):
        return nullcontext()

    def get_events(self, start_date, end_date, countries, importances):
        return [
            event for event in self.events
            if start_date <= event.scheduled_at.date() <= end_date
            and event.country in countries
            and event.importance in importances
        ]

    def get_provider_state(self, _provider):
        return self.state

    def record_refresh_attempt(self, _provider, attempted_at):
        if self.state is None:
            self.state = {
                "last_successful_refresh": None,
                "last_attempted_refresh": attempted_at,
                "latest_error": None,
            }

    def record_refresh_failure(self, _provider, attempted_at, error_message):
        self.failure_calls += 1
        if self.state is None:
            self.state = {}
        self.state["last_attempted_refresh"] = attempted_at
        self.state["latest_error"] = error_message

    def save_refresh(self, _provider, events, fetched_at):
        self.save_calls += 1
        self.events = list(events)
        self.state = {
            "last_successful_refresh": fetched_at,
            "last_attempted_refresh": fetched_at,
            "latest_error": None,
        }


class CalendarServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
        self.event = sample_event()
        self.arguments = (
            date(2026, 9, 29),
            date(2026, 9, 29),
            ("US",),
            ("high", "medium", "low"),
        )

    def test_fresh_stored_data_skips_provider(self):
        provider = FakeProvider([self.event])
        store = FakeStore([self.event], {
            "last_successful_refresh": self.now - timedelta(hours=1),
            "last_attempted_refresh": self.now - timedelta(hours=1),
            "latest_error": None,
        })
        service = CalendarService(provider, store, now=lambda: self.now)

        result = service.get_events(*self.arguments)

        self.assertEqual(result.events, [self.event])
        self.assertEqual(provider.calls, 0)
        self.assertFalse(result.stale)

    def test_expired_cache_refreshes_and_persists(self):
        provider = FakeProvider([self.event])
        store = FakeStore([], {
            "last_successful_refresh": self.now - timedelta(hours=7),
            "last_attempted_refresh": self.now - timedelta(hours=7),
            "latest_error": None,
        })
        service = CalendarService(provider, store, now=lambda: self.now)

        result = service.get_events(*self.arguments)

        self.assertEqual(provider.calls, 1)
        self.assertEqual(store.save_calls, 1)
        self.assertEqual(result.events, [self.event])

    def test_concurrent_expired_requests_share_one_refresh(self):
        provider = FakeProvider([self.event], delay=0.03)
        store = FakeStore()
        service = CalendarService(provider, store, now=lambda: self.now)

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _index: service.get_events(*self.arguments), range(6)))

        self.assertEqual(provider.calls, 1)
        self.assertTrue(all(result.events == [self.event] for result in results))

    def test_provider_failure_returns_stored_events_as_stale(self):
        provider = FakeProvider()
        provider.fail = True
        store = FakeStore([self.event], {
            "last_successful_refresh": self.now - timedelta(hours=7),
            "last_attempted_refresh": self.now - timedelta(hours=7),
            "latest_error": None,
        })
        service = CalendarService(provider, store, now=lambda: self.now)

        result = service.get_events(*self.arguments)

        self.assertTrue(result.stale)
        self.assertEqual(result.events, [self.event])
        self.assertEqual(store.failure_calls, 1)
        self.assertNotIn("private", result.warning)

    def test_provider_failure_without_stored_data_is_unavailable(self):
        provider = FakeProvider()
        provider.fail = True
        service = CalendarService(provider, FakeStore(), now=lambda: self.now)

        with self.assertRaises(CalendarUnavailable):
            service.get_events(*self.arguments)


class FakeCursor:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def execute(self, statement, parameters):
        self.database.queries.append((statement, parameters))

    def fetchone(self):
        return (True,)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def cursor(self):
        return FakeCursor(self.database)

    def commit(self):
        self.database.commits += 1

    def rollback(self):
        self.database.rollbacks += 1

    def close(self):
        self.database.closes += 1


class FakeDatabase:
    def __init__(self):
        self.queries = []
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def connect(self):
        return FakeConnection(self)


class CalendarStoreTests(unittest.TestCase):
    def test_refresh_upserts_events_and_state_in_one_transaction(self):
        database = FakeDatabase()
        store = EconomicCalendarStore(connection_factory=database.connect)
        fetched_at = datetime(2026, 9, 29, tzinfo=timezone.utc)

        store.save_refresh("bls", [sample_event()], fetched_at)

        self.assertEqual(database.commits, 1)
        self.assertEqual(database.rollbacks, 0)
        self.assertEqual(database.closes, 1)
        self.assertEqual(len(database.queries), 2)
        self.assertIn("ON CONFLICT (event_id) DO UPDATE", database.queries[0][0])
        self.assertIn("economic_calendar_provider_state", database.queries[1][0])

    def test_provider_refresh_lock_uses_postgresql_advisory_lock(self):
        database = FakeDatabase()
        store = EconomicCalendarStore(connection_factory=database.connect)

        with store.refresh_lock("bls"):
            pass

        self.assertIn("pg_advisory_lock", database.queries[0][0])
        self.assertIn("pg_advisory_unlock", database.queries[1][0])
        self.assertEqual(database.closes, 1)


class CalendarRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_api_uses_current_week_defaults(self):
        result = CalendarResult(
            events=[sample_event()],
            providers=["bls"],
            last_updated=datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc),
        )
        with patch.object(app, "current_week", return_value=(date(2026, 9, 28), date(2026, 10, 4))):
            with patch.object(app.economic_calendar_service, "get_events", return_value=result) as fetch:
                response = self.client.get("/api/economic-calendar")

        self.assertEqual(response.status_code, 200)
        fetch.assert_called_once_with(
            date(2026, 9, 28),
            date(2026, 10, 4),
            ("US",),
            tuple(SUPPORTED_IMPORTANCES),
        )
        self.assertEqual(response.json["meta"]["timezone"], "UTC")
        self.assertEqual(response.json["events"][0]["scheduled_at"], "2026-09-29T12:30:00Z")

    def test_api_validates_dates_ranges_and_unknown_parameters(self):
        urls = [
            "/api/economic-calendar?start=bad&end=2026-09-29",
            "/api/economic-calendar?start=2026-09-30&end=2026-09-29",
            "/api/economic-calendar?start=2026-09-01&end=2026-10-02",
            "/api/economic-calendar?start=2026-09-29&start=2026-09-30",
            "/api/economic-calendar?extra=true",
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["code"], "invalid_parameters")

    def test_api_deduplicates_and_validates_filters(self):
        result = CalendarResult([], ["bls"], None)
        with patch.object(app.economic_calendar_service, "get_events", return_value=result) as fetch:
            response = self.client.get(
                "/api/economic-calendar?start=2026-09-29&end=2026-09-29"
                "&country=US,US&country=US&importance=high,medium&importance=high"
            )

        self.assertEqual(response.status_code, 200)
        fetch.assert_called_once_with(
            date(2026, 9, 29),
            date(2026, 9, 29),
            ("US",),
            ("high", "medium"),
        )
        self.assertEqual(self.client.get("/api/economic-calendar?country=CA").status_code, 400)
        self.assertEqual(self.client.get("/api/economic-calendar?importance=urgent").status_code, 400)

    def test_api_returns_clean_unavailable_error(self):
        with patch.object(
            app.economic_calendar_service,
            "get_events",
            side_effect=CalendarUnavailable("database detail"),
        ):
            response = self.client.get("/api/economic-calendar")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["code"], "provider_unavailable")
        self.assertNotIn("database", response.json["error"])

    def test_pages_are_dedicated_and_coming_soon_pages_are_lightweight(self):
        calendar = self.client.get("/economic-calendar").get_data(as_text=True)
        earnings = self.client.get("/earnings").get_data(as_text=True)
        sentiment = self.client.get("/sentiment").get_data(as_text=True)

        self.assertIn('id="economic-calendar-list"', calendar)
        self.assertIn(
            "Track scheduled market-moving economic releases from official sources.",
            calendar,
        )
        self.assertNotIn("compare reported values with expectations", calendar)
        self.assertIn("MarketV impact classifications", calendar)
        self.assertIn("U.S. Bureau of Labor Statistics", calendar)
        self.assertIn("Earnings Calendar — Coming Soon", earnings)
        self.assertIn("Market Sentiment — Coming Soon", sentiment)
        self.assertNotIn('/static/script.js', earnings)
        self.assertNotIn('/static/economic-calendar.js', earnings)


class CalendarValidationTests(unittest.TestCase):
    def test_date_and_filter_helpers(self):
        self.assertEqual(parse_iso_date("2026-09-29", "start"), date(2026, 9, 29))
        with self.assertRaises(ValueError):
            parse_iso_date("09/29/2026", "start")
        with self.assertRaises(ValueError):
            validate_date_range(date(2026, 9, 1), date(2026, 10, 2))
        self.assertEqual(
            parse_filter_values(["high,medium", "high"], {"high", "medium"}, "importance", ()),
            ("high", "medium"),
        )


if __name__ == "__main__":
    unittest.main()
