"""Cached Twelve Data market-data service used by Flask routes."""

import threading
import time
from collections import deque
from dataclasses import dataclass

from services.twelve_data import (
    MAX_BATCH_SIZE,
    TwelveDataClient,
    TwelveDataError,
    history_request_options,
)


QUOTE_TTL_SECONDS = 15 * 60
QUOTE_STALE_TTL_SECONDS = 6 * 60 * 60
HISTORY_TTL_SECONDS = 6 * 60 * 60
HISTORY_STALE_TTL_SECONDS = 24 * 60 * 60
ERROR_TTL_SECONDS = 60
MINUTE_CREDIT_LIMIT = 8
DAILY_CREDIT_LIMIT = 800


class MarketDataUnavailable(Exception):
    """Raised when no current or stale provider result can be returned."""

    def __init__(self, message, state="unavailable"):
        super().__init__(message)
        self.state = state


@dataclass(frozen=True)
class CacheEntry:
    created_at: float
    value: object


class CreditBudget:
    def __init__(
        self,
        minute_limit=MINUTE_CREDIT_LIMIT,
        daily_limit=DAILY_CREDIT_LIMIT,
        clock=None,
    ):
        self.minute_limit = minute_limit
        self.daily_limit = daily_limit
        self.clock = clock or time.monotonic
        self._minute_credits = deque()
        self._daily_credits = deque()
        self._lock = threading.Lock()

    def reserve(self, credits):
        now = self.clock()
        with self._lock:
            self._discard_expired(self._minute_credits, now - 60)
            self._discard_expired(self._daily_credits, now - 24 * 60 * 60)
            if len(self._minute_credits) + credits > self.minute_limit:
                raise MarketDataUnavailable(
                    "Market data is temporarily rate limited",
                    state="rate_limited",
                )
            if len(self._daily_credits) + credits > self.daily_limit:
                raise MarketDataUnavailable(
                    "The daily market-data limit has been reached",
                    state="rate_limited",
                )

            self._minute_credits.extend([now] * credits)
            self._daily_credits.extend([now] * credits)

    @staticmethod
    def _discard_expired(entries, cutoff):
        while entries and entries[0] <= cutoff:
            entries.popleft()


class MarketDataService:
    def __init__(
        self,
        provider=None,
        quote_ttl=QUOTE_TTL_SECONDS,
        quote_stale_ttl=QUOTE_STALE_TTL_SECONDS,
        history_ttl=HISTORY_TTL_SECONDS,
        history_stale_ttl=HISTORY_STALE_TTL_SECONDS,
        error_ttl=ERROR_TTL_SECONDS,
        clock=None,
        credit_budget=None,
    ):
        self.provider = provider or TwelveDataClient()
        self.quote_ttl = quote_ttl
        self.quote_stale_ttl = quote_stale_ttl
        self.history_ttl = history_ttl
        self.history_stale_ttl = history_stale_ttl
        self.error_ttl = error_ttl
        self.clock = clock or time.monotonic
        self.credit_budget = credit_budget or CreditBudget(clock=self.clock)
        self._quotes = {}
        self._quote_errors = {}
        self._history = {}
        self._history_errors = {}
        self._history_states = {}
        self._quote_refresh_lock = threading.Lock()
        self._history_refresh_lock = threading.Lock()
        self._lock = threading.Lock()

    def get_quote(self, symbol):
        quotes, errors = self.get_quotes([symbol])
        if symbol in quotes:
            return quotes[symbol]
        error = errors.get(symbol, "Quote unavailable")
        raise MarketDataUnavailable(error, state=error_state(error))

    def get_quotes(self, symbols):
        unique_symbols = list(dict.fromkeys(symbols))
        if not unique_symbols:
            return {}, {}
        if len(unique_symbols) > MAX_BATCH_SIZE:
            raise ValueError("Provide no more than 8 symbols per quote request")

        quotes, missing, errors = self._cached_quotes(unique_symbols)
        if not missing:
            return quotes, errors

        with self._quote_refresh_lock:
            refreshed, missing, recent_errors = self._cached_quotes(missing)
            quotes.update(refreshed)
            errors.update(recent_errors)
            if not missing:
                return quotes, errors

            try:
                self.credit_budget.reserve(len(missing))
                fetched, provider_errors = self.provider.fetch_quotes(missing)
            except (MarketDataUnavailable, TwelveDataError) as exc:
                state = getattr(exc, "state", "unavailable")
                for symbol in missing:
                    self._use_stale_quote_or_error(symbol, state, quotes, errors)
                return quotes, errors

            now = self.clock()
            with self._lock:
                for symbol, quote in fetched.items():
                    self._quotes[symbol] = CacheEntry(now, quote)
                    self._quote_errors.pop(symbol, None)

            for symbol in missing:
                if symbol in fetched:
                    quotes[symbol] = quote_state(fetched[symbol], stale=False)
                    continue
                provider_error_value = provider_errors.get(
                    symbol,
                    TwelveDataError("Quote unavailable"),
                )
                state = getattr(provider_error_value, "state", "unavailable")
                self._use_stale_quote_or_error(symbol, state, quotes, errors)

        return quotes, errors

    def get_history(self, symbol, period="1mo", interval="1d"):
        histories, errors = self._get_histories([symbol], period, interval)
        if symbol in histories:
            return histories[symbol]
        error = errors.get(symbol, "History unavailable")
        raise MarketDataUnavailable(error, state=error_state(error))

    def get_intraday_histories(self, symbols):
        return self._get_histories(symbols, "1d", "5m")

    def get_history_state(self, symbol, period="1mo", interval="1d"):
        with self._lock:
            return self._history_states.get((symbol, period, interval), "delayed")

    def get_intraday_history_states(self, symbols):
        with self._lock:
            return {
                symbol: self._history_states.get(
                    (symbol, "1d", "5m"),
                    "delayed",
                )
                for symbol in symbols
                if (symbol, "1d", "5m") in self._history_states
            }

    def _get_histories(self, symbols, period, interval):
        history_request_options(period, interval)
        unique_symbols = list(dict.fromkeys(symbols))
        if not unique_symbols:
            return {}, {}
        if len(unique_symbols) > MAX_BATCH_SIZE:
            raise ValueError("Provide no more than 8 symbols per history request")

        histories, missing, errors = self._cached_histories(
            unique_symbols,
            period,
            interval,
        )
        if not missing:
            return histories, errors

        with self._history_refresh_lock:
            refreshed, missing, recent_errors = self._cached_histories(
                missing,
                period,
                interval,
            )
            histories.update(refreshed)
            errors.update(recent_errors)
            if not missing:
                return histories, errors

            try:
                self.credit_budget.reserve(len(missing))
                fetched, provider_errors = self.provider.fetch_histories(
                    missing,
                    period,
                    interval,
                )
            except (MarketDataUnavailable, TwelveDataError) as exc:
                state = getattr(exc, "state", "unavailable")
                for symbol in missing:
                    self._use_stale_history_or_error(
                        symbol,
                        period,
                        interval,
                        state,
                        histories,
                        errors,
                    )
                return histories, errors

            now = self.clock()
            with self._lock:
                for symbol, points in fetched.items():
                    key = (symbol, period, interval)
                    self._history[key] = CacheEntry(now, points)
                    self._history_errors.pop(key, None)
                    self._history_states[key] = "delayed"

            for symbol in missing:
                if symbol in fetched:
                    histories[symbol] = fetched[symbol]
                    continue
                provider_error_value = provider_errors.get(
                    symbol,
                    TwelveDataError("History unavailable"),
                )
                state = getattr(provider_error_value, "state", "unavailable")
                self._use_stale_history_or_error(
                    symbol,
                    period,
                    interval,
                    state,
                    histories,
                    errors,
                )

        return histories, errors

    def _cached_quotes(self, symbols):
        quotes = {}
        missing = []
        errors = {}
        now = self.clock()
        with self._lock:
            for symbol in symbols:
                entry = self._quotes.get(symbol)
                if entry and now - entry.created_at < self.quote_ttl:
                    quotes[symbol] = quote_state(entry.value, stale=False)
                    continue
                recent_error = self._quote_errors.get(symbol)
                if recent_error and now - recent_error.created_at < self.error_ttl:
                    if entry and now - entry.created_at < self.quote_stale_ttl:
                        quotes[symbol] = quote_state(entry.value, stale=True)
                    else:
                        errors[symbol] = state_message(recent_error.value)
                    continue
                missing.append(symbol)
        return quotes, missing, errors

    def _cached_histories(self, symbols, period, interval):
        histories = {}
        missing = []
        errors = {}
        now = self.clock()
        with self._lock:
            for symbol in symbols:
                key = (symbol, period, interval)
                entry = self._history.get(key)
                if entry and now - entry.created_at < self.history_ttl:
                    histories[symbol] = entry.value
                    self._history_states[key] = "delayed"
                    continue
                recent_error = self._history_errors.get(key)
                if recent_error and now - recent_error.created_at < self.error_ttl:
                    if entry and now - entry.created_at < self.history_stale_ttl:
                        histories[symbol] = entry.value
                        self._history_states[key] = "stale"
                    else:
                        errors[symbol] = state_message(recent_error.value, history=True)
                    continue
                missing.append(symbol)
        return histories, missing, errors

    def _use_stale_quote_or_error(self, symbol, state, quotes, errors):
        now = self.clock()
        with self._lock:
            entry = self._quotes.get(symbol)
            self._quote_errors[symbol] = CacheEntry(now, state)
        if entry and now - entry.created_at < self.quote_stale_ttl:
            quotes[symbol] = quote_state(entry.value, stale=True)
        else:
            errors[symbol] = state_message(state)

    def _use_stale_history_or_error(
        self,
        symbol,
        period,
        interval,
        state,
        histories,
        errors,
    ):
        now = self.clock()
        key = (symbol, period, interval)
        with self._lock:
            entry = self._history.get(key)
            self._history_errors[key] = CacheEntry(now, state)
        if entry and now - entry.created_at < self.history_stale_ttl:
            histories[symbol] = entry.value
            with self._lock:
                self._history_states[key] = "stale"
        else:
            errors[symbol] = state_message(state, history=True)


def quote_state(quote, stale):
    result = dict(quote)
    result["provider"] = "Twelve Data"
    result["delayed"] = True
    result["stale"] = stale
    result["data_state"] = "stale" if stale else "delayed"
    return result


def state_message(state, history=False):
    subject = "History" if history else "Quote"
    messages = {
        "rate_limited": f"{subject} rate limited; try again later",
        "unsupported": f"{subject} unsupported by Twelve Data",
        "unconfigured": f"{subject} unavailable; provider key is missing",
        "unavailable": f"{subject} unavailable from Twelve Data",
    }
    return messages.get(state, messages["unavailable"])


def error_state(message):
    lowered = str(message).lower()
    if "rate limit" in lowered:
        return "rate_limited"
    if "unsupported" in lowered:
        return "unsupported"
    if "key is missing" in lowered:
        return "unconfigured"
    return "unavailable"


market_data = MarketDataService()
