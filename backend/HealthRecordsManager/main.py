import click
import os
import sys
import logging
import asyncio

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
from memory_service import health_records_memory_service
# 确保优先使用当前模块下的 database_config，避免与 AgentMemorySystem 同名模块冲突
CUR_DIR = os.path.dirname(os.path.abspath(__file__))
if CUR_DIR not in sys.path:
    sys.path.insert(0, CUR_DIR)
import importlib.util
db_config_path = os.path.join(CUR_DIR, 'database_config.py')
try:
    _spec = importlib.util.spec_from_file_location("HRM_database_config", db_config_path)
    _module = importlib.util.module_from_spec(_spec)
    assert _spec and _spec.loader
    _spec.loader.exec_module(_module)
    get_db_manager = getattr(_module, 'get_db_manager')
except Exception as _e:
    logger.error(f"加载本地 database_config 失败：{_e}")
    raise

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


@click.command(help="启动健康档案管理员 A2A Server")
@click.option("--host", "host", default="localhost", help="服务器绑定的主机名（默认为 localhost）")
@click.option("--port", "port", default=10010,help="服务器监听的端口号（默认为 10010）")
@click.option("--prompt", "agent_prompt_file", default="memory_enhanced_agent_prompt.md",help="Agent 的 prompt 文件路径（默认为 memory_enhanced_agent_prompt.md）")
@click.option("--model", "model_name", default="deepseek-chat",help="使用的模型名称（如 deepseek-chat）")
@click.option("--provider", "provider", default="deepseek", help="模型提供方名称（如 deepseek、openai 等）")
@click.option("--mcp_config", "mcp_config_path", default="mcp_config.json",help="MCP 配置文件路径（默认为 mcp_config.json）")
@click.option("--agent_url", "agent_url", default="",help="Agent Card中对外展示和访问的地址")
def main(host, port, agent_prompt_file, model_name, provider, mcp_config_path, agent_url=""):
    """启动健康档案管理员 A2A Server
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
                id="HealthRecordsManager",
                name="健康档案管理员",
                description="负责处理健康数据的录入、解析和存储，支持OCR识别、信息提取和安全存储",
                tags=["health", "ocr", "storage", "medical"],
                examples=[
                    "帮我识别这张体检报告中的文字信息",
                    "请提取这份处方单中的药物信息",
                    "保存我的健康档案数据"
                ]
            )
        if not agent_url:
            agent_url = f"http://{host}:{port}/"
        # 包括 agent 的名字、描述、接口 URL、支持的输入输出格式、版本号等
        agent_card = AgentCard(
            name="健康档案管理员",
            description="负责处理健康数据的录入、解析和存储，支持OCR识别、信息提取和安全存储",
            url=agent_url,
            version="1.0.0",
            defaultInputModes=input_mode,
            defaultOutputModes=output_mode,
            capabilities=capabilities,
            skills=[skill],
        )
        agent = BasicAgent(config_path=mcp_config_path, model_name=model_name, prompt_file=agent_prompt_file, provider=provider)

        # 预加载逻辑在服务器 startup 事件中执行，避免与主事件循环不一致

        # 启动前验证数据库连接（必要时进行初始化）
        try:
            db_manager = get_db_manager()
            if db_manager.test_connection():
                logger.info("数据库连接正常")
            else:
                logger.warning("数据库连接测试失败，尝试初始化数据库...")
                try:
                    db_manager.init_database()
                except Exception as init_err:
                    logger.error(f"数据库初始化失败：{init_err}")
                if db_manager.test_connection():
                    logger.info("数据库连接恢复正常")
                else:
                    logger.error("数据库初始化后仍无法连接，请检查 MySQL 服务与配置")
        except Exception as e:
            logger.error(f"数据库预检异常：{e}")
        
        enable_memory_flag = os.getenv("ENABLE_AGENT_MEMORY", "true").lower()
        skip_memory_init = os.getenv("SKIP_MEMORY_INIT", "0") == "1"
        enable_memory = (enable_memory_flag in ("true", "1")) and not skip_memory_init

        if not enable_memory:
            logger.warning("记忆服务未启用（ENABLE_AGENT_MEMORY=false 或 SKIP_MEMORY_INIT=1）")
        else:
            logger.info("正在初始化记忆服务...")
            try:
                memory_initialized = asyncio.run(
                    health_records_memory_service.initialize()
                )
                if memory_initialized:
                    logger.info("记忆服务初始化成功")
                else:
                    logger.warning("记忆服务初始化失败，将在无记忆模式下运行")
            except Exception as e:
                logger.error(f"记忆服务初始化异常: {e}，将在无记忆模式下运行")
        
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
