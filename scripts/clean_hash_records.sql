-- 阶段47: 清理 test 脏数据 (删 hash-named records)
-- testuser 的 user_id (登录后真实账号) 不一定与历史脏数据 user_id 匹配
-- 所以这里清掉所有 hash-named 测试记录

DELETE FROM health_records
WHERE title ~ 'medical_record - [A-Za-z0-9]{20,}\.(png|jpg|jpeg|pdf)'
   OR title LIKE '%[A-Za-z0-9]{20,}.[a-z]';

-- 清空 title 为空的记录
DELETE FROM health_records WHERE title IS NULL OR TRIM(title) = '';

-- 统计
SELECT COUNT(*) AS remaining FROM health_records;