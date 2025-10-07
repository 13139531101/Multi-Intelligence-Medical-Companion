import asyncio
import logging
import os
import sys
from typing import Tuple, Dict, Any

# Ensure local A2AServer/src is preferred over any installed package
_current_dir = os.path.dirname(os.path.abspath(__file__))
_src_path = os.path.join(_current_dir, 'A2AServer', 'src')
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from A2AServer.mcp_client.client import MCPClient

logging.basicConfig(level=logging.DEBUG)
# 强化客户端日志输出，便于看到 start() 失败原因
_client_logger = logging.getLogger('A2AServer.mcp_client.client')
_client_logger.setLevel(logging.DEBUG)
if not _client_logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
    _client_logger.addHandler(_h)
    _client_logger.propagate = False


def build_server_config(target: str) -> Tuple[str, str, list[str], Dict[str, str], str]:
    """根据目标服务器构建 MCPClient 所需参数。
    返回: (server_name, command, args, env, cwd)
    """
    target = (target or '').strip() or 'MemoryIntegrationTool'
    backend_root = _current_dir
    hrm_dir = os.path.join(backend_root, 'HealthRecordsManager')

    # 默认环境变量（可通过系统环境覆盖）
    env: Dict[str, str] = {
        # MySQL 相关，供 StorageTool/ReminderTool 使用
        'DB_HOST': os.getenv('DB_HOST', 'localhost'),
        'DB_PORT': os.getenv('DB_PORT', '3306'),
        'DB_USER': os.getenv('DB_USER', 'root'),
        'DB_PASSWORD': os.getenv('DB_PASSWORD', 'root'),
        'DB_NAME': os.getenv('DB_NAME', 'personal_health_assistant'),
        # 记忆工具相关
        'MEMORY_DB_HOST': os.getenv('MEMORY_DB_HOST', 'localhost'),
        'MEMORY_DB_PORT': os.getenv('MEMORY_DB_PORT', '3306'),
        'MEMORY_DB_NAME': os.getenv('MEMORY_DB_NAME', 'agent_memory'),
        'MEMORY_DB_USER': os.getenv('MEMORY_DB_USER', 'root'),
        'MEMORY_DB_PASSWORD': os.getenv('MEMORY_DB_PASSWORD', 'root'),
        'MEMORY_EMBEDDING_MODEL': os.getenv('MEMORY_EMBEDDING_MODEL', 'all-MiniLM-L6-v2'),
        'PYTHONUNBUFFERED': '1',
    }

    if target.lower() == 'storagetool':
        server_name = 'StorageTool'
        command = 'uv'
        args = [
            'run', '--with', 'mcp[cli]', '--with', 'mysql-connector-python', '--with', 'cryptography',
            'mcp', 'run', 'mcpserver/storage_tool.py'
        ]
        cwd = hrm_dir
    elif target.lower() == 'remindertool':
        server_name = 'ReminderTool'
        command = 'uv'
        args = [
            'run', '--with', 'mcp[cli]', '--with', 'mysql-connector-python',
            'mcp', 'run', 'mcpserver/reminder_tool.py'
        ]
        cwd = hrm_dir
    else:
        # 默认测试 MemoryIntegrationTool（Python 直接运行）
        server_name = 'MemoryIntegrationTool'
        command = 'python'
        args = ['mcpserver/memory_integration_tool.py']
        cwd = hrm_dir

    return server_name, command, args, env, cwd


async def main():
    target = sys.argv[1] if len(sys.argv) > 1 else 'MemoryIntegrationTool'
    server_name, command, args, env, cwd = build_server_config(target)

    print(f'准备启动: server={server_name}\n  command={command}\n  args={args}\n  cwd={cwd}')
    print('环境变量(部分):', {k: env[k] for k in ['DB_HOST','DB_PORT','DB_USER','DB_NAME'] if k in env})

    client = MCPClient(
        server_name=server_name,
        command=command,
        args=args,
        env=env,
        cwd=cwd,
    )
    ok = await client.start()
    print('client.start:', ok)
    if ok:
        try:
            tools = await client.list_tools()
            print('tools len:', len(tools))
            for t in tools:
                # t 可能是 Tool dataclass-like 或自定义对象，尽量打印通用字段
                name = getattr(t, 'name', None) or getattr(t, 'tool_name', None) or str(t)
                desc = getattr(t, 'description', '')
                print(f'- {name}: {desc}')
        except Exception as e:
            print('list_tools 调用异常:', e)
        finally:
            await client.cleanup()

if __name__ == '__main__':
    asyncio.run(main())