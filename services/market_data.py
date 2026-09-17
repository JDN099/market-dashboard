"""Yahoo Finance adapter with a short, per-process quote cache."""

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf


QUOTE_TTL_SECONDS = 60
HISTORY_TTL_SECONDS = 300
ERROR_TTL_SECONDS = 10
HISTORY_OPTIONS = {
    "1d": {"5m"},
    "5d": {"1d", "1h"},
    "1mo": {"1d", "1h"},
    "3mo": {"1d"},
    "1y": {"1d"},
}


class MarketDataUnavailable(Exception):
    """Raised when the provider has no usable price for a supported symbol."""


def positive_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number) or number <= 0:
        return None
    return number


def nonnegative_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number) or number < 0:
        return None
    return number


class MarketDataService:
    def __init__(
        self,
        quote_ttl=QUOTE_TTL_SECONDS,
        history_ttl=HISTORY_TTL_SECONDS,
        ticker_factory=None,
        clock=None,
    ):
        self.quote_ttl = quote_ttl
        self.history_ttl = history_ttl
        self.ticker_factory = ticker_factory or yf.Ticker
        self.clock = clock or time.monotonic
        self._quotes = {}
        self._errors = {}
        self._quote_locks = {}
        self._history = {}
        self._history_locks = {}
        self._lock = threading.Lock()

    def get_quote(self, symbol):
        with self._lock:
            cached = self._quotes.get(symbol)
            if cached and self.clock() - cached[0] < self.quote_ttl:
                return cached[1]
            recent_error = self._errors.get(symbol)
            if recent_error and self.clock() - recent_error[0] < ERROR_TTL_SECONDS:
                raise MarketDataUnavailable(recent_error[1])
            symbol_lock = self._quote_locks.setdefault(symbol, threading.Lock())

        # A second caller for the same symbol waits here instead of calling Yahoo again.
        with symbol_lock:
            with self._lock:
                cached = self._quotes.get(symbol)
                if cached and self.clock() - cached[0] < self.quote_ttl:
                    return cached[1]
                recent_error = self._errors.get(symbol)
                if recent_error and self.clock() - recent_error[0] < ERROR_TTL_SECONDS:
                    raise MarketDataUnavailable(recent_error[1])

            try:
                quote = self._fetch_quote(symbol)
            except MarketDataUnavailable as exc:
                with self._lock:
                    self._errors[symbol] = (self.clock(), str(exc))
                raise
            with self._lock:
                self._quotes[symbol] = (self.clock(), quote)
                self._errors.pop(symbol, None)
            return quote

    def get_quotes(self, symbols):
        quotes = {}
        errors = {}
        if not symbols:
            return quotes, errors

        def fetch_one(symbol):
            try:
                return symbol, self.get_quote(symbol), None
            except MarketDataUnavailable as exc:
                return symbol, None, str(exc)
            except Exception:
                return symbol, None, f"Quote unavailable for {symbol}"

        with ThreadPoolExecutor(max_workers=min(4, len(symbols))) as executor:
            for symbol, quote, error in executor.map(fetch_one, symbols):
                if error:
                    errors[symbol] = error
                else:
                    quotes[symbol] = quote

        return quotes, errors

    def get_history(self, symbol, period="1mo", interval="1d"):
        if interval not in HISTORY_OPTIONS.get(period, set()):
            raise ValueError("Unsupported history period or interval")

        key = (symbol, period, interval)
        with self._lock:
            cached = self._history.get(key)
            if cached and self.clock() - cached[0] < self.history_ttl:
                return cached[1]
            history_lock = self._history_locks.setdefault(key, threading.Lock())

        with history_lock:
            with self._lock:
                cached = self._history.get(key)
                if cached and self.clock() - cached[0] < self.history_ttl:
                    return cached[1]

            points = self._fetch_history(symbol, period, interval)
            with self._lock:
                self._history[key] = (self.clock(), points)
            return points

    def get_intraday_histories(self, symbols):
        histories = {}
        errors = {}
        if not symbols:
            return histories, errors

        def fetch_one(symbol):
            try:
                return symbol, self.get_history(symbol, period="1d", interval="5m"), None
            except MarketDataUnavailable as exc:
                return symbol, None, str(exc)
            except Exception:
                return symbol, None, f"History unavailable for {symbol}"

        with ThreadPoolExecutor(max_workers=min(4, len(symbols))) as executor:
            for symbol, points, error in executor.map(fetch_one, symbols):
                if error:
                    errors[symbol] = error
                else:
                    histories[symbol] = points

        return histories, errors

    def _fetch_history(self, symbol, period, interval):
        try:
            history = self.ticker_factory(symbol).history(
                period=period,
                interval=interval,
                auto_adjust=False,
            )
        except Exception as exc:
            raise MarketDataUnavailable(f"History unavailable for {symbol}") from exc

        if history is None or history.empty or "Close" not in history:
            raise MarketDataUnavailable(f"History unavailable for {symbol}")

        points = []
        for timestamp, row in history.iterrows():
            close = positive_number(row.get("Close"))
            if close is not None:
                points.append({
                    "time": timestamp.isoformat(),
                    "close": round(close, 2),
                })

        if not points:
            raise MarketDataUnavailable(f"History unavailable for {symbol}")
        return points

    def _fetch_quote(self, symbol):
        try:
            stock = self.ticker_factory(symbol)
        except Exception as exc:
            raise MarketDataUnavailable(f"Quote unavailable for {symbol}") from exc

        try:
            info = stock.info or {}
        except Exception:
            info = {}

        try:
            history = stock.history(period="5d", auto_adjust=False)
        except Exception:
            history = None

        closes = []
        if history is not None and not history.empty and "Close" in history:
            for value in history["Close"]:
                close = positive_number(value)
                if close is not None:
                    closes.append(close)

        is_futures = symbol.endswith("=F")
        live_price = positive_number(info.get("regularMarketPrice"))
        if is_futures:
            price = live_price
        else:
            price = live_price
            if price is None and closes:
                price = closes[-1]
        if price is None:
            raise MarketDataUnavailable(f"Quote unavailable for {symbol}")

        if is_futures:
            previous_close = positive_number(info.get("regularMarketPreviousClose"))
            change_basis = "Prior settlement"
        else:
            previous_close = positive_number(info.get("regularMarketPreviousClose"))
            if previous_close is None and len(closes) > 1:
                previous_close = closes[-2]
            if previous_close is None:
                previous_close = positive_number(info.get("previousClose"))
            change_basis = "Previous close"
        change = None
        if previous_close is not None:
            change = round((price - previous_close) / previous_close * 100, 2)

        market_cap = positive_number(info.get("marketCap"))
        fund_assets = positive_number(info.get("totalAssets"))
        size_value = market_cap or fund_assets
        size_label = "Fund assets" if market_cap is None and fund_assets else "Market cap"

        return {
            "symbol": symbol,
            "name": info.get("shortName") or info.get("longName") or symbol,
            "price": round(price, 2),
            "change": change,
            "change_basis": change_basis,
            "market_cap": market_cap,
            "size_value": size_value,
            "size_label": size_label,
            "volume": nonnegative_number(info.get("regularMarketVolume")),
            "day_high": positive_number(info.get("regularMarketDayHigh")),
            "day_low": positive_number(info.get("regularMarketDayLow")),
            "sparkline": [round(value, 2) for value in closes[-5:]],
        }


market_data = MarketDataService()
