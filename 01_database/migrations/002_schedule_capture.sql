CREATE TABLE IF NOT EXISTS credit.input_load (
    load_id BIGSERIAL PRIMARY KEY,
    batch_name TEXT NOT NULL,
    application_id TEXT NOT NULL,
    action TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credit.schedule_capture (
    capture_id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    application_id TEXT REFERENCES credit.loan_application (application_id),
    load_action TEXT NOT NULL,
    recommendation TEXT,
    pd_display TEXT,
    run_id TEXT REFERENCES credit.decision (run_id),
    detail TEXT NOT NULL
);
