# 智能路由API使用说明

## 概述

智能路由API是一个统一的接口，允许用户通过一句话调用不同的健康助手智能体。系统会根据用户输入的内容自动选择最合适的智能体来处理请求。

## API地址

```
POST http://localhost:13001/smart_chat
```

## 请求格式

```json
{
  "message": "用户的自然语言请求"
}
```

## 响应格式

### 成功响应
```json
{
  "success": true,
  "message": "已将您的请求转发给健康档案管理员",
  "conversation_id": "890e8c27-7487-4487-9da4-1f3276844066",
  "message_id": "cd7292f6-e7ed-4dab-ad67-b3424346e592",
  "selected_agent": "健康档案管理员"
}
```

### 错误响应
```json
{
  "error": "错误信息"
}
```

## 智能体路由规则

系统根据用户输入中的关键词自动选择合适的智能体：

### 1. 健康档案管理员
**关键词**: 档案、病史、记录、健康记录、医疗记录、病历
**功能**: 管理个人健康档案和病史记录
**示例**: 
- "我想查看我的健康档案"
- "帮我更新病史记录"
- "查看我的医疗记录"

### 2. 健康顾问
**关键词**: 建议、咨询、症状、诊断、治疗、健康问题、医疗建议
**功能**: 提供个性化健康建议和医疗咨询
**示例**: 
- "我最近有头痛症状，需要一些建议"
- "关于高血压的治疗建议"
- "我有健康问题需要咨询"

### 3. 用药提醒助手
**关键词**: 用药、药物、提醒、服药、药品、medication
**功能**: 管理用药计划和智能提醒
**示例**: 
- "帮我设置用药提醒"
- "管理我的药物清单"
- "设置服药时间"

### 4. 就诊摘要生成器
**关键词**: 摘要、总结、就诊、报告、文档、解析
**功能**: 生成就诊记录摘要和医疗文档解析
**示例**: 
- "生成我上次就诊的摘要"
- "解析这份医疗报告"
- "总结我的检查结果"

### 默认路由
如果用户输入没有明确匹配任何关键词，系统会默认使用**健康顾问**来处理请求。

## 使用示例

### Python示例
```python
import requests
import json

def call_smart_chat(message):
    url = "http://localhost:13001/smart_chat"
    payload = {"message": message}
    
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": f"请求失败: {response.status_code}"}

# 使用示例
result = call_smart_chat("我想查看我的健康档案")
print(json.dumps(result, ensure_ascii=False, indent=2))
```

### JavaScript示例
```javascript
async function callSmartChat(message) {
    try {
        const response = await fetch('http://localhost:13001/smart_chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message })
        });
        
        const result = await response.json();
        return result;
    } catch (error) {
        return { error: `请求失败: ${error.message}` };
    }
}

// 使用示例
callSmartChat("帮我设置用药提醒").then(result => {
    console.log(result);
});
```

### curl示例
```bash
curl -X POST http://localhost:13001/smart_chat \
  -H "Content-Type: application/json" \
  -d '{"message": "我最近有头痛症状，需要一些建议"}'
```

## 注意事项

1. **服务器启动**: 确保API服务器正在运行 (`python api.py`)
2. **端口配置**: 默认端口为13001，如需修改请更新api.py中的配置
3. **智能体服务**: 确保相关的智能体服务正在运行（端口10010-10013）
4. **错误处理**: 请妥善处理API返回的错误信息
5. **会话管理**: 每次请求都会创建新的会话，如需持续对话请使用返回的conversation_id

## 测试

运行测试脚本验证API功能：
```bash
python test_smart_chat.py
```

## 技术架构

- **框架**: FastAPI
- **路由算法**: 基于关键词匹配的智能路由
- **消息格式**: 符合A2A协议的Message格式
- **智能体通信**: 通过ADKHostManager管理多智能体协调

## 扩展功能

未来可以考虑的扩展：
- 基于机器学习的智能路由
- 多智能体协作处理复杂请求
- 用户偏好学习和个性化路由
- 会话上下文理解和连续对话