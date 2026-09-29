import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def apply_migrations():
    from services.database import get_db_connection

    load_dotenv(PROJECT_ROOT / ".env")
    paths = sorted((PROJECT_ROOT / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_lock(hashtext(%s))",
                ("marketv_schema_migrations",),
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        connection.commit()

        for path in paths:
            version = int(path.name.split("_", 1)[0])
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                )
                if cursor.fetchone():
                    print(f"Already applied: {path.name}")
                    continue

                cursor.execute(path.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            connection.commit()
            print(f"Applied: {path.name}")
    except Exception:
        connection.rollback()
        raise
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))",
                    ("marketv_schema_migrations",),
                )
            connection.commit()
        except Exception:
            connection.rollback()
        connection.close()


if __name__ == "__main__":
    apply_migrations()
