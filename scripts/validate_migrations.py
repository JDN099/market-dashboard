import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def validate_migrations():
    from services.database import get_db_connection

    load_dotenv(PROJECT_ROOT / ".env")
    migration_paths = sorted(
        (PROJECT_ROOT / "migrations").glob("[0-9][0-9][0-9]_*.sql")
    )
    schema_name = f"marketv_validation_{uuid.uuid4().hex}"
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA "{schema_name}"')
            cursor.execute(f'SET LOCAL search_path TO "{schema_name}"')
            cursor.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            for path in migration_paths:
                version = int(path.name.split("_", 1)[0])
                cursor.execute(path.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )

            cursor.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = %s
                ORDER BY tablename
                """,
                (schema_name,),
            )
            tables = {row[0] for row in cursor.fetchall()}

        required_tables = {
            "economic_calendar_events",
            "economic_calendar_provider_state",
            "schema_migrations",
            "watchlist_entries",
        }
        missing_tables = sorted(required_tables - tables)
        if missing_tables:
            raise RuntimeError(
                f"Migration validation is missing tables: {', '.join(missing_tables)}"
            )

        print(
            f"Validated {len(migration_paths)} migrations in a temporary PostgreSQL schema"
        )
    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    validate_migrations()
