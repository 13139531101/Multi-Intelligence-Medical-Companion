# 🚀 A2A Server Development Guide

This guide explains how to develop and test your own A2A Server, including the project structure, setup instructions, and testing methods.

---

## 📂 Project Structure

```
backend
├── A2AServer           # Dependency package for A2A Server
├── DeepSearch          # Example project for deep search functionality
├── AgentRAG            # Example project for Agent RAG
├── LNGExpert           # Example project for Agent flexible workflow
└── client.py           # Client script for testing A2A Servers
```

---

## 🛠️ Developing Your Own A2A Server

Follow these steps to create your custom A2A Server by using the `DeepSearch` example as a template.

### 1. Clone the DeepSearch Directory
Copy the entire `DeepSearch` directory to start your project:

```
DeepSearch
├── .env                # Stores API keys for models
├── main.py             # Entry point for your A2A Server
├── mcp_config.json     # Configuration file for your MCP Server
├── mcpserver/          # Optional: MCP Server code
│   └── search_tool.py  # Example MCP tool (supports multiple tools)
└── prompt.txt          # Prompt file for your Agent
```

### 2. Customize Your Server
- **Update `.env`**: Add your model API keys.
- **Modify `main.py`**: Implement your A2A Server logic.
- **Configure `mcp_config.json`**: Define your MCP tools and settings.
- **Add Tools in `mcpserver/`**: Create additional tools as needed (e.g., `search_tool.py`).
- **Edit `prompt.txt`**: Customize the Agent's prompt to suit your use case.

---

## 🧪 Testing Your A2A Server

You can test your A2A Server using either the command-line client or the frontend interface.

### Option 1: Command-Line Testing
Use the provided `client.py` script to test your Agent:

```bash
python client.py --agent http://localhost:10004
```

### Option 2: Frontend Testing
Test your Agent using the single-agent frontend interface:
1. Navigate to the frontend directory:
   ```bash
   cd frontend/single_agent
   npm install
   npm run dev
   ```
2. Open the frontend in your browser, input your Agent's URL (e.g., `http://localhost:10004`), and start testing.

---

## ⚠️ Important Notes

- **Tool Naming in `mcp_config.json`**:
  - Use camelCase or PascalCase for tool names (e.g., `SearchTool`, `RAGTool`).
  - Avoid underscores (e.g., do not use `Search_Tool` or `RAG_Tool`), as they may cause tools to be unrecognized.

---

## 💡 Next Steps
- Explore the `DeepSearch` example to understand A2A Server implementation.
- Extend your server by adding more tools in the `mcpserver/` directory.
- Integrate with the multi-agent frontend for collaborative Agent testing.