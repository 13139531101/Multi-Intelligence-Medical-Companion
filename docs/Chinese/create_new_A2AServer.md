# 🧠 如何创建新的 Agent, A2AServer
本教程将指导你如何在现有 AgentRAG 系统中创建一个新的智能 Agent，包括 prompt 编写、MCP 配置和 A2A Server 启动步骤。

# 📁 第一步：创建1个项目的目录AgentRAG
```
mkdir AgentRAG
```

# ✏️ 第二步：定义 Agent 的 Prompt
编辑或创建 prompt.txt 文件，内容描述 Agent 的角色与工作流程
```
你是一名擅长复杂问题解答的智能助手。你可以调用检索工具来获取参考内容，并基于检索到的高质量信息回答用户的问题。
请遵循以下步骤完成任务：

理解用户提出的问题，并根据需要进行分解或重构；
使用检索工具查找相关资料，可以进行多次检索，直到找到充分且相关的参考内容；
结合检索结果，用自己的语言给出准确、清晰、可靠的答案；
如找不到明确答案，也应诚实说明并给出你的分析或建议。
```

# 第三步: 创建 mcpserver 目录（如果需要自定义MCP工具，你也可以使用其它已有的MCP工具）
```
mkdir -p mcpserver
touch mcpserver/rag_tool.py
```
# 第四步：定义 MCP 工具
```python
# @Desc  : eg: RAG检索工具
import time
from fastmcp import FastMCP

mcp = FastMCP("RAG检索工具")

@mcp.tool()
def RAGsearch(query: str) -> str:
    """
    根据关键词对企业知识库进行搜索
    :param query: 搜索的词语和句子
    :return:
    """
    # 模拟搜索结果, 真实开发，需要替换成自己的向量检索结果
    rag_result = """LNG 是 液化天然气 (Liquefied Natural Gas) 的英文缩写。简单来说，它就是经过冷却至零下约 162 摄氏度 (-260 华氏度) 的液态天然气。

你可以把它想象成把气体“浓缩”成液体，这样做有几个重要的好处：

体积大大缩小： 液化后的天然气体积只有气态时的约 1/600，这使得储存和运输更加高效和经济。
便于长距离运输： 由于体积小，LNG 可以通过专门的 LNG 运输船跨洋运输到没有天然气管道连接的地方。
更纯净： 在液化过程中，天然气中的杂质，如二氧化碳、硫化物和水等会被去除，使得 LNG 燃烧时更加清洁，减少污染物排放。"""
    return rag_result

if __name__ == '__main__':
    result = RAGsearch(query="LNG")
    print(result)
```


# 第五步， 配置 MCP 工具
测试下工具，然后在配置到 mcp_config.json 中，测试命令: uv run --with fastmcp fastmcp run mcpserver/rag_tool.py
在 mcp_config.json 中，确保工具名称使用 驼峰命名：
 ```
 {
  "mcpServers": {
    "RAGTool": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "fastmcp",
        "fastmcp",
        "run",
        "mcpserver/rag_tool.py"
      ]
    }
  }
}
 ```

# 配置你的LLM,创建.env文件
```
#如果使用deepseek模型，python main.py --provider deepseek --model deepseek-chat
DEEPSEEK_API_KEY=sk-xxxx

#如果使用openai模型， python main.py --provider openai --model gpt-4o
OPENAI_API_KEY=xxx
```

# 最后，启动你的Agent
python main.py --port 10006

# 在前端中使用
在单/多代理前端中，添加地址 http://localhost:10006，即可访问新代理。