"""PostgreSQL persistence for normalized economic calendar events."""

from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone

from services.database import get_db_connection
from services.economic_calendar.models import CalendarEvent


class EconomicCalendarStore:
    def __init__(self, connection_factory=None):
        self.connection_factory = connection_factory or get_db_connection

    def get_events(self, start_date, end_date, countries, importances):
        range_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT event_id, provider, event_name, country, currency,
                           scheduled_at, importance, reporting_period, actual,
                           forecast, previous, source_name, source_url, status
                    FROM economic_calendar_events
                    WHERE scheduled_at >= %s
                      AND scheduled_at < %s
                      AND country = ANY(%s)
                      AND importance = ANY(%s)
                    ORDER BY scheduled_at, event_name
                    """,
                    (range_start, range_end, list(countries), list(importances)),
                )
                rows = cursor.fetchall()
            return [self._event_from_row(row) for row in rows]
        finally:
            connection.close()

    @contextmanager
    def refresh_lock(self, provider):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_lock(hashtext(%s))",
                    (f"economic-calendar:{provider}",),
                )
            yield
        finally:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtext(%s))",
                        (f"economic-calendar:{provider}",),
                    )
            finally:
                connection.close()

    def get_provider_state(self, provider):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT last_successful_refresh, last_attempted_refresh, latest_error
                    FROM economic_calendar_provider_state
                    WHERE provider = %s
                    """,
                    (provider,),
                )
                row = cursor.fetchone()
            if not row:
                return None
            return {
                "last_successful_refresh": row[0],
                "last_attempted_refresh": row[1],
                "latest_error": row[2],
            }
        finally:
            connection.close()

    def record_refresh_attempt(self, provider, attempted_at):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO economic_calendar_provider_state (
                        provider,
                        last_attempted_refresh
                    )
                    VALUES (%s, %s)
                    ON CONFLICT (provider) DO UPDATE SET
                        last_attempted_refresh = EXCLUDED.last_attempted_refresh
                    """,
                    (provider, attempted_at),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_refresh_failure(self, provider, attempted_at, error_message):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO economic_calendar_provider_state (
                        provider,
                        last_attempted_refresh,
                        latest_error
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (provider) DO UPDATE SET
                        last_attempted_refresh = EXCLUDED.last_attempted_refresh,
                        latest_error = EXCLUDED.latest_error
                    """,
                    (provider, attempted_at, error_message),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_refresh(self, provider, events, fetched_at):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                for event in events:
                    cursor.execute(
                        """
                        INSERT INTO economic_calendar_events (
                            event_id, provider, event_name, country, currency,
                            scheduled_at, importance, reporting_period, actual,
                            forecast, previous, source_name, source_url, status,
                            fetched_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (event_id) DO UPDATE SET
                            provider = EXCLUDED.provider,
                            event_name = EXCLUDED.event_name,
                            country = EXCLUDED.country,
                            currency = EXCLUDED.currency,
                            scheduled_at = EXCLUDED.scheduled_at,
                            importance = EXCLUDED.importance,
                            reporting_period = EXCLUDED.reporting_period,
                            actual = EXCLUDED.actual,
                            forecast = EXCLUDED.forecast,
                            previous = EXCLUDED.previous,
                            source_name = EXCLUDED.source_name,
                            source_url = EXCLUDED.source_url,
                            status = EXCLUDED.status,
                            updated_at = NOW(),
                            fetched_at = EXCLUDED.fetched_at
                        """,
                        (
                            event.id,
                            event.provider,
                            event.name,
                            event.country,
                            event.currency,
                            event.scheduled_at,
                            event.importance,
                            event.reporting_period,
                            event.actual,
                            event.forecast,
                            event.previous,
                            event.source,
                            event.source_url,
                            event.status,
                            fetched_at,
                        ),
                    )
                cursor.execute(
                    """
                    INSERT INTO economic_calendar_provider_state (
                        provider,
                        last_successful_refresh,
                        last_attempted_refresh,
                        latest_error
                    )
                    VALUES (%s, %s, %s, NULL)
                    ON CONFLICT (provider) DO UPDATE SET
                        last_successful_refresh = EXCLUDED.last_successful_refresh,
                        last_attempted_refresh = EXCLUDED.last_attempted_refresh,
                        latest_error = NULL
                    """,
                    (provider, fetched_at, fetched_at),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _event_from_row(row):
        return CalendarEvent(
            id=row[0],
            provider=row[1],
            name=row[2],
            country=row[3],
            currency=row[4],
            scheduled_at=row[5],
            importance=row[6],
            reporting_period=row[7],
            actual=row[8],
            forecast=row[9],
            previous=row[10],
            source=row[11],
            source_url=row[12],
            status=row[13],
        )
