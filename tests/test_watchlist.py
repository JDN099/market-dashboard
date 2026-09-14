import unittest
from unittest.mock import patch

import app
from services.watchlist import WatchlistStore


class FakeCursor:
    def __init__(self, data):
        self.data = data
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def execute(self, statement, parameters):
        self.data.queries.append((statement, parameters))
        self.data.assert_visitor_filter(statement)

        if "SELECT symbol" in statement:
            visitor_id = parameters[0]
            self.rows = [(symbol,) for symbol in self.data.symbols.get(visitor_id, [])]
        elif "INSERT INTO" in statement:
            visitor_id, symbol = parameters
            items = self.data.symbols.setdefault(visitor_id, [])
            if symbol not in items:
                items.insert(0, symbol)
        elif "DELETE FROM" in statement:
            visitor_id, symbol = parameters
            items = self.data.symbols.setdefault(visitor_id, [])
            if symbol in items:
                items.remove(symbol)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, data):
        self.data = data

    def cursor(self):
        return FakeCursor(self.data)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class FakeDatabase:
    def __init__(self):
        self.symbols = {}
        self.queries = []

    def connect(self):
        return FakeConnection(self)

    def assert_visitor_filter(self, statement):
        if "SELECT symbol" in statement or "DELETE FROM" in statement:
            assert "WHERE visitor_id = %s" in statement
        if "INSERT INTO" in statement:
            assert "(visitor_id, symbol)" in statement
            assert "ON CONFLICT (visitor_id, symbol)" in statement


class WatchlistIsolationTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.store_patch = patch.object(
            app,
            "watchlist_store",
            WatchlistStore(connection_factory=self.database.connect),
        )
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.first_browser = app.app.test_client()
        self.second_browser = app.app.test_client()

    def test_two_browsers_have_separate_lists(self):
        first_add = self.first_browser.post("/watchlist/add", json={"symbol": "AAPL"})
        second_add = self.second_browser.post("/watchlist/add", json={"symbol": "MSFT"})

        self.assertEqual(first_add.status_code, 200)
        self.assertEqual(second_add.status_code, 200)
        self.assertEqual(self.first_browser.get("/watchlist").json["watchlist"], ["AAPL"])
        self.assertEqual(self.second_browser.get("/watchlist").json["watchlist"], ["MSFT"])

        self.second_browser.delete("/watchlist/remove", json={"symbol": "AAPL"})
        self.assertEqual(self.first_browser.get("/watchlist").json["watchlist"], ["AAPL"])
        self.assertEqual(self.second_browser.get("/watchlist").json["watchlist"], ["MSFT"])

        visitor_ids = list(self.database.symbols)
        self.assertEqual(len(visitor_ids), 2)
        self.assertNotEqual(visitor_ids[0], visitor_ids[1])

    def test_cookie_is_random_http_only_and_lax(self):
        response = self.first_browser.get("/watchlist")
        cookie = response.headers["Set-Cookie"]

        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertRegex(cookie, r"marketv_visitor=[A-Za-z0-9_-]{43}")
        self.assertNotIn("Secure;", cookie)

        second_response = self.first_browser.get("/watchlist")
        self.assertNotIn("Set-Cookie", second_response.headers)

    def test_secure_cookie_can_be_forced_behind_https_proxy(self):
        with patch.dict("os.environ", {"VISITOR_COOKIE_SECURE": "true"}):
            response = self.first_browser.get("/watchlist")

        self.assertIn("Secure", response.headers["Set-Cookie"])

    def test_unsupported_symbol_is_rejected(self):
        response = self.first_browser.post("/watchlist/add", json={"symbol": "FAKE"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.database.symbols, {})

    def test_database_failure_returns_json_service_error(self):
        with patch.object(app.watchlist_store, "get_symbols", side_effect=RuntimeError("missing table")):
            response = self.first_browser.get("/watchlist")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json, {"error": "Watchlist unavailable"})


if __name__ == "__main__":
    unittest.main()
