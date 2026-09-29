import os
import unittest
from unittest.mock import patch

from services.database import get_db_connection


class DatabaseConfigurationTests(unittest.TestCase):
    def test_database_url_uses_ssl_by_default(self):
        environment = {
            "DATABASE_URL": "postgresql://example:secret@host.example/marketv",
            "DB_CONNECT_TIMEOUT": "12",
        }

        with patch.dict(os.environ, environment, clear=True):
            with patch("services.database.psycopg2.connect") as connect:
                get_db_connection()

        connect.assert_called_once_with(
            environment["DATABASE_URL"],
            connect_timeout=12,
            sslmode="require",
        )

    def test_database_url_preserves_embedded_ssl_mode(self):
        database_url = (
            "postgresql://example:secret@host.example/marketv?sslmode=verify-full"
        )

        with patch.dict(os.environ, {"DATABASE_URL": database_url}, clear=True):
            with patch("services.database.psycopg2.connect") as connect:
                get_db_connection()

        connect.assert_called_once_with(database_url, connect_timeout=10)

    def test_local_variables_are_used_when_database_url_is_empty(self):
        environment = {
            "DATABASE_URL": "",
            "DB_NAME": "market_dashboard",
            "DB_USER": "postgres",
            "DB_PASSWORD": "local-password",
            "DB_HOST": "localhost",
            "DB_PORT": "5432",
        }

        with patch.dict(os.environ, environment, clear=True):
            with patch("services.database.psycopg2.connect") as connect:
                get_db_connection()

        connect.assert_called_once_with(
            dbname="market_dashboard",
            user="postgres",
            password="local-password",
            host="localhost",
            port="5432",
            connect_timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
