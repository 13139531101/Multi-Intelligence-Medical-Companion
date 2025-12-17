-- =====================================================
-- 个人智能健康助手数据库设计 (PostgreSQL Version)
-- 基于A2A-MCP Server框架
-- 数据库类型：PostgreSQL 16+
-- =====================================================

-- 启用 pgvector 扩展 (如果需要向量检索)
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- 1. 用户管理相关表
-- =====================================================

-- 用户基本信息表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL UNIQUE,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    salt VARCHAR(32) NOT NULL,
    email VARCHAR(100) UNIQUE,
    phone VARCHAR(20) UNIQUE,
    avatar_url VARCHAR(255),
    last_login_at TIMESTAMPTZ,
    login_count INT DEFAULT 0,
    status SMALLINT DEFAULT 1, -- 1-正常，0-禁用
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 用户会话表（用于JWT token管理）
CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    is_active SMALLINT DEFAULT 1, -- 1-是，0-否
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(token_hash);

-- 用户个人档案表
CREATE TABLE IF NOT EXISTS user_profiles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    real_name VARCHAR(50),
    gender VARCHAR(10), -- male, female, other
    birth_date DATE,
    height DECIMAL(5,2),
    weight DECIMAL(5,2),
    blood_type VARCHAR(10), -- A, B, AB, O, unknown
    emergency_contact VARCHAR(50),
    emergency_phone VARCHAR(20),
    allergies TEXT,
    chronic_diseases TEXT,
    family_history TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 2. 健康档案管理相关表
-- =====================================================

-- 健康档案主表
CREATE TABLE IF NOT EXISTS health_records (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    record_type VARCHAR(50) NOT NULL, -- prescription, test_report, etc.
    title VARCHAR(200) NOT NULL,
    content_encrypted BYTEA,
    extracted_data_encrypted BYTEA,
    file_hash VARCHAR(64),
    hospital_name VARCHAR(100),
    department VARCHAR(50),
    doctor_name VARCHAR(50),
    visit_date DATE,
    tags JSONB,
    is_deleted SMALLINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_health_records_user_id ON health_records(user_id);
CREATE INDEX IF NOT EXISTS idx_health_records_type ON health_records(record_type);

-- 健康档案附件表
CREATE TABLE IF NOT EXISTS health_record_attachments (
    id SERIAL PRIMARY KEY,
    record_id INT NOT NULL REFERENCES health_records(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    file_path VARCHAR(500),
    file_url VARCHAR(500),
    thumbnail_url VARCHAR(500),
    upload_status SMALLINT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attachments_record_id ON health_record_attachments(record_id);

-- =====================================================
-- 3. 用药管理相关表
-- =====================================================

-- 药物基础信息表
CREATE TABLE IF NOT EXISTS medications_base (
    id SERIAL PRIMARY KEY,
    drug_name VARCHAR(100) NOT NULL,
    generic_name VARCHAR(100),
    drug_type VARCHAR(20), -- prescription, otc, etc.
    manufacturer VARCHAR(100),
    specifications VARCHAR(100),
    dosage_form VARCHAR(50), -- tablet, capsule, etc.
    active_ingredients TEXT,
    indications TEXT,
    contraindications TEXT,
    side_effects TEXT,
    drug_interactions TEXT,
    storage_conditions VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 用户用药记录表
CREATE TABLE IF NOT EXISTS user_medications (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    medication_id INT REFERENCES medications_base(id) ON DELETE SET NULL,
    drug_name VARCHAR(100) NOT NULL,
    dosage VARCHAR(50) NOT NULL,
    frequency VARCHAR(100) NOT NULL,
    usage_method VARCHAR(100),
    start_date DATE NOT NULL,
    end_date DATE,
    duration_days INT,
    total_quantity DECIMAL(10,2),
    remaining_quantity DECIMAL(10,2),
    unit VARCHAR(20),
    notes TEXT,
    prescription_source VARCHAR(100),
    doctor_name VARCHAR(50),
    is_active SMALLINT DEFAULT 1,
    is_deleted SMALLINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_medications_user_id ON user_medications(user_id);

-- =====================================================
-- 4. 提醒管理相关表
-- =====================================================

-- 提醒主表
CREATE TABLE IF NOT EXISTS reminders (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reminder_type VARCHAR(20) NOT NULL, -- medication, checkup, etc.
    title VARCHAR(200) NOT NULL,
    description TEXT,
    reminder_time TIMESTAMPTZ NOT NULL,
    repeat_type VARCHAR(20) DEFAULT 'none',
    repeat_interval INT DEFAULT 1,
    repeat_days VARCHAR(20),
    end_repeat_date DATE,
    advance_minutes INT DEFAULT 0,
    is_completed SMALLINT DEFAULT 0,
    is_active SMALLINT DEFAULT 1,
    is_deleted SMALLINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id);

-- =====================================================
-- 5. 健康咨询相关表 (Updated to match Backend API)
-- =====================================================

-- 咨询会话表 (Matches backend 'consultations' table)
CREATE TABLE IF NOT EXISTS consultations (
    consultation_id TEXT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title TEXT,
    consultation_type TEXT, -- general, etc.
    agent_id TEXT,
    status TEXT,
    question TEXT,
    session_id TEXT,
    tags JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_consultations_user_id ON consultations(user_id);
CREATE INDEX IF NOT EXISTS idx_consultations_created_at ON consultations(created_at DESC);

-- 咨询消息表 (Matches backend 'chat_messages' table)
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    consultation_id TEXT NOT NULL REFERENCES consultations(consultation_id) ON DELETE CASCADE,
    role TEXT NOT NULL, -- user, assistant, system
    content TEXT NOT NULL,
    files JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_consultation_id ON chat_messages(consultation_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at ASC);

-- =====================================================
-- 6. 就诊摘要相关表
-- =====================================================

-- 就诊摘要表
CREATE TABLE IF NOT EXISTS visit_summaries (
    id TEXT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title TEXT NOT NULL,
    visit_date DATE,
    doctor TEXT,
    hospital TEXT,
    department TEXT,
    chief_complaint TEXT,
    symptoms TEXT,
    examination TEXT,
    diagnosis TEXT,
    treatment TEXT,
    prescription TEXT,
    follow_up TEXT,
    notes TEXT,
    files JSONB,
    tests JSONB,
    is_deleted SMALLINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_visit_summaries_user_id ON visit_summaries(user_id);

-- =====================================================
-- 7. 系统管理相关表
-- =====================================================

-- 智能体配置表
CREATE TABLE IF NOT EXISTS agent_configs (
    id SERIAL PRIMARY KEY,
    agent_type VARCHAR(50) NOT NULL,
    agent_name VARCHAR(100) NOT NULL,
    agent_url VARCHAR(255) NOT NULL,
    port INT NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    config_data JSONB,
    version VARCHAR(20),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 系统日志表
CREATE TABLE IF NOT EXISTS system_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64),
    action VARCHAR(100) NOT NULL,
    module VARCHAR(50) NOT NULL,
    level VARCHAR(10) DEFAULT 'INFO',
    message TEXT NOT NULL,
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 8. 数据初始化
-- =====================================================

-- 插入智能体配置数据
INSERT INTO agent_configs (agent_type, agent_name, agent_url, port, description) VALUES
('health_records_manager', '健康档案管理员', 'http://127.0.0.1:10010', 10010, '负责健康档案的录入、解析和安全存储'),
('health_advisor', '健康顾问', 'http://127.0.0.1:10011', 10011, '提供健康咨询和建议服务'),
('medication_assistant', '用药提醒助手', 'http://127.0.0.1:10012', 10012, '管理用药计划、发送提醒、跟踪库存'),
('summary_generator', '就诊摘要生成器', 'http://127.0.0.1:10013', 10013, '整合信息，生成就诊摘要和医疗文档分析');
