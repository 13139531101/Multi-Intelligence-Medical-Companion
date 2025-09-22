# Navicat 数据库导入指南

## 快速开始

### 第一步：准备工作

1. 确保已安装 **Navicat for MySQL** 或 **Navicat Premium**
2. 确保 MySQL 服务器正在运行（推荐 MySQL 8.0+）
3. 准备好数据库连接信息（主机、端口、用户名、密码）

### 第二步：创建数据库连接

1. 打开 Navicat
2. 点击 **"连接"** → **"MySQL"**
3. 填写连接信息：
   - **连接名**: `个人健康助手`
   - **主机**: `localhost` (或你的 MySQL 服务器地址)
   - **端口**: `3306` (默认端口)
   - **用户名**: `root` (或你的 MySQL 用户名)
   - **密码**: (你的 MySQL 密码)
4. 点击 **"测试连接"** 确保连接成功
5. 点击 **"确定"** 保存连接

### 第三步：创建数据库

1. 双击刚创建的连接，打开数据库服务器
2. 右键点击连接名，选择 **"新建数据库"**
3. 填写数据库信息：
   - **数据库名**: `personal_health_assistant`
   - **字符集**: `utf8mb4`
   - **排序规则**: `utf8mb4_unicode_ci`
4. 点击 **"确定"** 创建数据库

### 第四步：导入 SQL 脚本

#### 方法一：直接执行 SQL 文件

1. 右键点击 `personal_health_assistant` 数据库
2. 选择 **"运行 SQL 文件"**
3. 浏览并选择 `personal_health_assistant.sql` 文件
4. 确保 **"目标数据库"** 选择为 `personal_health_assistant`
5. 点击 **"开始"** 执行脚本
6. 等待执行完成，查看执行结果

#### 方法二：查询窗口执行

1. 双击 `personal_health_assistant` 数据库打开
2. 点击工具栏的 **"查询"** 按钮（或按 Ctrl+Q）
3. 打开 `personal_health_assistant.sql` 文件
4. 复制所有内容到查询窗口
5. 点击 **"运行"** 按钮（或按 F5）
6. 查看执行结果，确保无错误

### 第五步：验证数据库结构

1. 刷新数据库（F5 或右键刷新）
2. 展开 `personal_health_assistant` 数据库
3. 检查是否包含以下表：
   - **用户管理**: `users`, `user_profiles`
   - **健康档案**: `health_records`, `health_record_attachments`
   - **用药管理**: `medications_base`, `user_medications`
   - **提醒系统**: `reminders`, `medication_reminders`, `reminder_logs`
   - **咨询系统**: `consultation_sessions`, `consultation_messages`
   - **就诊摘要**: `visit_summaries`
   - **系统管理**: `agent_configs`, `system_logs`

### 第六步：查看预置数据

1. 双击打开 `agent_configs` 表
2. 查看是否包含 4 个智能体配置：
   - 健康档案管理员 (端口 10010)
   - 健康顾问 (端口 10011)
   - 用药提醒助手 (端口 10012)
   - 就诊摘要生成 (端口 10013)
3. 双击打开 `medications_base` 表
4. 查看是否包含常用药物信息

## 高级功能验证

### 查看视图

1. 在数据库中找到 **"视图"** 节点
2. 展开查看是否包含：
   - `user_health_overview`
   - `medication_reminder_overview`
3. 双击视图可以查看视图结构和数据

### 查看存储过程

1. 在数据库中找到 **"函数"** 或 **"存储过程"** 节点
2. 展开查看是否包含：
   - `CreateUserProfile`
   - `GetActiveMedications`

### 查看触发器

1. 展开相关表（如 `health_records`）
2. 查看 **"触发器"** 节点
3. 确认触发器已正确创建

## 常见问题解决

### 问题 1：字符集错误

**现象**: 中文显示乱码
**解决**:

1. 确保数据库字符集为 `utf8mb4`
2. 检查 Navicat 连接的字符集设置
3. 重新创建数据库时指定正确字符集

### 问题 2：权限不足

**现象**: 无法创建数据库或表
**解决**:

1. 确保 MySQL 用户有足够权限
2. 使用 root 用户或具有 CREATE 权限的用户
3. 检查 MySQL 服务器配置

### 问题 3：外键约束错误

**现象**: 表创建失败，提示外键错误
**解决**:

1. 确保按顺序执行 SQL 脚本
2. 检查 MySQL 版本是否支持外键
3. 确保 InnoDB 存储引擎已启用

### 问题 4：JSON 字段不支持

**现象**: JSON 字段创建失败
**解决**:

1. 确保 MySQL 版本为 5.7+（推荐 8.0+）
2. 如果版本较低，可以将 JSON 字段改为 TEXT 类型

## 数据库管理建议

### 日常维护

1. **定期备份**:

   - 右键数据库 → "转储 SQL 文件" → "结构和数据"
   - 建议每日自动备份

2. **性能监控**:

   - 使用 Navicat 的"服务器监控"功能
   - 定期检查慢查询日志

3. **数据清理**:
   - 定期清理 `system_logs` 表的历史数据
   - 清理已删除的记录（is_deleted=1）

### 安全设置

1. **用户权限**:

   - 为应用程序创建专用数据库用户
   - 只授予必要的权限（SELECT, INSERT, UPDATE, DELETE）
   - 避免使用 root 用户连接应用程序

2. **连接安全**:
   - 启用 SSL 连接（生产环境）
   - 限制连接 IP 地址
   - 使用强密码

### 性能优化

1. **索引管理**:

   - 定期分析表使用情况
   - 根据查询模式调整索引
   - 删除不必要的索引

2. **表维护**:
   - 定期执行 `OPTIMIZE TABLE`
   - 分析表统计信息
   - 监控表大小增长

## 测试数据插入

### 创建测试用户

```sql
-- 插入测试用户
CALL CreateUserProfile(
    'test_user_001',
    'testuser',
    'test@example.com',
    '张三',
    'male',
    '1990-01-01'
);
```

### 插入测试健康档案

```sql
-- 插入测试健康档案
INSERT INTO health_records (
    user_id, record_type, title, hospital_name,
    department, doctor_name, visit_date
) VALUES (
    'test_user_001', 'medical_record', '体检报告',
    '市人民医院', '内科', '李医生', '2024-01-15'
);
```

### 插入测试用药记录

```sql
-- 插入测试用药记录
INSERT INTO user_medications (
    user_id, drug_name, dosage, frequency,
    start_date, duration_days
) VALUES (
    'test_user_001', '阿莫西林胶囊', '0.25g',
    '每日3次，饭后服用', '2024-01-15', 7
);
```

## 联系支持

如果在导入过程中遇到问题，请：

1. 检查 MySQL 和 Navicat 版本兼容性
2. 查看错误日志获取详细信息
3. 参考 `数据库设计说明.md` 获取更多技术细节
4. 联系技术支持团队

---

**最后更新**: 2024 年
**适用版本**: Navicat 15+, MySQL 8.0+
