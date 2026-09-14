import unittest
from unittest.mock import patch

import app
from services.market_data import MarketDataUnavailable


class MarketRoutesTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_batch_deduplicates_and_returns_partial_errors(self):
        quote = {"symbol": "SPY", "price": 100, "change": 1}
        with patch.object(app.market_data, "get_quotes", return_value=(
            {"SPY": quote},
            {"QQQ": "Quote unavailable for QQQ"},
        )) as fetch:
            response = self.client.get("/api/quotes?symbols=SPY,QQQ,SPY")

        self.assertEqual(response.status_code, 200)
        fetch.assert_called_once_with(["SPY", "QQQ"])
        self.assertEqual(response.json["quotes"]["SPY"], quote)
        self.assertIn("QQQ", response.json["errors"])

    def test_batch_rejects_unsupported_symbols(self):
        response = self.client.get("/api/quotes?symbols=SPY,NOT-A-TICKER")
        self.assertEqual(response.status_code, 400)

    def test_batch_returns_unavailable_when_all_quotes_fail(self):
        with patch.object(app.market_data, "get_quotes", return_value=(
            {},
            {"SPY": "Quote unavailable for SPY"},
        )):
            response = self.client.get("/api/quotes?symbols=SPY")

        self.assertEqual(response.status_code, 503)
        self.assertIn("SPY", response.json["errors"])

    def test_single_quote_reports_provider_failure(self):
        with patch.object(
            app.market_data,
            "get_quote",
            side_effect=MarketDataUnavailable("Quote unavailable for SPY"),
        ):
            response = self.client.get("/quote?ticker=SPY")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "Quote unavailable for SPY")

    def test_history_route_returns_points(self):
        points = [{"time": "2026-01-01T00:00:00", "close": 100}]
        with patch.object(app.market_data, "get_history", return_value=points):
            response = self.client.get("/api/history?symbol=SPY&period=1mo&interval=1d")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["points"], points)

    def test_history_rejects_invalid_symbol(self):
        response = self.client.get("/api/history?symbol=UNKNOWN")
        self.assertEqual(response.status_code, 400)

    def test_legacy_watchlist_quotes_route_is_removed(self):
        response = self.client.get("/watchlist/quotes")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
