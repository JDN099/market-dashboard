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

    def test_batch_rejects_more_than_eight_symbols(self):
        symbols = "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD,SPY"
        response = self.client.get(f"/api/quotes?symbols={symbols}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "Provide 1 to 8 symbols")

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
        self.assertEqual(
            response.json["error"],
            "Market data is unavailable right now",
        )

    def test_history_route_returns_points(self):
        points = [{"time": "2026-01-01T00:00:00", "close": 100}]
        with patch.object(app.market_data, "get_history", return_value=points):
            response = self.client.get("/api/history?symbol=SPY&period=1mo&interval=1d")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["points"], points)

    def test_history_route_accepts_intraday_range(self):
        points = [{"time": "2026-09-11T09:30:00-04:00", "close": 100}]
        with patch.object(app.market_data, "get_history", return_value=points) as get_history:
            response = self.client.get("/api/history?symbol=SPY&period=1d&interval=5m")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["points"], points)
        get_history.assert_called_once_with("SPY", period="1d", interval="5m")

    def test_intraday_batch_deduplicates_and_returns_partial_errors(self):
        points = [{"time": "2026-09-11T09:30:00-04:00", "close": 100}]
        with patch.object(app.market_data, "get_intraday_histories", return_value=(
            {"SPY": points},
            {"QQQ": "History unavailable for QQQ"},
        )) as fetch:
            response = self.client.get("/api/history/batch?symbols=SPY,QQQ,SPY")

        self.assertEqual(response.status_code, 200)
        fetch.assert_called_once_with(["SPY", "QQQ"])
        self.assertEqual(response.json["histories"]["SPY"], points)
        self.assertIn("QQQ", response.json["errors"])

    def test_intraday_batch_limits_symbols(self):
        response = self.client.get("/api/history/batch?symbols=")
        self.assertEqual(response.status_code, 400)

        response = self.client.get("/api/history/batch?symbols=UNKNOWN")
        self.assertEqual(response.status_code, 400)

    def test_history_rejects_invalid_symbol(self):
        response = self.client.get("/api/history?symbol=UNKNOWN")
        self.assertEqual(response.status_code, 400)

    def test_legacy_watchlist_quotes_route_is_removed(self):
        response = self.client.get("/watchlist/quotes")
        self.assertEqual(response.status_code, 404)

    def test_dashboard_displays_delay_and_educational_notices(self):
        response = self.client.get("/markets")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Delayed market data", page)
        self.assertIn("GLD gold ETF", page)
        self.assertIn("USO oil ETF", page)
        self.assertNotIn("index futures", page)
        self.assertIn("For educational purposes only. Not financial advice.", page)
        self.assertNotIn("only — not financial advice", page)
        self.assertIn('id="news-status">Delayed', page)

    def test_dashboard_loads_split_ui_scripts_without_inline_search_handler(self):
        response = self.client.get("/markets")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/market-ui.js', page)
        self.assertIn('/static/dashboard-shell.js', page)
        self.assertIn('/static/watchlist-ui.js', page)
        self.assertIn('/static/search.js', page)
        self.assertIn('id="ticker-search-button"', page)
        self.assertNotIn('onclick="searchTicker()', page)

    def test_search_uses_twelve_data_symbols_and_labels(self):
        response = self.client.get("/search?q=USO")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json[0]["symbol"], "USO")
        self.assertIn("ETF", response.json[0]["instrument_name"])

        legacy_futures = self.client.get("/search?q=ES=F")
        self.assertEqual(legacy_futures.json, [])

    def test_news_page_displays_delay_and_educational_notices(self):
        response = self.client.get("/news-page")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Delayed news", page)
        self.assertIn("For educational purposes only. Not financial advice.", page)
        self.assertNotIn("only — not financial advice", page)
        self.assertIn('id="latest-news-status">Delayed', page)


if __name__ == "__main__":
    unittest.main()
