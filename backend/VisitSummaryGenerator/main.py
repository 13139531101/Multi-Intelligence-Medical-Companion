import click
import os
import sys
import logging
import asyncio
from A2AServer.common.server import A2AServer
from A2AServer.common.A2Atypes import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from A2AServer.task_manager import AgentTaskManager
from A2AServer.agent import BasicAgent
from dotenv import load_dotenv
from memory_service import visit_summary_memory_service

load_dotenv()

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# 强制配置 root logger
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@click.command(help="启动 A2A Server，用于加载智能 Agent 并响应任务请求")
@click.option("--host", "host", default="localhost", help="服务器绑定的主机名（默认为 localhost,可以指定具体本机ip）")
@click.option("--port", "port", default=10013,help="服务器监听的端口号（默认为 10013）")
@click.option("--prompt", "agent_prompt_file", default="memory_enhanced_agent_prompt.md",help="Agent 的 prompt 文件路径（默认为 memory_enhanced_agent_prompt.md）")
@click.option("--model", "model_name", default="deepseek-chat",help="使用的模型名称（如 deepseek-chat）")
@click.option("--provider", "provider", default="deepseek", help="模型提供方名称（如 deepseek、openai 等）")
@click.option("--mcp_config", "mcp_config_path", default="mcp_config.json",help="MCP 配置文件路径（默认为 mcp_config.json）")
@click.option("--agent_url", "agent_url", default="",help="Agent Card中对外展示和访问的地址")
def main(host, port, agent_prompt_file, model_name, provider, mcp_config_path, agent_url=""):
    """启动A2A Server
    host: 启动的Agent的主机
    port: 启动的端口
    agent_prompt_file: prompt文件
    """
    input_mode, output_mode = ["text", "text/plain"], ["text", "text/plain"]
    # Agent支持的输入和输出，默认只支持文本
    BasicAgent.SUPPORTED_CONTENT_TYPES = input_mode
    try:
        # 定义 Agent 能力和技能,  功能（支持流式响应）
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
                id="VisitSummaryGenerator",
                name="就诊摘要生成",
                description="处理医疗文档、生成就诊摘要和提供健康分析",
                tags=["医疗文档", "摘要生成", "健康分析"],
                examples=[
                    "解析门诊记录并提取关键信息",
                    "生成综合就诊摘要报告",
                    "分析健康趋势和风险评估"
                ]
            )
        if not agent_url:
            agent_url = f"http://{host}:{port}/"
        # 包括 agent 的名字、描述、接口 URL、支持的输入输出格式、版本号等
        agent_card = AgentCard(
            name="就诊摘要生成",
            description="就诊摘要生成智能体，专门处理医疗文档、生成就诊摘要和提供健康分析",
            url=agent_url,
            version="1.0.0",
            defaultInputModes=input_mode,
            defaultOutputModes=output_mode,
            capabilities=capabilities,
            skills=[skill],
        )
        agent = BasicAgent(config_path=mcp_config_path, model_name=model_name, prompt_file=agent_prompt_file, provider=provider)
        
        # 初始化记忆服务
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            memory_initialized = loop.run_until_complete(visit_summary_memory_service.initialize())
            if memory_initialized:
                agent.memory_service = visit_summary_memory_service
                logger.info("就诊摘要生成记忆服务初始化成功")
            else:
                logger.warning("就诊摘要生成记忆服务初始化失败，将在无记忆模式下运行")
                agent.memory_service = None
            loop.close()
        except Exception as e:
            logger.error(f"记忆服务初始化异常: {e}，将在无记忆模式下运行")
            agent.memory_service = None
        
        # 启动 A2A 服务器
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=agent),
            host=host,
            port=port,
        )

        logger.info(f"Starting agent on {host}:{port}")
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)

if __name__ == "__main__":
    main()
