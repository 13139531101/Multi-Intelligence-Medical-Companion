import json
import logging
import os
import uuid
from datetime import datetime
from mcp.server.fastmcp import FastMCP
import sys
# Add parent directory to sys.path to import database_config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_config import DatabaseManager

# Initialize FastMCP
mcp = FastMCP("database_tool")

# Configure Logging
logger = logging.getLogger(__name__)

# Initialize Database Manager
db_manager = DatabaseManager()

def init_database():
    """Initialize the database tables."""
    try:
        # 1. Create table if not exists
        create_table_query = """
            CREATE TABLE IF NOT EXISTS consultations (
                id SERIAL PRIMARY KEY,
                consultation_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                session_id TEXT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                tags JSONB DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        """
        db_manager.execute_update(create_table_query)

        # 2. Check if session_id column exists (for existing tables created before this change)
        check_col_query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='consultations' AND column_name='session_id'
        """
        cols = db_manager.execute_query(check_col_query)
        if not cols:
             logger.info("Adding missing column 'session_id' to consultations table")
             db_manager.execute_update("ALTER TABLE consultations ADD COLUMN session_id TEXT")

        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

# Call initialization
init_database()

@mcp.tool()
def save_consultation(user_id: str, question: str, answer: str, tags: list = None) -> str:
    """
    保存健康咨询记录
    :param user_id: 用户ID
    :param question: 用户的问题
    :param answer: 智能体的回答
    :param tags: 相关的标签列表
    :return: 保存结果
    """
    try:
        consultation_id = str(uuid.uuid4())
        # 在实际应用中，session_id 可能需要从上下文获取，这里暂时生成一个新的或使用默认值
        session_id = str(uuid.uuid4())

        query = """
            INSERT INTO consultations
            (user_id, consultation_id, session_id, question, answer, tags)
            VALUES (%s, %s, %s, %s, %s, %s)
        """

        tags_json = json.dumps(tags, ensure_ascii=False) if tags else '[]'

        db_manager.execute_update(query, (user_id, consultation_id, session_id, question, answer, tags_json))

        return json.dumps({'success': True, 'consultation_id': consultation_id}, ensure_ascii=False)

    except Exception as e:
        logger.error(f"保存咨询记录失败: {e}")
        return json.dumps({'success': False, 'message': str(e)}, ensure_ascii=False)

@mcp.tool()
def get_consultation_history(user_id: str, limit: int = 10) -> str:
    """
    获取用户的历史咨询记录
    :param user_id: 用户ID
    :param limit: 获取数量限制
    :return: 历史咨询记录列表
    """
    try:
        query = """
            SELECT consultation_id, question, answer, tags, created_at
            FROM consultations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """

        results = db_manager.execute_query(query, (user_id, limit))

        return json.dumps({
            'success': True,
            'history': results
        }, ensure_ascii=False, indent=2, default=str)

    except Exception as e:
        logger.error(f"获取咨询历史失败: {e}")
        return json.dumps({'success': False, 'message': str(e)}, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
