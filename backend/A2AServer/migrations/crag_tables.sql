-- PHA v2 CRAG Tables Migration
-- 阶段48-CRAG: Corrective RAG 支持

-- rag_feedback: 持久化用户对 RAG 检索结果的反馈（替代 in-memory dict）
CREATE TABLE IF NOT EXISTS rag_feedback (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    query TEXT NOT NULL,
    score_delta FLOAT NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, chunk_id, query)
);

-- rag_feedback 索引：按 user_id + score 快速查询高反馈 chunks
CREATE INDEX IF NOT EXISTS idx_rag_feedback_user_score
    ON rag_feedback(user_id, score_delta DESC);

-- crag_web_sources: 记录 CRAG 触发 web 搜索的来源（可溯源）
CREATE TABLE IF NOT EXISTS crag_web_sources (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('CORRECT', 'AMBIGUOUS', 'INCORRECT')),
    url TEXT NOT NULL,
    title TEXT,
    snippet TEXT,
    score FLOAT DEFAULT 0.8,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- crag_web_sources 索引：按 user_id + created_at 查询历史搜索来源
CREATE INDEX IF NOT EXISTS idx_crag_web_sources_user_time
    ON crag_web_sources(user_id, created_at DESC);

-- crag_action_log: CRAG 决策日志（可观测性）
CREATE TABLE IF NOT EXISTS crag_action_log (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('CORRECT', 'AMBIGUOUS', 'INCORRECT')),
    rag_score FLOAT DEFAULT 0.0,
    rag_is_relevant BOOLEAN DEFAULT FALSE,
    web_results_count INT DEFAULT 0,
    confidence_level TEXT DEFAULT 'unknown',
    latency_ms INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- crag_action_log 索引
CREATE INDEX IF NOT EXISTS idx_crag_action_log_user_time
    ON crag_action_log(user_id, created_at DESC);

COMMENT ON TABLE rag_feedback IS '用户对 RAG 检索结果的反馈（点赞/点踩），用于调整检索权重';
COMMENT ON TABLE crag_web_sources IS 'CRAG web 搜索的来源记录，用于答案溯源';
COMMENT ON TABLE crag_action_log IS 'CRAG 三分支决策日志，用于可观测性分析';
