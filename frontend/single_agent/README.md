# 测试单个A2A的Agent

# 安装
npm install

# 步骤
## 1. 运行1个A2Aserver
cd backend/AgentRAG
python main.py

## 2. 启动本项目即可测试
npm run dev


# 文档
识别表单交互：当后端返回 status.state 为 input-required 且包含 form 数据时，渲染一个表单界面，而不是显示普通文本消息。
表单渲染：根据 form.properties 动态生成输入字段，预填充 form_data 中的值，允许用户编辑缺失字段（如 date）。
提交表单：用户填写表单后点击“同意”按钮，将表单数据作为新任务发送到后端，保持与原有交互的会话一致性。
兼容性：保留原有文本消息的处理逻辑，仅在检测到表单数据时切换到表单渲染模式。