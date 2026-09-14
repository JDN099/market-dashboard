from services.database import get_db_connection


class WatchlistStore:
    def __init__(self, connection_factory=None):
        self.connection_factory = connection_factory or get_db_connection

    def get_symbols(self, visitor_id):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT symbol
                    FROM watchlist_entries
                    WHERE visitor_id = %s
                    ORDER BY added_at DESC, id DESC
                    """,
                    (visitor_id,),
                )
                return [row[0] for row in cursor.fetchall()]
        finally:
            connection.close()

    def add_symbol(self, visitor_id, symbol):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO watchlist_entries (visitor_id, symbol)
                    VALUES (%s, %s)
                    ON CONFLICT (visitor_id, symbol) DO NOTHING
                    """,
                    (visitor_id, symbol),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def remove_symbol(self, visitor_id, symbol):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM watchlist_entries
                    WHERE visitor_id = %s AND symbol = %s
                    """,
                    (visitor_id, symbol),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
