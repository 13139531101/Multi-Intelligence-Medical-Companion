-- PostgreSQL DDL for medication reminders, appointment reminders, reminder logs,
-- and health records with file attachments

-- Medication reminders
CREATE TABLE IF NOT EXISTS medication_reminders (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    medication_name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    frequency TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    reminder_times JSONB NOT NULL,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_medication_reminders_user ON medication_reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_medication_reminders_active ON medication_reminders(is_active);
CREATE INDEX IF NOT EXISTS idx_medication_reminders_created ON medication_reminders(created_at);

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
    scheduled_time TIMESTAMPTZ NOT NULL,
    actual_time TIMESTAMPTZ,
    status TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reminder_logs_reminder ON reminder_logs(reminder_id);
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