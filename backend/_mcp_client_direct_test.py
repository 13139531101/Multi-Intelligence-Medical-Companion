import asyncio
import logging
import os
import sys

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

async def main():
    config_dir = os.path.abspath(os.path.join(os.getcwd(), 'HealthAdvisor'))
    print('config_dir:', config_dir)
    client = MCPClient(
        server_name='MemoryIntegrationTool',
        command='python',
        args=['mcpserver/memory_integration_tool.py'],
        env={
            "MEMORY_DB_HOST": "localhost",
            "MEMORY_DB_PORT": "3306",
            "MEMORY_DB_NAME": "agent_memory",
            "MEMORY_DB_USER": "root",
            "MEMORY_DB_PASSWORD": "root",
            "EMBEDDING_MODEL": "all-MiniLM-L6-v2",
            "MEMORY_ENCRYPTION_ENABLED": "false",
            "PYTHONUNBUFFERED": "1"
        },
        cwd=config_dir
    )
    ok = await client.start()
    print('client.start:', ok)
    if ok:
        tools = await client.list_tools()
        print('tools len:', len(tools))
        await client.cleanup()

if __name__ == '__main__':
    asyncio.run(main())