-- =====================================================
-- 个人智能健康助手数据库设计
-- 基于A2A-MCP Server框架
-- 数据库类型：MySQL 8.0+
-- 字符集：utf8mb4
-- 排序规则：utf8mb4_unicode_ci
-- =====================================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS personal_health_assistant 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE personal_health_assistant;

-- =====================================================
-- 1. 用户管理相关表
-- =====================================================

-- 用户基本信息表
CREATE TABLE users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID',
    user_id VARCHAR(64) NOT NULL UNIQUE COMMENT '用户唯一标识',
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    salt VARCHAR(32) NOT NULL COMMENT '密码盐值',
    email VARCHAR(100) UNIQUE COMMENT '邮箱',
    phone VARCHAR(20) UNIQUE COMMENT '手机号',
    avatar_url VARCHAR(255) COMMENT '头像URL',
    last_login_at TIMESTAMP NULL COMMENT '最后登录时间',
    login_count INT DEFAULT 0 COMMENT '登录次数',
    status TINYINT DEFAULT 1 COMMENT '状态：1-正常，0-禁用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_id (user_id),
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户基本信息表';

-- 用户会话表（用于JWT token管理）
CREATE TABLE user_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '会话ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    token_hash VARCHAR(255) NOT NULL COMMENT 'Token哈希',
    expires_at TIMESTAMP NOT NULL COMMENT '过期时间',
    ip_address VARCHAR(45) COMMENT 'IP地址',
    user_agent TEXT COMMENT '用户代理',
    is_active TINYINT DEFAULT 1 COMMENT '是否活跃：1-是，0-否',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_id (user_id),
    INDEX idx_token_hash (token_hash),
    INDEX idx_expires_at (expires_at),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户会话表';

-- 用户个人档案表
CREATE TABLE user_profiles (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '档案ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    real_name VARCHAR(50) COMMENT '真实姓名',
    gender ENUM('male', 'female', 'other') COMMENT '性别',
    birth_date DATE COMMENT '出生日期',
    height DECIMAL(5,2) COMMENT '身高(cm)',
    weight DECIMAL(5,2) COMMENT '体重(kg)',
    blood_type ENUM('A', 'B', 'AB', 'O', 'unknown') COMMENT '血型',
    emergency_contact VARCHAR(50) COMMENT '紧急联系人',
    emergency_phone VARCHAR(20) COMMENT '紧急联系电话',
    allergies TEXT COMMENT '过敏史',
    chronic_diseases TEXT COMMENT '慢性疾病史',
    family_history TEXT COMMENT '家族病史',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户个人档案表';

-- =====================================================
-- 2. 健康档案管理相关表
-- =====================================================

-- 健康档案主表
CREATE TABLE health_records (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '记录ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    record_type ENUM('prescription', 'test_report', 'medical_record', 'hospital_record', 'vaccination', 'surgery', 'other') NOT NULL COMMENT '记录类型',
    title VARCHAR(200) NOT NULL COMMENT '记录标题',
    content_encrypted LONGBLOB COMMENT '加密的原始内容',
    extracted_data_encrypted LONGBLOB COMMENT '加密的提取数据',
    file_hash VARCHAR(64) COMMENT '文件哈希值',
    hospital_name VARCHAR(100) COMMENT '医院名称',
    department VARCHAR(50) COMMENT '科室',
    doctor_name VARCHAR(50) COMMENT '医生姓名',
    visit_date DATE COMMENT '就诊日期',
    tags JSON COMMENT '标签',
    is_deleted TINYINT DEFAULT 0 COMMENT '是否删除：0-否，1-是',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_id (user_id),
    INDEX idx_record_type (record_type),
    INDEX idx_visit_date (visit_date),
    INDEX idx_hospital (hospital_name),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='健康档案主表';

-- 健康档案附件表
CREATE TABLE health_record_attachments (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '附件ID',
    record_id BIGINT UNSIGNED NOT NULL COMMENT '档案记录ID',
    file_name VARCHAR(255) NOT NULL COMMENT '文件名',
    file_type VARCHAR(50) COMMENT '文件类型',
    file_size BIGINT COMMENT '文件大小(字节)',
    file_path VARCHAR(500) COMMENT '文件路径',
    file_url VARCHAR(500) COMMENT '文件URL',
    thumbnail_url VARCHAR(500) COMMENT '缩略图URL',
    upload_status TINYINT DEFAULT 1 COMMENT '上传状态：1-成功，0-失败',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_record_id (record_id),
    INDEX idx_file_type (file_type),
    FOREIGN KEY (record_id) REFERENCES health_records(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='健康档案附件表';

-- =====================================================
-- 3. 用药管理相关表
-- =====================================================

-- 药物基础信息表
CREATE TABLE medications_base (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '药物ID',
    drug_name VARCHAR(100) NOT NULL COMMENT '药物名称',
    generic_name VARCHAR(100) COMMENT '通用名',
    drug_type ENUM('prescription', 'otc', 'supplement', 'other') COMMENT '药物类型',
    manufacturer VARCHAR(100) COMMENT '生产厂家',
    specifications VARCHAR(100) COMMENT '规格',
    dosage_form ENUM('tablet', 'capsule', 'liquid', 'injection', 'cream', 'other') COMMENT '剂型',
    active_ingredients TEXT COMMENT '主要成分',
    indications TEXT COMMENT '适应症',
    contraindications TEXT COMMENT '禁忌症',
    side_effects TEXT COMMENT '副作用',
    drug_interactions TEXT COMMENT '药物相互作用',
    storage_conditions VARCHAR(200) COMMENT '储存条件',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_drug_name (drug_name),
    INDEX idx_generic_name (generic_name),
    INDEX idx_drug_type (drug_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='药物基础信息表';

-- 用户用药记录表
CREATE TABLE user_medications (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '用药记录ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    medication_id BIGINT UNSIGNED COMMENT '药物基础信息ID',
    drug_name VARCHAR(100) NOT NULL COMMENT '药物名称',
    dosage VARCHAR(50) NOT NULL COMMENT '剂量',
    frequency VARCHAR(100) NOT NULL COMMENT '用药频率',
    usage_method VARCHAR(100) COMMENT '用法',
    start_date DATE NOT NULL COMMENT '开始日期',
    end_date DATE COMMENT '结束日期',
    duration_days INT COMMENT '用药天数',
    total_quantity DECIMAL(10,2) COMMENT '总数量',
    remaining_quantity DECIMAL(10,2) COMMENT '剩余数量',
    unit VARCHAR(20) COMMENT '单位',
    notes TEXT COMMENT '备注',
    prescription_source VARCHAR(100) COMMENT '处方来源',
    doctor_name VARCHAR(50) COMMENT '开药医生',
    is_active TINYINT DEFAULT 1 COMMENT '是否活跃：1-是，0-否',
    is_deleted TINYINT DEFAULT 0 COMMENT '是否删除：0-否，1-是',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_id (user_id),
    INDEX idx_medication_id (medication_id),
    INDEX idx_drug_name (drug_name),
    INDEX idx_start_date (start_date),
    INDEX idx_end_date (end_date),
    INDEX idx_is_active (is_active),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (medication_id) REFERENCES medications_base(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户用药记录表';

-- =====================================================
-- 4. 提醒管理相关表
-- =====================================================

-- 提醒主表
CREATE TABLE reminders (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '提醒ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    reminder_type ENUM('medication', 'checkup', 'appointment', 'exercise', 'diet', 'other') NOT NULL COMMENT '提醒类型',
    title VARCHAR(200) NOT NULL COMMENT '提醒标题',
    description TEXT COMMENT '提醒描述',
    reminder_time DATETIME NOT NULL COMMENT '提醒时间',
    repeat_type ENUM('none', 'daily', 'weekly', 'monthly', 'custom') DEFAULT 'none' COMMENT '重复类型',
    repeat_interval INT DEFAULT 1 COMMENT '重复间隔',
    repeat_days VARCHAR(20) COMMENT '重复日期(周几)',
    end_repeat_date DATE COMMENT '重复结束日期',
    advance_minutes INT DEFAULT 0 COMMENT '提前提醒分钟数',
    is_completed TINYINT DEFAULT 0 COMMENT '是否完成：0-否，1-是',
    is_active TINYINT DEFAULT 1 COMMENT '是否激活：1-是，0-否',
    is_deleted TINYINT DEFAULT 0 COMMENT '是否删除：0-否，1-是',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_id (user_id),
    INDEX idx_reminder_type (reminder_type),
    INDEX idx_reminder_time (reminder_time),
    INDEX idx_is_active (is_active),
    INDEX idx_is_completed (is_completed),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='提醒主表';

-- 用药提醒详情表
CREATE TABLE medication_reminders (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '用药提醒ID',
    reminder_id BIGINT UNSIGNED NOT NULL COMMENT '提醒ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    medication_id BIGINT UNSIGNED COMMENT '用药记录ID',
    medication_name VARCHAR(100) NOT NULL COMMENT '药物名称',
    dosage VARCHAR(50) NOT NULL COMMENT '剂量',
    frequency VARCHAR(100) NOT NULL COMMENT '频率',
    reminder_times JSON NOT NULL COMMENT '提醒时间点',
    start_date DATE NOT NULL COMMENT '开始日期',
    end_date DATE COMMENT '结束日期',
    notes TEXT COMMENT '备注',
    is_active TINYINT DEFAULT 1 COMMENT '是否激活：1-是，0-否',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_reminder_id (reminder_id),
    INDEX idx_user_id (user_id),
    INDEX idx_medication_id (medication_id),
    INDEX idx_start_date (start_date),
    INDEX idx_is_active (is_active),
    FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (medication_id) REFERENCES user_medications(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用药提醒详情表';

-- 提醒执行记录表
CREATE TABLE reminder_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '记录ID',
    reminder_id BIGINT UNSIGNED NOT NULL COMMENT '提醒ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    scheduled_time DATETIME NOT NULL COMMENT '计划提醒时间',
    actual_time DATETIME COMMENT '实际提醒时间',
    status ENUM('pending', 'sent', 'completed', 'skipped', 'failed') DEFAULT 'pending' COMMENT '状态',
    completion_time DATETIME COMMENT '完成时间',
    notes TEXT COMMENT '备注',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_reminder_id (reminder_id),
    INDEX idx_user_id (user_id),
    INDEX idx_scheduled_time (scheduled_time),
    INDEX idx_status (status),
    FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='提醒执行记录表';

-- =====================================================
-- 5. 健康咨询相关表
-- =====================================================

-- 咨询会话表
CREATE TABLE consultation_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '会话ID',
    session_id VARCHAR(64) NOT NULL UNIQUE COMMENT '会话唯一标识',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    agent_type ENUM('health_advisor', 'medication_assistant', 'records_manager', 'summary_generator') NOT NULL COMMENT '智能体类型',
    title VARCHAR(200) COMMENT '会话标题',
    status ENUM('active', 'completed', 'archived') DEFAULT 'active' COMMENT '会话状态',
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
    end_time TIMESTAMP NULL COMMENT '结束时间',
    total_messages INT DEFAULT 0 COMMENT '消息总数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id),
    INDEX idx_agent_type (agent_type),
    INDEX idx_status (status),
    INDEX idx_start_time (start_time),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='咨询会话表';

-- 咨询消息表
CREATE TABLE consultation_messages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '消息ID',
    session_id VARCHAR(64) NOT NULL COMMENT '会话ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    message_id VARCHAR(64) NOT NULL UNIQUE COMMENT '消息唯一标识',
    role ENUM('user', 'assistant', 'system') NOT NULL COMMENT '角色',
    content LONGTEXT NOT NULL COMMENT '消息内容',
    content_type ENUM('text', 'image', 'file', 'structured') DEFAULT 'text' COMMENT '内容类型',
    metadata JSON COMMENT '元数据',
    attachments JSON COMMENT '附件信息',
    tokens_used INT COMMENT '使用的token数',
    response_time_ms INT COMMENT '响应时间(毫秒)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id),
    INDEX idx_message_id (message_id),
    INDEX idx_role (role),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (session_id) REFERENCES consultation_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='咨询消息表';

-- =====================================================
-- 6. 就诊摘要相关表
-- =====================================================

-- 就诊摘要表
CREATE TABLE visit_summaries (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '摘要ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    summary_id VARCHAR(64) NOT NULL UNIQUE COMMENT '摘要唯一标识',
    visit_date DATE NOT NULL COMMENT '就诊日期',
    hospital_name VARCHAR(100) COMMENT '医院名称',
    department VARCHAR(50) COMMENT '科室',
    doctor_name VARCHAR(50) COMMENT '医生姓名',
    chief_complaint TEXT COMMENT '主诉',
    symptoms TEXT COMMENT '症状描述',
    diagnosis TEXT COMMENT '诊断结果',
    treatment_plan TEXT COMMENT '治疗方案',
    prescribed_medications JSON COMMENT '开具药物',
    follow_up_instructions TEXT COMMENT '随访指导',
    next_appointment_date DATE COMMENT '下次预约日期',
    summary_content LONGTEXT COMMENT '完整摘要内容',
    generated_by ENUM('manual', 'ai_assistant', 'ocr_extraction') DEFAULT 'manual' COMMENT '生成方式',
    confidence_score DECIMAL(3,2) COMMENT '置信度分数',
    is_verified TINYINT DEFAULT 0 COMMENT '是否已验证：0-否，1-是',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_id (user_id),
    INDEX idx_summary_id (summary_id),
    INDEX idx_visit_date (visit_date),
    INDEX idx_hospital (hospital_name),
    INDEX idx_doctor (doctor_name),
    INDEX idx_generated_by (generated_by),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='就诊摘要表';

-- =====================================================
-- 7. 系统管理相关表
-- =====================================================

-- 智能体配置表
CREATE TABLE agent_configs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '配置ID',
    agent_type VARCHAR(50) NOT NULL COMMENT '智能体类型',
    agent_name VARCHAR(100) NOT NULL COMMENT '智能体名称',
    agent_url VARCHAR(255) NOT NULL COMMENT '智能体URL',
    port INT NOT NULL COMMENT '端口号',
    status ENUM('active', 'inactive', 'maintenance') DEFAULT 'active' COMMENT '状态',
    config_data JSON COMMENT '配置数据',
    version VARCHAR(20) COMMENT '版本号',
    description TEXT COMMENT '描述',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_agent_type (agent_type),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能体配置表';

-- 系统日志表
CREATE TABLE system_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '日志ID',
    user_id VARCHAR(64) COMMENT '用户ID',
    action VARCHAR(100) NOT NULL COMMENT '操作',
    module VARCHAR(50) NOT NULL COMMENT '模块',
    level ENUM('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL') DEFAULT 'INFO' COMMENT '日志级别',
    message TEXT NOT NULL COMMENT '日志消息',
    details JSON COMMENT '详细信息',
    ip_address VARCHAR(45) COMMENT 'IP地址',
    user_agent TEXT COMMENT '用户代理',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_user_id (user_id),
    INDEX idx_action (action),
    INDEX idx_module (module),
    INDEX idx_level (level),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统日志表';

-- =====================================================
-- 8. 数据初始化
-- =====================================================

-- 插入智能体配置数据
INSERT INTO agent_configs (agent_type, agent_name, agent_url, port, description) VALUES
('health_records_manager', '健康档案管理员', 'http://127.0.0.1:10010', 10010, '负责健康档案的录入、解析和安全存储'),
('health_advisor', '健康顾问', 'http://127.0.0.1:10011', 10011, '提供健康咨询和建议服务'),
('medication_reminder', '用药提醒助手', 'http://127.0.0.1:10012', 10012, '管理用药计划和提醒服务'),
('visit_summary_generator', '就诊摘要生成', 'http://127.0.0.1:10013', 10013, '生成就诊摘要和医患沟通辅助');

-- 插入常用药物基础信息
INSERT INTO medications_base (drug_name, generic_name, drug_type, dosage_form, specifications) VALUES
('阿莫西林胶囊', '阿莫西林', 'prescription', 'capsule', '0.25g'),
('布洛芬缓释胶囊', '布洛芬', 'otc', 'capsule', '0.3g'),
('复方甘草片', '复方甘草', 'otc', 'tablet', '每片含甘草流浸膏112.5mg'),
('维生素C片', '维生素C', 'supplement', 'tablet', '100mg'),
('钙片', '碳酸钙', 'supplement', 'tablet', '600mg');

-- =====================================================
-- 9. 创建视图
-- =====================================================

-- 用户健康概览视图
CREATE VIEW user_health_overview AS
SELECT 
    u.user_id,
    u.username,
    up.real_name,
    up.gender,
    up.birth_date,
    TIMESTAMPDIFF(YEAR, up.birth_date, CURDATE()) AS age,
    up.height,
    up.weight,
    up.blood_type,
    COUNT(DISTINCT hr.id) AS total_records,
    COUNT(DISTINCT um.id) AS active_medications,
    COUNT(DISTINCT r.id) AS active_reminders
FROM users u
LEFT JOIN user_profiles up ON u.user_id = up.user_id
LEFT JOIN health_records hr ON u.user_id = hr.user_id AND hr.is_deleted = 0
LEFT JOIN user_medications um ON u.user_id = um.user_id AND um.is_active = 1 AND um.is_deleted = 0
LEFT JOIN reminders r ON u.user_id = r.user_id AND r.is_active = 1 AND r.is_deleted = 0
GROUP BY u.user_id;

-- 用药提醒概览视图
CREATE VIEW medication_reminder_overview AS
SELECT 
    mr.user_id,
    mr.medication_name,
    mr.dosage,
    mr.frequency,
    mr.start_date,
    mr.end_date,
    mr.reminder_times,
    r.title AS reminder_title,
    r.is_active,
    COUNT(rl.id) AS total_logs,
    SUM(CASE WHEN rl.status = 'completed' THEN 1 ELSE 0 END) AS completed_count
FROM medication_reminders mr
JOIN reminders r ON mr.reminder_id = r.id
LEFT JOIN reminder_logs rl ON r.id = rl.reminder_id
GROUP BY mr.id;

-- =====================================================
-- 10. 创建存储过程
-- =====================================================

DELIMITER //

-- 创建用户完整档案的存储过程
CREATE PROCEDURE CreateUserProfile(
    IN p_user_id VARCHAR(64),
    IN p_username VARCHAR(50),
    IN p_email VARCHAR(100),
    IN p_real_name VARCHAR(50),
    IN p_gender ENUM('male', 'female', 'other'),
    IN p_birth_date DATE
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    
    START TRANSACTION;
    
    -- 插入用户基本信息
    INSERT INTO users (user_id, username, email) 
    VALUES (p_user_id, p_username, p_email);
    
    -- 插入用户档案信息
    INSERT INTO user_profiles (user_id, real_name, gender, birth_date)
    VALUES (p_user_id, p_real_name, p_gender, p_birth_date);
    
    COMMIT;
END //

-- 获取用户活跃用药的存储过程
CREATE PROCEDURE GetActiveMedications(
    IN p_user_id VARCHAR(64)
)
BEGIN
    SELECT 
        um.id,
        um.drug_name,
        um.dosage,
        um.frequency,
        um.start_date,
        um.end_date,
        um.remaining_quantity,
        um.unit,
        mb.indications,
        mb.side_effects
    FROM user_medications um
    LEFT JOIN medications_base mb ON um.medication_id = mb.id
    WHERE um.user_id = p_user_id 
        AND um.is_active = 1 
        AND um.is_deleted = 0
        AND (um.end_date IS NULL OR um.end_date >= CURDATE())
    ORDER BY um.start_date DESC;
END //

DELIMITER ;

-- =====================================================
-- 11. 创建触发器
-- =====================================================

DELIMITER //

-- 健康档案更新时间触发器
CREATE TRIGGER tr_health_records_update
    BEFORE UPDATE ON health_records
    FOR EACH ROW
BEGIN
    SET NEW.updated_at = CURRENT_TIMESTAMP;
END //

-- 用药记录状态变更触发器
CREATE TRIGGER tr_user_medications_status
    BEFORE UPDATE ON user_medications
    FOR EACH ROW
BEGIN
    -- 如果结束日期已过，自动设置为非活跃状态
    IF NEW.end_date IS NOT NULL AND NEW.end_date < CURDATE() THEN
        SET NEW.is_active = 0;
    END IF;
    
    SET NEW.updated_at = CURRENT_TIMESTAMP;
END //

DELIMITER ;

-- =====================================================
-- 12. 创建索引优化
-- =====================================================

-- 复合索引优化查询性能
CREATE INDEX idx_health_records_user_type_date ON health_records(user_id, record_type, visit_date);
CREATE INDEX idx_user_medications_user_active ON user_medications(user_id, is_active, is_deleted);
CREATE INDEX idx_reminders_user_type_time ON reminders(user_id, reminder_type, reminder_time);
CREATE INDEX idx_consultation_messages_session_time ON consultation_messages(session_id, created_at);

-- =====================================================
-- 数据库设计完成
-- 说明：
-- 1. 支持完整的个人健康助手功能
-- 2. 包含用户管理、健康档案、用药管理、提醒系统等核心模块
-- 3. 采用MySQL 8.0+特性，支持JSON字段和现代SQL功能
-- 4. 包含必要的索引、视图、存储过程和触发器
-- 5. 支持数据加密存储和安全管理
-- 6. 预留扩展接口，便于后续功能增强
-- =====================================================