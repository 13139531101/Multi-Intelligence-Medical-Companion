-- 阶段48-fix: 删除 rag_chunks 上遗留的跨租户唯一约束
--
-- 现象
-- ----
-- 用户 B 索引一个 source_id 已被用户 A 用过的文档时, /v2/rag/index 直接 500:
--   duplicate key value violates unique constraint
--   "rag_chunks_source_type_source_id_chunk_index_embedding_mode_key"
--   DETAIL: Key (source_type, source_id, chunk_index, embedding_model)=(...) already exists.
--
-- 根因
-- ----
-- 线上库上同时存在**两个**唯一约束:
--   1. rag_chunks_source_type_source_id_chunk_index_embedding_model_key
--      → (source_type, source_id, chunk_index, embedding_model)   ← 不含 user_id
--   2. rag_chunks_user_source_chunk_model_key
--      → (user_id, source_type, source_id, chunk_index, embedding_model)
--
-- 约束 1 是旧版 schema 的遗留物（现行 DDL database/postgres/init/02_reminders_and_records.sql:156
-- 只有约束 2）。它把 source_id 当成全局唯一, 于是**跨用户互相踩踏** —— 而 rag.py
-- 的 index_document 又是 `DELETE ... WHERE user_id=%s AND source_type=%s AND source_id=%s`
-- 按用户删、再插, 删的粒度和约束的粒度不一致, 结果就是"删不掉别人的行, 又插不进自己的行"。
--
-- 修法
-- ----
-- 约束 2 是约束 1 的严格超集（多了 user_id 维度）: 任何能满足约束 2 的行集合都更宽松,
-- 所以删掉约束 1 不会放进任何"按租户语义本不该存在"的重复行, 只是恢复了多租户隔离。
-- 用 IF EXISTS 保证幂等, 在已经干净的环境上执行是空操作。

-- 顺序要紧: 先删约束（约束会自动带走它背后的索引）。
-- 反过来先 DROP INDEX 会报 "cannot drop index ... because constraint ... requires it"。
ALTER TABLE rag_chunks
    DROP CONSTRAINT IF EXISTS rag_chunks_source_type_source_id_chunk_index_embedding_mode_key;

-- 兜底: 万一遗留的是裸索引而不是约束
DROP INDEX IF EXISTS rag_chunks_source_type_source_id_chunk_index_embedding_mode_key;

-- 兜底: 确保正确的那条约束一定存在（老环境可能只有遗留约束）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'rag_chunks_user_source_chunk_model_key'
          AND conrelid = 'rag_chunks'::regclass
    ) THEN
        ALTER TABLE rag_chunks
            ADD CONSTRAINT rag_chunks_user_source_chunk_model_key
            UNIQUE (user_id, source_type, source_id, chunk_index, embedding_model);
    END IF;
END $$;
