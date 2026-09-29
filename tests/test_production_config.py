import os
import unittest
from unittest.mock import patch

import app
from services.config import debug_enabled, env_flag


class ProductionConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_production_never_enables_debug_mode(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "FLASK_DEBUG": "true"},
            clear=True,
        ):
            self.assertFalse(debug_enabled())

    def test_debug_mode_is_explicit_in_development(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "development", "FLASK_DEBUG": "true"},
            clear=True,
        ):
            self.assertTrue(debug_enabled())
            self.assertTrue(env_flag("FLASK_DEBUG"))

    def test_health_does_not_call_providers_or_database(self):
        with patch.object(app.market_data, "get_quote") as quote:
            with patch.object(app, "get_market_news") as news:
                with patch.object(
                    app.economic_calendar_service,
                    "get_events",
                ) as calendar:
                    with patch.object(
                        app.watchlist_store,
                        "get_symbols",
                    ) as watchlist:
                        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json,
            {"service": "marketv", "status": "ok"},
        )
        quote.assert_not_called()
        news.assert_not_called()
        calendar.assert_not_called()
        watchlist.assert_not_called()

    def test_production_visitor_cookie_is_secure(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            with patch.object(app.watchlist_store, "get_symbols", return_value=[]):
                response = self.client.get("/watchlist")

        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)


if __name__ == "__main__":
    unittest.main()
