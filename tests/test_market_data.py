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

        intraday_points = service.get_history("SPY", period="1d", interval="5m")
        self.assertEqual([point["close"] for point in intraday_points], [100, 101])

        with self.assertRaises(ValueError):
            service.get_history("SPY", period="5y", interval="1m")

        with self.assertRaises(ValueError):
            service.get_history("SPY", period="1d", interval="1d")

    def test_history_is_cached_by_symbol_and_range_until_ttl_expires(self):
        ticker = FakeTicker(closes=[100, 101])
        current_time = [0]
        service = MarketDataService(
            history_ttl=300,
            ticker_factory=lambda _symbol: ticker,
            clock=lambda: current_time[0],
        )

        first = service.get_history("SPY", period="1mo", interval="1d")
        current_time[0] = 299
        second = service.get_history("SPY", period="1mo", interval="1d")
        self.assertEqual(first, second)
        self.assertEqual(ticker.calls, 1)

        service.get_history("SPY", period="1mo", interval="1h")
        self.assertEqual(ticker.calls, 2)

        current_time[0] = 300
        service.get_history("SPY", period="1mo", interval="1d")
        self.assertEqual(ticker.calls, 3)

    def test_intraday_batch_reuses_history_cache_and_reports_partial_errors(self):
        tickers = {
            "SPY": FakeTicker(closes=[100, 101]),
            "QQQ": FakeTicker(),
        }
        service = MarketDataService(ticker_factory=lambda symbol: tickers[symbol])

        histories, errors = service.get_intraday_histories(["SPY", "QQQ"])
        again = service.get_history("SPY", period="1d", interval="5m")

        self.assertEqual([point["close"] for point in histories["SPY"]], [100, 101])
        self.assertEqual(histories["SPY"], again)
        self.assertEqual(tickers["SPY"].calls, 1)
        self.assertIn("QQQ", errors)

    def test_simultaneous_history_requests_share_one_provider_fetch(self):
        ticker = FakeTicker(closes=[100, 101], delay=0.03)
        service = MarketDataService(ticker_factory=lambda _symbol: ticker)

        with ThreadPoolExecutor(max_workers=8) as executor:
            histories = list(executor.map(
                lambda _index: service.get_history("SPY"),
                range(8),
            ))

        self.assertEqual(ticker.calls, 1)
        self.assertTrue(all(history == histories[0] for history in histories))


if __name__ == "__main__":
    unittest.main()
