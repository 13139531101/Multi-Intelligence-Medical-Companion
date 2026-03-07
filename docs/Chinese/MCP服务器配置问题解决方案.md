# MCP 服务器配置问题解决方案

## 问题背景

在个人智能健康助手项目中，使用了 Model Context Protocol (MCP) 架构来实现多个功能模块的服务器端工具。项目包含以下几个主要模块：

- **HealthRecordsManager**: 健康记录管理模块
- **HealthAdvisor**: 健康建议模块  
- **MedicationReminder**: 用药提醒模块
- **VisitSummaryGenerator**: 就诊总结生成模块
- **AgentRAG**: 智能检索增强生成模块
- **DeepSearch**: 深度搜索模块

## 遇到的问题

### 1. FastMCP 导入路径问题

**问题描述**: 所有 MCP 服务器文件中使用了过时的 `from fastmcp import FastMCP` 导入语句，导致模块无法正常加载。

**错误信息**: `ModuleNotFoundError: No module named 'fastmcp'`

**影响范围**: 所有 MCP 服务器工具文件

### 2. MCP CLI 依赖缺失问题

**问题描述**: 配置文件中使用了 `fastmcp` 命令，但实际应该使用标准的 `mcp` 命令，且缺少 `mcp[cli]` 依赖包。

**错误信息**: `ModuleNotFoundError: No module named 'typer'`

### 3. 数据库连接依赖问题

**问题描述**: `StorageTool` 和 `ReminderTool` 启动失败，出现 "Connection closed" 错误。

**根本原因**: 这两个工具依赖 `database_config.py` 模块，该模块使用 `mysql.connector` 库，但配置中缺少 `mysql-connector-python` 依赖。

## 解决方案

### 1. 修复 FastMCP 导入路径

**解决方法**: 将所有 MCP 服务器文件中的导入语句从：
```python
from fastmcp import FastMCP
```
更新为：
```python
from mcp.server.fastmcp import FastMCP
```

**修改的文件**:
- `HealthRecordsManager/mcpserver/ocr_tool.py`
- `HealthRecordsManager/mcpserver/data_extraction_tool.py`
- `HealthRecordsManager/mcpserver/storage_tool.py`
- `HealthRecordsManager/mcpserver/reminder_tool.py`
- `HealthAdvisor/mcpserver/knowledge_tool.py`
- `HealthAdvisor/mcpserver/diagnosis_tool.py`
- `MedicationReminder/mcpserver/reminder_tool.py`
- `MedicationReminder/mcpserver/notification_tool.py`
- `VisitSummaryGenerator/mcpserver/document_tool.py`
- `VisitSummaryGenerator/mcpserver/ai_analysis_tool.py`
- `AgentRAG/mcpserver/rag_tool.py`
- `DeepSearch/mcpserver/search_tool.py`

### 2. 更新 MCP 配置文件

**解决方法**: 将所有 `mcp_config.json` 文件中的启动命令从 `fastmcp` 更新为标准的 `mcp` 命令，并添加必要的依赖包。

**配置更新示例**:
```json
// 修改前
{
  "command": "fastmcp",
  "args": ["run", "mcpserver/tool.py"]
}

// 修改后
{
  "command": "uv",
  "args": [
    "run",
    "--with",
    "mcp[cli]",
    "mcp",
    "run",
    "mcpserver/tool.py"
  ]
}
```

### 3. 添加特定依赖包

**针对不同工具添加相应依赖**:

- **OCRTool**: 添加 `requests` 和 `python-dotenv` 依赖
- **DiagnosisTool**: 添加 `requests` 和 `python-dotenv` 依赖
- **StorageTool**: 添加 `mysql-connector-python` 和 `cryptography` 依赖
- **ReminderTool**: 添加 `mysql-connector-python` 依赖
- **所有工具**: 统一添加 `mcp[cli]` 依赖

## 技术细节

### 依赖管理策略

使用 `uv` 包管理器的 `--with` 参数来动态安装依赖，避免在每个模块中创建独立的虚拟环境：

```bash
uv run --with "mcp[cli]" --with mysql-connector-python mcp run mcpserver/tool.py
```

### 数据库连接问题分析

通过代码分析发现，`StorageTool` 和 `ReminderTool` 都导入了 `database_config.py` 模块：

```python
from database_config import get_db_manager
```

该模块使用了 MySQL 连接器：
```python
import mysql.connector
from mysql.connector import Error
```

因此需要在启动命令中添加 `mysql-connector-python` 依赖。

## 验证结果

### 测试方法

1. **单独测试每个工具**:
   ```bash
   uv run --with "mcp[cli]" --with [specific-deps] mcp run mcpserver/tool.py
   ```

2. **检查启动状态**: 观察是否出现 "Connection closed" 错误

3. **验证功能**: 确认 MCP 服务器能够正常接收和处理请求

### 测试结果

- ✅ **OCRTool**: 启动成功，功能正常
- ✅ **DataExtractionTool**: 启动成功，功能正常
- ✅ **StorageTool**: 修复后启动成功，数据库连接正常
- ✅ **ReminderTool**: 修复后启动成功，数据库连接正常
- ✅ **其他所有工具**: 启动成功，功能正常

## 经验总结

### 1. 依赖管理的重要性

在微服务架构中，每个服务的依赖管理至关重要。需要确保：
- 所有必需的依赖包都被正确声明
- 依赖版本兼容性
- 运行时环境的一致性

### 2. 配置文件的维护

配置文件需要与代码实现保持同步：
- 当代码中的依赖发生变化时，配置文件也需要相应更新
- 定期检查配置文件的有效性
- 使用版本控制跟踪配置变更

### 3. 错误诊断方法

- **分层诊断**: 从导入错误开始，逐层排查问题
- **对比分析**: 比较成功和失败的工具，找出差异
- **依赖追踪**: 分析代码中的实际依赖关系

### 4. 测试策略

- **单元测试**: 每个工具独立测试
- **集成测试**: 验证整体系统功能
- **渐进式修复**: 逐个解决问题，避免引入新的错误

## 技术栈说明

- **MCP (Model Context Protocol)**: 用于 AI 模型与外部工具的通信协议
- **FastMCP**: MCP 的 Python 实现框架
- **uv**: 现代 Python 包管理器
- **MySQL**: 关系型数据库
- **Python**: 主要编程语言

## 后续优化建议

1. **自动化测试**: 建立 CI/CD 流水线，自动测试所有 MCP 工具的启动状态
2. **依赖锁定**: 使用 `requirements.txt` 或 `pyproject.toml` 锁定依赖版本
3. **监控告警**: 实现服务健康检查和异常告警机制
4. **文档完善**: 为每个工具编写详细的部署和使用文档

---

*本文档记录了个人智能健康助手项目中 MCP 服务器配置问题的完整解决过程，可作为类似问题的参考方案。*