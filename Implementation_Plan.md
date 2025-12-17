# A2A Health Assistant 新功能实现方案

本方案旨在实现用户提出的三个核心需求：就诊摘要生成、健康趋势分析、以及健康档案智能体的异步通知机制。

## 1. 就诊摘要 (Visit Summary)

### 1.1 功能描述
用户在就诊后，可上传病历、处方、检查报告等照片。系统通过OCR识别文字，利用大模型（LLM）整理成结构化的就诊摘要，并按次罗列展示。

### 1.2 技术架构
*   **前端 (WeChat Mini Program)**:
    *   新增页面 `pages/visit-summary/index` (列表页) 和 `pages/visit-summary/upload` (上传页)。
    *   使用 `wx.chooseMedia` 选择图片。
    *   调用后端上传接口。
*   **后端 (Python/FastAPI)**:
    *   **OCR服务**: 利用现有的 `HealthRecordsManager/mcpserver/ocr_tool.py` (基于 Tesseract 或云服务)。
    *   **LLM整理**: 使用 `VisitSummaryGenerator` 中的 `AIAnalysisTool` 对OCR结果进行结构化提取（提取诊断、药品、医嘱等）。
    *   **存储**: 存入 `visit_summaries` 表（已存在）或扩展 `health_records` 表。

### 1.3 详细流程
1.  **上传**: 用户上传图片 -> 前端压缩并转 Base64 -> 调用 `POST /api/visit-summary/generate`。
2.  **处理 (后端)**:
    *   调用 `OCRTool` 提取文本。
    *   构建 Prompt: "请根据以下OCR识别的医疗文本，整理为结构化的就诊摘要，包含：就诊时间、医院/科室、诊断结果、处方药品、医嘱。"
    *   调用 LLM 生成 JSON 结构数据。
    *   保存到数据库。
3.  **展示**: 前端调用 `GET /api/visit-summary/list` 获取历史记录并渲染。

---

## 2. 健康趋势 (Health Trends)

### 2.1 功能描述
针对特定特征（如血压、血糖）或症状（如头痛频率），进行长期统计并展示变化趋势，辅助医生诊断。

### 2.2 技术架构
*   **前端**:
    *   新增页面 `pages/health-trends/index`。
    *   引入 `echarts-for-weixin` 组件库进行图表渲染（折线图/柱状图）。
*   **后端**:
    *   利用 `VisitSummaryGenerator/mcpserver/ai_analysis_tool.py` 中的 `analyze_health_trends` 函数。
    *   新增接口 `GET /api/health-trends/analyze`。
    *   支持参数 `feature` (特征名) 和 `period` (时间范围)。

### 2.3 详细流程
1.  **数据源**: 从 `health_records` 和 `visit_summaries` 中提取带有数值或等级的数据。
2.  **分析**:
    *   用户选择/输入关注的特征（如 "白细胞计数" 或 "睡眠质量"）。
    *   后端检索相关记录，提取时间点和对应值。
    *   如果是非数值型描述（如"严重"、"轻微"），LLM可将其映射为数值（1-10）以便绘图。
3.  **可视化**: 前端接收 `(date, value)` 数组，绘制趋势图。

---

## 3. 异步通知机制 (Asynchronous Notification)

### 3.1 功能描述
健康档案智能体在查询或处理耗时任务时（如分析长期的健康趋势、整理大量病历），不再让用户在聊天窗口等待，而是立即返回“正在处理”，处理完成后通过服务通知（订阅消息）触达用户。

### 3.2 技术架构
*   **消息机制**: 微信小程序“订阅消息” (Subscribe Message)。
*   **后端任务队列**:
    *   使用 `asyncio.create_task` (轻量级) 或 `Celery` (生产级) 后台执行任务。
    *   新增 `NotificationTool` 的微信接口适配。

### 3.3 详细流程
1.  **触发**: 用户在对话框发起复杂请求（如“分析我过去一年的健康变化”）。
2.  **立即响应**:
    *   后端 API 立即返回 JSON: `{ "status": "processing", "task_id": "xxx", "message": "正在分析中，结果将通过通知发送给您。" }`
    *   前端识别到 `processing` 状态，弹出 `wx.requestSubscribeMessage` 申请发送通知权限。
3.  **后台处理**:
    *   Agent 在后台执行检索和分析逻辑。
    *   生成结果报告/摘要。
4.  **推送**:
    *   任务完成，调用微信 `POST https://api.weixin.qq.com/cgi-bin/message/subscribe/send`。
    *   通知内容：“您的健康趋势分析已生成，点击查看。”
    *   用户点击通知，跳转到分析结果详情页。

## 4. 开发计划 (ToDo)

1.  **环境检查**: 确认 OCR 工具 (Tesseract) 可用性。
2.  **后端开发**:
    *   [ ] 实现图片上传与 OCR + LLM 串联接口。
    *   [ ] 实现健康趋势数据提取接口。
    *   [ ] 改造 Agent 响应模式，支持异步任务与微信消息推送。
3.  **前端开发**:
    *   [ ] `visit-summary` 页面 (上传 + 列表)。
    *   [ ] `health-trends` 页面 (ECharts 集成)。
    *   [ ] 适配异步通知交互 (订阅授权弹窗)。
