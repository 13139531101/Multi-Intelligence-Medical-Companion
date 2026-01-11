# 智能体长期记忆系统 (Agent Memory System)

## 概述

智能体长期记忆系统是一个为多智能体系统设计的统一记忆管理解决方案。它提供了记忆的存储、检索、管理和优化功能，支持语义搜索、重要性评估、记忆压缩和自动清理等高级特性。

## 核心特性

### 🧠 记忆类型支持

- **短期记忆 (Short-term)**: 临时信息，24 小时后自动过期
- **工作记忆 (Working)**: 当前任务相关信息，7 天后过期
- **长期记忆 (Long-term)**: 重要信息，永久保存
- **元记忆 (Meta)**: 关于记忆本身的信息

### 🔍 智能检索

- **语义搜索**: 基于向量嵌入的语义相似度搜索
- **时间范围搜索**: 按时间段检索记忆
- **标签搜索**: 基于标签的精确匹配
- **重要性过滤**: 按重要性评分筛选
- **关联记忆**: 查找相关联的记忆

### 📊 记忆管理

- **重要性评估**: 基于多因子的智能重要性评分
- **记忆压缩**: 自动合并相似记忆
- **过期清理**: 自动清理过期和低价值记忆
- **关联构建**: 自动建立记忆间的关联关系

### 🔒 安全特性

- **数据加密**: 敏感信息加密存储
- **访问控制**: 基于智能体和用户的权限控制
- **审计日志**: 完整的操作记录

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    智能体记忆系统                              │
├─────────────────────────────────────────────────────────────┤
│  记忆接口层 (Memory Interface Layer)                         │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ │
│  │   存储接口      │ │   检索接口      │ │   管理接口      │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  记忆处理层 (Memory Processing Layer)                        │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ │
│  │   嵌入服务      │ │   重要性评估    │ │   关联分析      │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  记忆存储层 (Memory Storage Layer)                           │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ │
│  │   记忆主表      │ │   向量索引      │ │   关联关系      │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 安装和配置

### 1. 环境要求

- Python 3.8+
- 至少 4GB RAM
- 支持向量计算的 CPU 或 GPU

### 2. 安装依赖

```bash
cd backend/AgentMemorySystem
pip install -r requirements.txt
```

### 3. 数据库配置

创建 MySQL 数据库：

```sql
CREATE DATABASE agent_memory CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'memory_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON agent_memory.* TO 'memory_user'@'localhost';
FLUSH PRIVILEGES;
```

### 4. 环境变量配置

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入实际配置：

```env
# 数据库配置
MEMORY_DB_HOST=localhost
MEMORY_DB_PORT=3306
MEMORY_DB_USER=memory_user
MEMORY_DB_PASSWORD=your_password
MEMORY_DB_NAME=agent_memory

# 嵌入模型配置
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu

# 安全配置
MEMORY_ENCRYPTION_KEY=your_32_character_encryption_key

# 运行时开关（与 Agent 集成）
# 将在运行 Agent 时读取这些变量
# 设置为 false 或 1 来关闭记忆初始化：
# - ENABLE_AGENT_MEMORY=false  或  SKIP_MEMORY_INIT=1
ENABLE_AGENT_MEMORY=true
# 跳过初始化以加速调试（优先级高于 ENABLE_AGENT_MEMORY）
SKIP_MEMORY_INIT=0

# 标识信息（写入/检索记忆时使用）
AGENT_ID=A2AAgent
# 建议为后端或会话进程设置 USER_ID；若未设置，系统将使用 sessionId 作为回退
USER_ID=
```

### 5. 初始化数据库

```python
from memory_system import AgentMemorySystem

# 创建记忆系统实例（会自动初始化数据库表）
memory_system = AgentMemorySystem()
```

## 使用指南

### 基本使用

```python
from memory_system import AgentMemorySystem

# 初始化记忆系统
memory_system = AgentMemorySystem()

# 存储记忆
memory_id = memory_system.store_memory(
    agent_id="health_advisor_001",
    user_id="user_123",
    content={
        'text': '用户询问了关于高血压的问题',
        'structured_data': {
            'question_type': 'health_inquiry',
            'topic': 'hypertension',
            'user_concern': 'prevention'
        },
        'metadata': {
            'session_id': 'session_456',
            'timestamp': '2024-01-15T10:30:00Z'
        }
    },
    memory_type='working',
    importance=0.7,
    tags=['健康咨询', '高血压', '预防']
)

# 搜索记忆
results = memory_system.search_memories(
    query="高血压预防方法",
    agent_id="health_advisor_001",
    user_id="user_123",
    limit=10
)

# 获取最近记忆
recent_memories = memory_system.get_recent_memories(
    agent_id="health_advisor_001",
    user_id="user_123",
    hours=24
)
```

### 智能体特化接口

#### 健康档案智能体

```python
# 存储健康档案记忆
memory_id = memory_system.store_health_record_memory(
    agent_id="health_records_001",
    user_id="user_123",
    record_type="体检报告",
    record_data={
        'summary': '年度体检结果正常',
        'blood_pressure': '120/80',
        'cholesterol': '180mg/dL',
        'blood_sugar': '95mg/dL',
        'date': '2024-01-15',
        'doctor': 'Dr. Smith'
    },
    importance=0.9
)
```

#### 用药提醒智能体

```python
# 存储用药记忆
memory_id = memory_system.store_medication_memory(
    agent_id="medication_001",
    user_id="user_123",
    medication_info={
        'medication_name': '阿司匹林',
        'dosage': '100mg',
        'frequency': '每日一次',
        'time': '08:00',
        'duration': '长期',
        'purpose': '心血管保护'
    }
)
```

#### 对话记忆

```python
# 存储对话记忆
memory_id = memory_system.store_conversation_memory(
    agent_id="health_advisor_001",
    user_id="user_123",
    user_message="我最近血压有点高，应该注意什么？",
    agent_response="建议您注意低盐饮食，适量运动，定期监测血压...",
    context={
        'session_id': 'session_789',
        'conversation_turn': 3
    }
)
```

### 记忆管理

```python
# 评估记忆重要性
importance = memory_system.evaluate_memory_importance(memory_id)

# 压缩相似记忆
compressed_count = memory_system.compress_memories(
    agent_id="health_advisor_001",
    user_id="user_123"
)

# 清理过期记忆
expired_count = memory_system.cleanup_expired_memories()

# 执行系统维护
maintenance_result = memory_system.perform_maintenance(
    agent_id="health_advisor_001",
    user_id="user_123"
)
```

### 系统监控

```python
# 获取系统状态
status = memory_system.get_system_status()
print(f"数据库连接: {status['database_connected']}")
print(f"记忆总数: {status['table_statistics']['memories']}")

# 分析记忆模式
patterns = memory_system.analyze_memory_patterns(
    agent_id="health_advisor_001",
    user_id="user_123",
    days=30
)
```

## 配置说明

### 记忆类型配置

```python
from config import MemorySystemConfig

# 获取记忆类型配置
long_term_config = MemorySystemConfig.get_memory_type_config('long_term')
print(f"长期记忆过期时间: {long_term_config['default_expires_hours']}")
print(f"最大重要性: {long_term_config['max_importance']}")
```

### 智能体配置

```python
# 获取智能体特定配置
health_config = MemorySystemConfig.get_agent_config('health_records')
print(f"默认重要性: {health_config['default_importance']}")
print(f"记忆类型: {health_config['memory_type']}")
print(f"必需标签: {health_config['required_tags']}")
```

## 性能优化

### 1. 数据库优化

- 为常用查询字段创建索引
- 定期执行 `ANALYZE TABLE` 更新统计信息
- 配置适当的连接池大小

### 2. 嵌入模型优化

- 使用 GPU 加速（如果可用）
- 调整批处理大小
- 考虑使用更小的模型以提高速度

### 3. 缓存策略

- 启用记忆缓存
- 配置适当的缓存 TTL
- 使用 Redis 作为分布式缓存

## 测试

运行单元测试：

```bash
python test_memory_system.py
```

运行特定测试：

```bash
python -m unittest test_memory_system.TestMemorySystem.test_store_memory
```

## 故障排除

### 常见问题

1. **数据库连接失败**

   - 检查数据库服务是否运行
   - 验证连接参数
   - 确认用户权限

2. **嵌入模型加载失败**

   - 检查网络连接
   - 验证模型名称
   - 确认磁盘空间

3. **内存不足**
   - 减少批处理大小
   - 使用更小的嵌入模型
   - 增加系统内存

### 日志分析

查看系统日志：

```bash
tail -f logs/memory_system.log
```

## API 参考

### 核心接口

#### `store_memory(agent_id, user_id, content, memory_type, importance, tags, expires_hours)`

存储新记忆。

**参数:**

- `agent_id` (str): 智能体 ID
- `user_id` (str): 用户 ID
- `content` (dict): 记忆内容
- `memory_type` (str): 记忆类型
- `importance` (float): 重要性评分 (0.0-1.0)
- `tags` (list): 标签列表
- `expires_hours` (int): 过期时间（小时）

**返回:** 记忆 ID (str)

#### `search_memories(query, agent_id, user_id, memory_types, limit, min_similarity)`

语义搜索记忆。

**参数:**

- `query` (str): 查询文本
- `agent_id` (str): 智能体 ID
- `user_id` (str): 用户 ID
- `memory_types` (list): 记忆类型过滤
- `limit` (int): 结果数量限制
- `min_similarity` (float): 最小相似度阈值

**返回:** 记忆列表 (list)

更多 API 详情请参考源代码文档。

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 许可证

本项目采用 MIT 许可证。详情请参考 LICENSE 文件。

## 联系方式

如有问题或建议，请通过以下方式联系：

- 邮箱: 2925042883@qq.com

---

**注意**: 本系统处理敏感的健康数据，请确保遵循相关的数据保护法规和最佳实践。
