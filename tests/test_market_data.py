import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from services.market_data import (
    CreditBudget,
    MarketDataService,
    MarketDataUnavailable,
)
from services.symbols import MARKET_FLOW_SYMBOLS, MARKET_SYMBOLS, VALID_SYMBOLS
from services.twelve_data import (
    TwelveDataClient,
    TwelveDataConfigurationError,
    TwelveDataError,
    TwelveDataRateLimited,
    TwelveDataUnsupported,
    asset_type_for,
    display_name_for,
)


def quote(symbol, price=100, change=1):
    return {
        "symbol": symbol,
        "name": symbol,
        "price": price,
        "change": change,
        "change_basis": "Previous close",
        "market_cap": None,
        "size_value": None,
        "size_label": "Asset type",
        "size_display": asset_type_for(symbol),
        "instrument_type": asset_type_for(symbol),
        "volume": 1000,
        "day_high": price + 1,
        "day_low": price - 1,
        "sparkline": [],
    }


class FakeProvider:
    def __init__(self, delay=0):
        self.delay = delay
        self.quote_calls = []
        self.history_calls = []
        self.quote_failure = None
        self.history_failure = None
        self.quote_errors = {}
        self.history_errors = {}
        self.lock = threading.Lock()

    def fetch_quotes(self, symbols):
        with self.lock:
            self.quote_calls.append(list(symbols))
        if self.delay:
            time.sleep(self.delay)
        if self.quote_failure:
            raise self.quote_failure
        return (
            {
                symbol: quote(symbol)
                for symbol in symbols
                if symbol not in self.quote_errors
            },
            {
                symbol: self.quote_errors[symbol]
                for symbol in symbols
                if symbol in self.quote_errors
            },
        )

    def fetch_histories(self, symbols, period, interval):
        with self.lock:
            self.history_calls.append((list(symbols), period, interval))
        if self.history_failure:
            raise self.history_failure
        return (
            {
                symbol: [
                    {"time": "2026-01-01T00:00:00+00:00", "close": 100},
                    {"time": "2026-01-02T00:00:00+00:00", "close": 101},
                ]
                for symbol in symbols
                if symbol not in self.history_errors
            },
            {
                symbol: self.history_errors[symbol]
                for symbol in symbols
                if symbol in self.history_errors
            },
        )


def generous_budget(clock):
    return CreditBudget(
        minute_limit=100,
        daily_limit=1000,
        clock=clock,
    )


class TwelveDataClientTests(unittest.TestCase):
    def test_successful_batch_quote_is_normalized(self):
        client = TwelveDataClient(api_key="fixture-key")
        client._request = lambda _endpoint, _parameters: {
            "SPY": {
                "symbol": "SPY",
                "name": "SPDR S&P 500 ETF Trust",
                "close": "501.25",
                "previous_close": "500.00",
                "percent_change": "0.25",
                "high": "502.00",
                "low": "498.50",
                "volume": "123456",
                "datetime": "2026-09-29 16:00:00",
            },
            "GLD": {
                "symbol": "GLD",
                "name": "SPDR Gold Shares",
                "close": "250.50",
                "previous_close": "252.00",
                "percent_change": "-0.5952",
                "high": "253.00",
                "low": "249.00",
                "volume": "1000",
                "datetime": "2026-09-29 16:00:00",
            },
        }

        quotes, errors = client.fetch_quotes(["SPY", "GLD"])

        self.assertEqual(errors, {})
        self.assertEqual(quotes["SPY"]["price"], 501.25)
        self.assertEqual(quotes["GLD"]["change"], -0.6)
        self.assertEqual(quotes["GLD"]["name"], "SPDR Gold Shares ETF")
        self.assertEqual(quotes["GLD"]["instrument_type"], "ETF")

    def test_history_batch_is_normalized_oldest_first(self):
        client = TwelveDataClient(api_key="fixture-key")
        client._request = lambda _endpoint, _parameters: {
            "EUR/USD": {
                "meta": {"symbol": "EUR/USD"},
                "values": [
                    {"datetime": "2026-09-29 12:00:00", "close": "1.1800"},
                    {"datetime": "2026-09-29 11:55:00", "close": "1.1790"},
                ],
                "status": "ok",
            }
        }

        histories, errors = client.fetch_histories(
            ["EUR/USD"],
            "1d",
            "5m",
        )

        self.assertEqual(errors, {})
        self.assertEqual(
            [point["close"] for point in histories["EUR/USD"]],
            [1.179, 1.18],
        )
        self.assertTrue(histories["EUR/USD"][0]["time"].endswith("+00:00"))

    def test_missing_api_key_fails_before_opening_network(self):
        opened = []
        client = TwelveDataClient(
            api_key="",
            opener=lambda *_args, **_kwargs: opened.append(True),
        )

        with self.assertRaises(TwelveDataConfigurationError):
            client.fetch_quotes(["SPY"])

        self.assertEqual(opened, [])

    def test_symbol_mappings_identify_etfs_and_currency_pairs(self):
        self.assertEqual(asset_type_for("GLD"), "ETF")
        self.assertEqual(asset_type_for("USO"), "ETF")
        self.assertEqual(asset_type_for("BTC/USD"), "Cryptocurrency")
        self.assertEqual(asset_type_for("EUR/USD"), "Forex")
        self.assertEqual(display_name_for("USO", None), "United States Oil Fund ETF")
        self.assertNotIn("ES=F", VALID_SYMBOLS)
        self.assertEqual(
            MARKET_SYMBOLS,
            ("SPY", "QQQ", "IWM", "DIA", "GLD", "USO"),
        )
        self.assertEqual(len(MARKET_FLOW_SYMBOLS), 8)


class MarketDataServiceTests(unittest.TestCase):
    def setUp(self):
        self.current_time = [0]
        self.clock = lambda: self.current_time[0]
        self.provider = FakeProvider()
        self.service = MarketDataService(
            provider=self.provider,
            quote_ttl=900,
            quote_stale_ttl=21600,
            history_ttl=21600,
            history_stale_ttl=86400,
            clock=self.clock,
            credit_budget=generous_budget(self.clock),
        )

    def test_eight_quotes_are_batched_and_cached_for_fifteen_minutes(self):
        symbols = list(MARKET_FLOW_SYMBOLS)

        first, errors = self.service.get_quotes(symbols)
        self.current_time[0] = 899
        second, second_errors = self.service.get_quotes(symbols)

        self.assertEqual(errors, {})
        self.assertEqual(second_errors, {})
        self.assertEqual(self.provider.quote_calls, [symbols])
        self.assertEqual(first, second)
        self.assertTrue(all(item["data_state"] == "delayed" for item in first.values()))

        self.current_time[0] = 900
        self.service.get_quotes(symbols)
        self.assertEqual(len(self.provider.quote_calls), 2)

    def test_simultaneous_requests_share_one_refresh(self):
        self.provider.delay = 0.03

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(self.service.get_quote, ["SPY"] * 8))

        self.assertEqual(len(self.provider.quote_calls), 1)
        self.assertTrue(all(result["price"] == 100 for result in results))

    def test_stale_quote_is_returned_when_refresh_is_rate_limited(self):
        self.service.get_quote("SPY")
        self.current_time[0] = 901
        self.provider.quote_failure = TwelveDataRateLimited("limited")

        stale = self.service.get_quote("SPY")
        again = self.service.get_quote("SPY")

        self.assertTrue(stale["stale"])
        self.assertEqual(stale["data_state"], "stale")
        self.assertEqual(stale, again)
        self.assertEqual(len(self.provider.quote_calls), 2)

    def test_rate_limit_without_stale_data_is_reported(self):
        self.provider.quote_failure = TwelveDataRateLimited("limited")

        with self.assertRaises(MarketDataUnavailable) as context:
            self.service.get_quote("SPY")

        self.assertEqual(context.exception.state, "rate_limited")

    def test_unsupported_symbol_is_returned_as_partial_batch_error(self):
        self.provider.quote_errors["FAKE"] = TwelveDataUnsupported("unsupported")

        quotes, errors = self.service.get_quotes(["SPY", "FAKE"])

        self.assertIn("SPY", quotes)
        self.assertIn("unsupported", errors["FAKE"].lower())

    def test_history_is_cached_for_several_hours(self):
        first = self.service.get_history("SPY", period="1mo", interval="1d")
        self.current_time[0] = 21599
        second = self.service.get_history("SPY", period="1mo", interval="1d")

        self.assertEqual(first, second)
        self.assertEqual(len(self.provider.history_calls), 1)

        self.current_time[0] = 21600
        self.service.get_history("SPY", period="1mo", interval="1d")
        self.assertEqual(len(self.provider.history_calls), 2)

    def test_stale_history_falls_back_after_provider_failure(self):
        expected = self.service.get_history("SPY", period="1mo", interval="1d")
        self.current_time[0] = 21601
        self.provider.history_failure = TwelveDataError("offline")

        actual = self.service.get_history("SPY", period="1mo", interval="1d")

        self.assertEqual(actual, expected)
        self.assertEqual(len(self.provider.history_calls), 2)
        self.assertEqual(
            self.service.get_history_state("SPY", "1mo", "1d"),
            "stale",
        )

    def test_history_batch_returns_success_and_unsupported_state(self):
        self.provider.history_errors["USO"] = TwelveDataUnsupported("unsupported")

        histories, errors = self.service.get_intraday_histories(["GLD", "USO"])

        self.assertIn("GLD", histories)
        self.assertIn("unsupported", errors["USO"].lower())

    def test_credit_budget_blocks_more_than_eight_credits_per_minute(self):
        budget = CreditBudget(clock=self.clock)
        budget.reserve(8)

        with self.assertRaises(MarketDataUnavailable) as context:
            budget.reserve(1)

        self.assertEqual(context.exception.state, "rate_limited")

        self.current_time[0] = 61
        budget.reserve(8)

    def test_credit_budget_enforces_rolling_daily_limit(self):
        budget = CreditBudget(
            minute_limit=1000,
            daily_limit=800,
            clock=self.clock,
        )
        budget.reserve(800)

        with self.assertRaises(MarketDataUnavailable) as context:
            budget.reserve(1)

        self.assertEqual(context.exception.state, "rate_limited")


if __name__ == "__main__":
    unittest.main()
