CREATE TABLE IF NOT EXISTS credit.operator_log (
    turn_id BIGSERIAL PRIMARY KEY,
    asked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    message TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_ok BOOLEAN NOT NULL,
    reply TEXT NOT NULL,
    source TEXT NOT NULL
);
