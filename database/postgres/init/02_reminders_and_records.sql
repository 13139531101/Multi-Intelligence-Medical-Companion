-- PostgreSQL DDL for medication reminders, appointment reminders, reminder logs,
-- and health records with file attachments

-- User medications
CREATE TABLE IF NOT EXISTS user_medications (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    drug_name TEXT NOT NULL,
    dosage TEXT,
    frequency TEXT,
    start_date DATE,
    end_date DATE,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_medications_user_id ON user_medications(user_id);

-- Medication reminders
CREATE TABLE IF NOT EXISTS medication_reminders (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    medication_name TEXT NOT NULL,
    dosage TEXT,
    frequency TEXT,
    start_date DATE,
    end_date DATE,
    reminder_times JSONB NOT NULL,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,
    medication_id INTEGER,
    reminder_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_medication_reminders_user ON medication_reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_medication_reminders_active ON medication_reminders(is_active);
CREATE INDEX IF NOT EXISTS idx_medication_reminders_created ON medication_reminders(created_at);
CREATE INDEX IF NOT EXISTS idx_medication_reminders_user_created_desc ON medication_reminders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_medication_reminders_user_medication ON medication_reminders(user_id, medication_id);

-- Appointment reminders
CREATE TABLE IF NOT EXISTS appointment_reminders (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    doctor_name TEXT NOT NULL,
    department TEXT NOT NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    hospital TEXT NOT NULL,
    notes TEXT,
    reminder_advance_days INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_appointment_reminders_user ON appointment_reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_appointment_reminders_date ON appointment_reminders(appointment_date);

-- Reminder logs
CREATE TABLE IF NOT EXISTS reminder_logs (
    id SERIAL PRIMARY KEY,
    reminder_id INTEGER NOT NULL REFERENCES medication_reminders(id) ON DELETE CASCADE,
    user_id TEXT,
    scheduled_time TIMESTAMPTZ NOT NULL,
    actual_time TIMESTAMPTZ,
    status TEXT NOT NULL,
    notes TEXT,
    completion_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reminder_logs_reminder ON reminder_logs(reminder_id);
CREATE INDEX IF NOT EXISTS idx_reminder_logs_reminder_scheduled ON reminder_logs(reminder_id, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_reminder_logs_user_scheduled ON reminder_logs(user_id, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_reminder_logs_status ON reminder_logs(status);
CREATE INDEX IF NOT EXISTS idx_reminder_logs_created ON reminder_logs(created_at);

-- Health records
CREATE TABLE IF NOT EXISTS health_records (
    id UUID PRIMARY KEY,
    user_id TEXT,
    title TEXT NOT NULL,
    record_type TEXT NOT NULL,
    summary TEXT,
    content TEXT,
    importance TEXT NOT NULL DEFAULT 'medium',
    tags JSONB,
    metadata JSONB,
    record_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_records_user ON health_records(user_id);
CREATE INDEX IF NOT EXISTS idx_health_records_type ON health_records(record_type);
CREATE INDEX IF NOT EXISTS idx_health_records_importance ON health_records(importance);
CREATE INDEX IF NOT EXISTS idx_health_records_date ON health_records(record_date);

-- File attachments (one-to-many with health_records)
CREATE TABLE IF NOT EXISTS file_attachments (
    id UUID PRIMARY KEY,
    record_id UUID REFERENCES health_records(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    mime_type TEXT,
    upload_time TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_file_attachments_record ON file_attachments(record_id);

-- RAG chunks (pgvector)
CREATE TABLE IF NOT EXISTS rag_documents (
    user_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    record_type TEXT,
    title TEXT,
    full_text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, source_type, source_id, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_user ON rag_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_user_source ON rag_documents(user_id, source_type);
CREATE INDEX IF NOT EXISTS idx_rag_documents_source ON rag_documents(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_updated ON rag_documents(updated_at);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    record_type TEXT,
    title TEXT,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, source_type, source_id, chunk_index, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_user ON rag_chunks(user_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_user_source ON rag_chunks(user_id, source_type);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_source ON rag_chunks(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_created ON rag_chunks(created_at);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
