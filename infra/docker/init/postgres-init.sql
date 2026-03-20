-- Computer PostgreSQL initialization
-- Creates the database schema for development

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- Jobs table (Orchestrator owns this)
CREATE TABLE IF NOT EXISTS jobs (
    job_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id      UUID,
    type            VARCHAR(100) NOT NULL,
    requested_by    VARCHAR(100) NOT NULL,
    origin          VARCHAR(50)  NOT NULL CHECK (origin IN ('operator','policy','ai_advisory','sensor_rule','emergency')),
    target_asset_ids JSONB       NOT NULL DEFAULT '[]',
    target_capability VARCHAR(200),
    target_zone     VARCHAR(100),
    parameters      JSONB        NOT NULL DEFAULT '{}',
    risk_class      VARCHAR(50)  NOT NULL CHECK (risk_class IN ('INFORMATIONAL','LOW','MEDIUM','HIGH','CRITICAL')),
    approval_mode   VARCHAR(50)  NOT NULL,
    state           VARCHAR(50)  NOT NULL DEFAULT 'PENDING',
    preconditions   JSONB        NOT NULL DEFAULT '[]',
    abort_conditions JSONB       NOT NULL DEFAULT '[]',
    command_log     JSONB        NOT NULL DEFAULT '[]',
    telemetry_refs  JSONB        NOT NULL DEFAULT '[]',
    approval_event  JSONB,
    rejection_reason TEXT,
    timeout_seconds INTEGER      NOT NULL DEFAULT 300,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_origin ON jobs(origin);
CREATE INDEX IF NOT EXISTS idx_jobs_risk_class ON jobs(risk_class);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_request_id ON jobs(request_id);

-- Assets table (Digital twin owns this)
CREATE TABLE IF NOT EXISTS assets (
    asset_id            VARCHAR(200) PRIMARY KEY,
    name                VARCHAR(200) NOT NULL,
    asset_type          VARCHAR(200) NOT NULL,
    capabilities        JSONB        NOT NULL DEFAULT '[]',
    zone                VARCHAR(100) NOT NULL,
    location_description TEXT,
    state               JSONB        NOT NULL DEFAULT '{}',
    state_source        VARCHAR(100),
    state_updated_at    TIMESTAMPTZ,
    operational_status  VARCHAR(50)  NOT NULL DEFAULT 'UNKNOWN',
    qualification_level VARCHAR(10)  NOT NULL DEFAULT 'QA0',
    vendor_entity       VARCHAR(200),  -- adapter-only; never used by orchestrator
    mqtt_topic_prefix   VARCHAR(300),
    calibration_due_at  TIMESTAMPTZ,
    maintenance_notes   JSONB        NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assets_asset_type ON assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_assets_zone ON assets(zone);
CREATE INDEX IF NOT EXISTS idx_assets_operational_status ON assets(operational_status);

-- Events table (Event ingest owns this)
CREATE TABLE IF NOT EXISTS events (
    event_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id      UUID,
    job_id          UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
    event_type      VARCHAR(50)  NOT NULL,
    source_service  VARCHAR(100) NOT NULL,
    asset_id        VARCHAR(200) REFERENCES assets(asset_id) ON DELETE SET NULL,
    zone            VARCHAR(100),
    severity        VARCHAR(20)  NOT NULL DEFAULT 'INFO',
    timestamp       TIMESTAMPTZ  NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    payload         JSONB        NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_asset_id ON events(asset_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);

-- Audit log (append-only; orchestrator writes this)
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id          UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
    request_id      UUID,
    actor           VARCHAR(100),
    action          VARCHAR(200) NOT NULL,
    resource_type   VARCHAR(50),
    resource_id     VARCHAR(200),
    details         JSONB        NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_job_id ON audit_log(job_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at DESC);

-- Schema version tracking (Alembic manages this, but we create it here as bootstrap)
-- Alembic will manage migrations from here forward.
