-- Migration: Initial schema (baseline)
-- Version: V20250827000000__init
-- Created: 2025-08-27
-- Description: Creates all baseline tables for PHA v2 multi-agent system

BEGIN;

-- Agent memory / RAG tables
CREATE TABLE IF NOT EXISTS agent_memory (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT NOT NULL,
    agent_name    TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    message_role  TEXT NOT NULL CHECK (message_role IN ('user','assistant','system')),
    content       TEXT NOT NULL,
    model         TEXT,
    token_count   INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_user_session
    ON agent_memory (user_id, session_id, created_at DESC);

-- RAG chunk storage
CREATE TABLE IF NOT EXISTS rag_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    doc_id      TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(1024),
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_user_doc
    ON rag_chunks (user_id, doc_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
    ON rag_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH lists = 100;

-- Medication reminders
CREATE TABLE IF NOT EXISTS medication_reminders (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT NOT NULL,
    drug_name     TEXT NOT NULL,
    dosage        TEXT,
    frequency     TEXT,
    remind_time   TIMESTAMPTZ NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending','taken','missed','skipped')),
    taken_at      TIMESTAMPTZ,
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_med_reminders_user_time
    ON medication_reminders (user_id, remind_time DESC);

-- Visit summaries
CREATE TABLE IF NOT EXISTS visit_summaries (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT NOT NULL,
    visit_date    DATE,
    hospital      TEXT,
    department    TEXT,
    doctor        TEXT,
    diagnosis     TEXT,
    medications   JSONB,
    summary_text  TEXT,
    raw_text      TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_visit_summaries_user
    ON visit_summaries (user_id, visit_date DESC);

-- Health records
CREATE TABLE IF NOT EXISTS health_records (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT NOT NULL,
    record_type   TEXT NOT NULL,
    title         TEXT,
    content       TEXT,
    file_url      TEXT,
    ocr_text      TEXT,
    tags          TEXT[],
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_records_user_type
    ON health_records (user_id, record_type);

-- Audit log (LLM indicator audit trail)
CREATE TABLE IF NOT EXISTS audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT,
    agent_name    TEXT,
    action        TEXT NOT NULL,
    request_data  JSONB,
    response_data JSONB,
    llm_model     TEXT,
    token_used    INTEGER,
    latency_ms    INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_user_time
    ON audit_log (user_id, created_at DESC);

-- Schema migrations tracking (managed by migrate.py — this table is created by migrate.py itself)
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          SERIAL PRIMARY KEY,
    version     VARCHAR(64) UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    VARCHAR(64) NOT NULL,
    rollback_sql TEXT
);

COMMIT;

-- rollback:
-- DROP TABLE IF EXISTS audit_log;
-- DROP TABLE IF EXISTS health_records;
-- DROP TABLE IF EXISTS visit_summaries;
-- DROP TABLE IF EXISTS medication_reminders;
-- DROP TABLE IF EXISTS rag_chunks;
-- DROP TABLE IF EXISTS agent_memory;
-- DROP TABLE IF EXISTS schema_migrations;
