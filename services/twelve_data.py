"""Server-side Twelve Data REST adapter."""

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
MAX_BATCH_SIZE = 8


class TwelveDataError(Exception):
    """Base class for safe provider failures."""

    state = "unavailable"


class TwelveDataConfigurationError(TwelveDataError):
    state = "unconfigured"


class TwelveDataRateLimited(TwelveDataError):
    state = "rate_limited"


class TwelveDataUnsupported(TwelveDataError):
    state = "unsupported"


def number(value, allow_zero=False, allow_negative=False):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(parsed):
        return None
    if allow_negative:
        return parsed
    if allow_zero and parsed >= 0:
        return parsed
    if parsed > 0:
        return parsed
    return None


def provider_error(payload):
    if not isinstance(payload, dict) or payload.get("status") != "error":
        return None

    code = payload.get("code")
    message = str(payload.get("message", "")).lower()
    if code == 429 or "credit" in message or "rate limit" in message:
        return TwelveDataRateLimited("Provider rate limit reached")
    if code == 401 or "api key" in message:
        return TwelveDataConfigurationError("Market data provider is not configured")
    if code in (400, 403, 404) or "symbol" in message:
        return TwelveDataUnsupported("Symbol is unsupported by the provider")
    return TwelveDataError("Market data provider is unavailable")


class TwelveDataClient:
    def __init__(self, api_key=None, opener=None, timeout=20):
        self.api_key = api_key if api_key is not None else os.getenv("TWELVE_DATA_API_KEY", "")
        self.opener = opener or urlopen
        self.timeout = timeout

    def fetch_quotes(self, symbols):
        self._validate_batch(symbols)
        payload = self._request("quote", {
            "symbol": ",".join(symbols),
        })
        results = self._batch_results(payload, symbols)
        quotes = {}
        errors = {}

        for symbol in symbols:
            item = results.get(symbol, {})
            error = provider_error(item)
            if error:
                errors[symbol] = error
                continue

            try:
                quotes[symbol] = self._normalize_quote(symbol, item)
            except TwelveDataError as exc:
                errors[symbol] = exc

        return quotes, errors

    def fetch_histories(self, symbols, period, interval):
        self._validate_batch(symbols)
        provider_interval, output_size = history_request_options(period, interval)
        payload = self._request("time_series", {
            "symbol": ",".join(symbols),
            "interval": provider_interval,
            "outputsize": output_size,
            "timezone": "UTC",
        })
        results = self._batch_results(payload, symbols)
        histories = {}
        errors = {}

        for symbol in symbols:
            item = results.get(symbol, {})
            error = provider_error(item)
            if error:
                errors[symbol] = error
                continue

            values = item.get("values") if isinstance(item, dict) else None
            points = []
            if isinstance(values, list):
                for value in reversed(values):
                    close = number(value.get("close"))
                    timestamp = normalize_timestamp(value.get("datetime"))
                    if close is not None and timestamp:
                        points.append({
                            "time": timestamp,
                            "close": round(close, 6),
                        })

            if points:
                histories[symbol] = points
            else:
                errors[symbol] = TwelveDataError("Price history is unavailable")

        return histories, errors

    def _request(self, endpoint, parameters):
        api_key = str(self.api_key or "").strip()
        if not api_key:
            raise TwelveDataConfigurationError("Market data provider is not configured")

        url = f"{TWELVE_DATA_BASE_URL}/{endpoint}?{urlencode(parameters)}"
        request = Request(
            url,
            headers={
                "Authorization": f"apikey {api_key}",
                "User-Agent": "MarketV market dashboard",
            },
        )

        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except HTTPError as exc:
            if exc.code == 429:
                raise TwelveDataRateLimited("Provider rate limit reached") from exc
            if exc.code == 401:
                raise TwelveDataConfigurationError("Market data provider rejected credentials") from exc
            if exc.code in (400, 403, 404):
                raise TwelveDataUnsupported("Provider does not support this request") from exc
            raise TwelveDataError("Market data provider is unavailable") from exc
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise TwelveDataError("Market data provider is unavailable") from exc

        error = provider_error(payload)
        if error:
            raise error
        if not isinstance(payload, dict):
            raise TwelveDataError("Market data provider returned an invalid response")
        return payload

    @staticmethod
    def _validate_batch(symbols):
        if not symbols or len(symbols) > MAX_BATCH_SIZE:
            raise ValueError("Twelve Data batches must contain 1 to 8 symbols")

    @staticmethod
    def _batch_results(payload, symbols):
        is_single_result = "symbol" in payload or "meta" in payload
        if len(symbols) == 1 and symbols[0] not in payload and is_single_result:
            return {symbols[0]: payload}
        return payload

    @staticmethod
    def _normalize_quote(symbol, item):
        price = number(item.get("close"))
        if price is None:
            raise TwelveDataError("Quote is unavailable")

        previous_close = number(item.get("previous_close"))
        percent_change = number(item.get("percent_change"), allow_negative=True)
        if percent_change is None and previous_close is not None:
            percent_change = (price - previous_close) / previous_close * 100

        asset_type = asset_type_for(symbol)
        return {
            "symbol": symbol,
            "name": display_name_for(symbol, item.get("name")),
            "price": round(price, 6),
            "change": round(percent_change, 2) if percent_change is not None else None,
            "change_basis": "Previous close",
            "market_cap": None,
            "size_value": None,
            "size_label": "Asset type",
            "size_display": asset_type,
            "instrument_type": asset_type,
            "volume": number(item.get("volume"), allow_zero=True),
            "day_high": number(item.get("high")),
            "day_low": number(item.get("low")),
            "provider_timestamp": normalize_timestamp(
                item.get("datetime") or item.get("timestamp")
            ),
            "sparkline": [],
        }


def history_request_options(period, interval):
    options = {
        ("1d", "5m"): ("5min", 100),
        ("5d", "1d"): ("1day", 5),
        ("5d", "1h"): ("1h", 40),
        ("1mo", "1d"): ("1day", 30),
        ("1mo", "1h"): ("1h", 180),
        ("3mo", "1d"): ("1day", 90),
        ("1y", "1d"): ("1day", 365),
    }
    try:
        return options[(period, interval)]
    except KeyError as exc:
        raise ValueError("Unsupported history period or interval") from exc


def normalize_timestamp(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        return int(value)

    text = str(value).strip()
    if len(text) == 10:
        text += "T00:00:00"
    else:
        text = text.replace(" ", "T")
    if text and not text.endswith("Z") and "+" not in text[10:]:
        text += "+00:00"
    return text or None


def asset_type_for(symbol):
    if symbol == "BTC/USD":
        return "Cryptocurrency"
    if symbol == "EUR/USD":
        return "Forex"
    if symbol in {"SPY", "QQQ", "IWM", "DIA", "GLD", "USO"}:
        return "ETF"
    return "Stock"


def display_name_for(symbol, provider_name):
    names = {
        "GLD": "SPDR Gold Shares ETF",
        "USO": "United States Oil Fund ETF",
        "BTC/USD": "Bitcoin / U.S. Dollar",
        "EUR/USD": "Euro / U.S. Dollar",
    }
    return names.get(symbol) or provider_name or symbol
