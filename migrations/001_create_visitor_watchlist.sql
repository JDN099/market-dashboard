CREATE TABLE IF NOT EXISTS watchlist_entries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    visitor_id VARCHAR(43) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT watchlist_entries_visitor_symbol_key UNIQUE (visitor_id, symbol)
);

CREATE INDEX IF NOT EXISTS watchlist_entries_visitor_added_idx
    ON watchlist_entries (visitor_id, added_at DESC, id DESC);
