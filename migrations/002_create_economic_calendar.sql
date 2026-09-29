CREATE TABLE IF NOT EXISTS economic_calendar_events (
    event_id VARCHAR(80) PRIMARY KEY,
    provider VARCHAR(40) NOT NULL,
    event_name TEXT NOT NULL,
    country VARCHAR(8) NOT NULL,
    currency VARCHAR(8) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    importance VARCHAR(12) NOT NULL,
    reporting_period VARCHAR(120),
    actual VARCHAR(80),
    forecast VARCHAR(80),
    previous VARCHAR(80),
    source_name VARCHAR(120) NOT NULL,
    source_url TEXT NOT NULL,
    status VARCHAR(24) NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fetched_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT economic_calendar_importance_check
        CHECK (importance IN ('high', 'medium', 'low'))
);

CREATE INDEX IF NOT EXISTS economic_calendar_scheduled_idx
    ON economic_calendar_events (scheduled_at);

CREATE INDEX IF NOT EXISTS economic_calendar_provider_scheduled_idx
    ON economic_calendar_events (provider, scheduled_at);

CREATE INDEX IF NOT EXISTS economic_calendar_importance_scheduled_idx
    ON economic_calendar_events (importance, scheduled_at);

CREATE TABLE IF NOT EXISTS economic_calendar_provider_state (
    provider VARCHAR(40) PRIMARY KEY,
    last_successful_refresh TIMESTAMPTZ,
    last_attempted_refresh TIMESTAMPTZ,
    latest_error TEXT
);
