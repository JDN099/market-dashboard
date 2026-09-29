"""Bureau of Labor Statistics iCalendar provider."""

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.economic_calendar.models import CalendarEvent
from services.economic_calendar.providers.base import (
    CalendarProviderError,
    EconomicCalendarProvider,
)


BLS_FEED_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BLS_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/"
BLS_SOURCE = "Bureau of Labor Statistics"
BLS_USER_AGENT = "MarketV/1.0 economic-calendar (student portfolio project)"
EASTERN_TIMEZONE_NAMES = {
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "US/Eastern": "America/New_York",
    "US-Eastern": "America/New_York",
    "Eastern Standard Time": "America/New_York",
}
MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
REPORTING_PERIOD_PATTERN = re.compile(
    rf"^(?P<name>.+?)\s+(?:for|[-–—])\s+(?P<period>(?:{MONTH_NAMES})\s+\d{{4}}|"
    r"(?:First|Second|Third|Fourth) Quarter(?:\s+\d{4})?|Q[1-4]\s+\d{4})$",
    re.IGNORECASE,
)
HIGH_IMPACT_NAMES = (
    "consumer price index",
    "employment situation",
    "nonfarm payrolls",
    "producer price index",
    "employment cost index",
)
MEDIUM_IMPACT_NAMES = (
    "job openings and labor turnover",
    "jolts",
    "productivity and costs",
    "import and export price",
    "real earnings",
)


def classify_bls_impact(event_name):
    normalized_name = " ".join(str(event_name).lower().split())
    if any(name in normalized_name for name in HIGH_IMPACT_NAMES):
        return "high"
    if any(name in normalized_name for name in MEDIUM_IMPACT_NAMES):
        return "medium"
    return "low"


def unfold_ical_lines(payload):
    unfolded = []
    for raw_line in payload.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw_line[1:]
        else:
            unfolded.append(raw_line)
    return unfolded


def unescape_ical_text(value):
    output = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "\\" or index + 1 >= len(value):
            output.append(character)
            index += 1
            continue

        escaped = value[index + 1]
        replacements = {
            "n": "\n",
            "N": "\n",
            ",": ",",
            ";": ";",
            "\\": "\\",
        }
        output.append(replacements.get(escaped, escaped))
        index += 2
    return "".join(output).strip()


def parse_property(line):
    head, separator, value = line.partition(":")
    if not separator:
        return None, {}, None

    parts = head.split(";")
    name = parts[0].upper()
    parameters = {}
    for part in parts[1:]:
        key, equals, parameter_value = part.partition("=")
        if equals:
            parameters[key.upper()] = parameter_value.strip('"')
    return name, parameters, value


def parse_ical_datetime(value, parameters):
    text = value.strip()
    formats = ["%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"]
    is_utc = text.endswith("Z")
    if is_utc:
        text = text[:-1]

    parsed = None
    for date_format in formats:
        try:
            parsed = datetime.strptime(text, date_format)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError("Unsupported DTSTART value")

    if is_utc:
        source_timezone = timezone.utc
    else:
        timezone_name = parameters.get("TZID", "America/New_York")
        timezone_name = EASTERN_TIMEZONE_NAMES.get(timezone_name, timezone_name)
        try:
            source_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unsupported DTSTART timezone") from exc

    return parsed.replace(tzinfo=source_timezone).astimezone(timezone.utc)


def split_name_and_period(summary):
    match = REPORTING_PERIOD_PATTERN.match(summary.strip())
    if not match:
        return summary.strip(), None
    return match.group("name").strip(), match.group("period").strip()


def safe_bls_url(value):
    candidate = str(value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme == "https" and parsed.hostname and parsed.hostname.lower().endswith("bls.gov"):
        return candidate
    return BLS_SCHEDULE_URL


def stable_event_id(uid):
    digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()[:32]
    return f"bls-{digest}"


def parse_bls_ics(payload):
    events_by_uid = {}
    current_event = None

    for line in unfold_ical_lines(payload):
        if line.upper() == "BEGIN:VEVENT":
            current_event = {}
            continue
        if line.upper() == "END:VEVENT":
            if current_event is not None:
                try:
                    event = normalize_bls_event(current_event)
                except (KeyError, TypeError, ValueError):
                    event = None
                if event is not None:
                    events_by_uid[event.id] = event
            current_event = None
            continue
        if current_event is None:
            continue

        name, parameters, value = parse_property(line)
        if name in {"UID", "SUMMARY", "DESCRIPTION", "URL", "DTSTART"}:
            current_event[name] = (parameters, value)

    return sorted(events_by_uid.values(), key=lambda event: (event.scheduled_at, event.id))


def normalize_bls_event(properties):
    uid = unescape_ical_text(properties["UID"][1])
    summary = unescape_ical_text(properties["SUMMARY"][1])
    if not uid or not summary:
        raise ValueError("BLS event requires UID and SUMMARY")

    scheduled_at = parse_ical_datetime(
        properties["DTSTART"][1],
        properties["DTSTART"][0],
    )
    name, reporting_period = split_name_and_period(summary)
    source_url = safe_bls_url(properties.get("URL", ({}, ""))[1])

    return CalendarEvent(
        id=stable_event_id(uid),
        provider="bls",
        name=name,
        country="US",
        currency="USD",
        scheduled_at=scheduled_at,
        importance=classify_bls_impact(name),
        reporting_period=reporting_period,
        actual=None,
        forecast=None,
        previous=None,
        source=BLS_SOURCE,
        source_url=source_url,
    )


class BlsCalendarProvider(EconomicCalendarProvider):
    name = "bls"

    def __init__(self, opener=None, timeout=10):
        self.opener = opener or urlopen
        self.timeout = timeout

    def fetch_events(self):
        request = Request(
            BLS_FEED_URL,
            headers={
                "Accept": "text/calendar",
                "User-Agent": BLS_USER_AGENT,
            },
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8-sig")
            events = parse_bls_ics(payload)
            if not events:
                raise CalendarProviderError("BLS calendar feed contained no valid events")
            return events
        except CalendarProviderError:
            raise
        except Exception as exc:
            raise CalendarProviderError("BLS calendar feed is unavailable") from exc
