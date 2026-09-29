import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MigrationDefinitionTests(unittest.TestCase):
    def test_migrations_are_numbered_and_create_required_tables(self):
        paths = sorted((PROJECT_ROOT / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
        versions = [int(path.name.split("_", 1)[0]) for path in paths]

        self.assertEqual(versions, [1, 2])

        combined_sql = "\n".join(
            path.read_text(encoding="utf-8").lower() for path in paths
        )
        self.assertIn("create table if not exists watchlist_entries", combined_sql)
        self.assertIn("create table if not exists economic_calendar_events", combined_sql)
        self.assertIn(
            "create table if not exists economic_calendar_provider_state",
            combined_sql,
        )

    def test_deployment_migrations_use_a_postgres_advisory_lock(self):
        migration_runner = (PROJECT_ROOT / "scripts" / "migrate.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("pg_advisory_lock", migration_runner)
        self.assertIn("pg_advisory_unlock", migration_runner)


if __name__ == "__main__":
    unittest.main()
