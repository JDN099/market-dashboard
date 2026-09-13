import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from services.market_data import MarketDataService, MarketDataUnavailable


class FakeTicker:
    def __init__(self, info=None, closes=None, delay=0):
        self.info = info or {}
        self.closes = closes or []
        self.delay = delay
        self.calls = 0
        self.lock = threading.Lock()

    def history(self, **_kwargs):
        with self.lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        dates = pd.date_range("2026-01-01", periods=len(self.closes))
        return pd.DataFrame({"Close": self.closes}, index=dates)


class MarketDataServiceTests(unittest.TestCase):
    def test_quote_is_cached_until_ttl_expires(self):
        ticker = FakeTicker(
            info={"shortName": "Apple", "previousClose": 100},
            closes=[100, 101, 102],
        )
        current_time = [0]
        service = MarketDataService(
            quote_ttl=60,
            ticker_factory=lambda _symbol: ticker,
            clock=lambda: current_time[0],
        )

        first = service.get_quote("AAPL")
        current_time[0] = 59
        second = service.get_quote("AAPL")
        self.assertEqual(first, second)
        self.assertEqual(ticker.calls, 1)
        self.assertEqual(first["price"], 102)
        self.assertEqual(first["sparkline"], [100, 101, 102])

        current_time[0] = 60
        service.get_quote("AAPL")
        self.assertEqual(ticker.calls, 2)

    def test_simultaneous_requests_share_one_provider_fetch(self):
        ticker = FakeTicker(info={"previousClose": 100}, closes=[101], delay=0.03)
        service = MarketDataService(ticker_factory=lambda _symbol: ticker)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(service.get_quote, ["SPY"] * 8))

        self.assertEqual(ticker.calls, 1)
        self.assertTrue(all(result["price"] == 101 for result in results))

    def test_missing_price_is_an_error_not_zero(self):
        ticker = FakeTicker()
        current_time = [0]
        service = MarketDataService(
            ticker_factory=lambda _symbol: ticker,
            clock=lambda: current_time[0],
        )

        with self.assertRaises(MarketDataUnavailable):
            service.get_quote("SPY")
        with self.assertRaises(MarketDataUnavailable):
            service.get_quote("SPY")
        self.assertEqual(ticker.calls, 1)

        current_time[0] = 10
        with self.assertRaises(MarketDataUnavailable):
            service.get_quote("SPY")
        self.assertEqual(ticker.calls, 2)

    def test_batch_reports_partial_failure(self):
        tickers = {
            "SPY": FakeTicker(info={"previousClose": 100}, closes=[101]),
            "QQQ": FakeTicker(),
        }
        service = MarketDataService(ticker_factory=lambda symbol: tickers[symbol])

        quotes, errors = service.get_quotes(["SPY", "QQQ"])

        self.assertEqual(quotes["SPY"]["price"], 101)
        self.assertNotIn("QQQ", quotes)
        self.assertIn("QQQ", errors)

    def test_history_returns_dated_points_and_rejects_invalid_ranges(self):
        ticker = FakeTicker(closes=[100, 101])
        service = MarketDataService(ticker_factory=lambda _symbol: ticker)

        points = service.get_history("SPY", period="1mo", interval="1d")
        self.assertEqual([point["close"] for point in points], [100, 101])
        self.assertIn("2026-01-01", points[0]["time"])

        with self.assertRaises(ValueError):
            service.get_history("SPY", period="5y", interval="1m")


if __name__ == "__main__":
    unittest.main()
