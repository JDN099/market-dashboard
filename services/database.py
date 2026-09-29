import os

import psycopg2


def get_db_connection():
    database_url = os.getenv("DATABASE_URL", "").strip()
    connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

    if database_url:
        connection_options = {
            "connect_timeout": connect_timeout,
        }
        if "sslmode=" not in database_url.lower():
            connection_options["sslmode"] = os.getenv("DB_SSLMODE", "require")

        return psycopg2.connect(database_url, **connection_options)

    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        connect_timeout=connect_timeout,
    )
