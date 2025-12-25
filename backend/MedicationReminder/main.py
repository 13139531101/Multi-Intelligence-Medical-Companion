import asyncio
import click
import os
import sys
import logging

# 优先使用本仓库的 src 版本，避免误用 build/lib 或已安装旧版本
_current_dir = os.path.dirname(__file__)
_src_path = os.path.abspath(os.path.join(_current_dir, "..", "A2AServer", "src"))
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from A2AServer.common.server import A2AServer
from A2AServer.common.A2Atypes import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from A2AServer.task_manager import AgentTaskManager
from A2AServer.agent import BasicAgent
from dotenv import load_dotenv
from memory_service import MedicationReminderMemoryService

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


@click.command(help="启动用药提醒助手 A2A Server")
@click.option("--host", "host", default="localhost", help="服务器绑定的主机名（默认为 localhost）")
@click.option("--port", "port", default=10012,help="服务器监听的端口号（默认为 10012）")
@click.option("--prompt", "agent_prompt_file", default="memory_enhanced_agent_prompt.md",help="Agent 的 prompt 文件路径（默认为 memory_enhanced_agent_prompt.md）")
@click.option("--model", "model_name", default="deepseek-chat",help="使用的模型名称（如 deepseek-chat）")
@click.option("--provider", "provider", default="deepseek", help="模型提供方名称（如 deepseek、openai 等）")
@click.option("--mcp_config", "mcp_config_path", default="mcp_config.json",help="MCP 配置文件路径（默认为 mcp_config.json）")
@click.option("--agent_url", "agent_url", default="",help="Agent Card中对外展示和访问的地址")
def main(host, port, agent_prompt_file, model_name, provider, mcp_config_path, agent_url=""):
    """启动用药提醒助手 A2A Server
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
                id="MedicationReminder",
                name="用药提醒助手",
                description="提供智能的用药提醒、复诊预约管理和服药依从性监控服务",
                tags=["medication", "reminder", "appointment", "health"],
                examples=[
                    "帮我设置阿莫西林的用药提醒，每日3次",
                    "查看我今天的用药安排",
                    "添加下周三的复诊预约提醒"
                ]
            )
        if not agent_url:
            agent_url = f"http://{host}:{port}/"
        # 包括 agent 的名字、描述、接口 URL、支持的输入输出格式、版本号等
        agent_card = AgentCard(
            name="用药提醒助手",
            description="提供智能的用药提醒、复诊预约管理和服药依从性监控服务",
            url=agent_url,
            version="1.0.0",
            defaultInputModes=input_mode,
            defaultOutputModes=output_mode,
            capabilities=capabilities,
            skills=[skill],
        )
        agent = BasicAgent(config_path=mcp_config_path, model_name=model_name, prompt_file=agent_prompt_file, provider=provider)

        # 预加载逻辑在服务器 startup 事件中执行，避免与主事件循环不一致
        
        # 初始化记忆服务（使用 asyncio.run，避免 MainThread 无事件循环错误）
        enable_memory_flag = os.getenv("ENABLE_AGENT_MEMORY", "true").lower()
        skip_memory_init = os.getenv("SKIP_MEMORY_INIT", "0") == "1"
        enable_memory = (enable_memory_flag in ("true", "1")) and not skip_memory_init

        if not enable_memory:
            logger.warning("记忆服务未启用（ENABLE_AGENT_MEMORY=false 或 SKIP_MEMORY_INIT=1）")
        else:
            try:
                memory_service = MedicationReminderMemoryService()
                memory_initialized = asyncio.run(memory_service.initialize())
                if memory_initialized:
                    logger.info("用药提醒记忆服务初始化成功")
                else:
                    logger.warning("用药提醒记忆服务初始化失败，智能体将在无记忆模式下运行")
            except Exception as e:
                logger.error(f"记忆服务初始化异常: {e}")
                logger.warning("智能体将在无记忆模式下运行")
        # 启动 A2A 服务器（MCP 预加载由服务器生命周期管理）
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
