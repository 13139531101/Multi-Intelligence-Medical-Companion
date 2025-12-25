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
def save_consultation(
    user_id: str,
    question: str,
    answer: str,
    tags: list = None,
    consultation_id: str = None,
    session_id: str = None,
) -> str:
    """
    保存健康咨询记录
    :param user_id: 用户ID
    :param question: 用户的问题
    :param answer: 智能体的回答
    :param tags: 相关的标签列表
    :param consultation_id: 咨询ID（用于复用同一会话）
    :param session_id: 会话ID（可选）
    :return: 保存结果
    """
    try:
        env_cid = os.getenv("A2A_CURRENT_CONVERSATION_ID") or os.getenv("A2A_CURRENT_SESSION_ID") or ""
        cid = (consultation_id or env_cid or str(uuid.uuid4())).strip()
        sid = (session_id or os.getenv("A2A_CURRENT_SESSION_ID") or cid).strip()

        cols = db_manager.execute_query(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='consultations'
            """,
        )
        colset = set([c.get("column_name") for c in (cols or []) if c and c.get("column_name")])
        if "consultation_id" not in colset or "user_id" not in colset:
            raise RuntimeError("consultations table schema incompatible")

        insert_cols = ["user_id", "consultation_id"]
        insert_vals = ["%s", "%s"]
        params = [user_id, cid]

        if "session_id" in colset:
            insert_cols.append("session_id")
            insert_vals.append("%s")
            params.append(sid)
        if "question" in colset:
            insert_cols.append("question")
            insert_vals.append("%s")
            params.append(question)
        if "answer" in colset:
            insert_cols.append("answer")
            insert_vals.append("%s")
            params.append(answer)
        if "tags" in colset:
            insert_cols.append("tags")
            insert_vals.append("%s::jsonb")
            params.append(json.dumps(tags, ensure_ascii=False) if tags else "[]")

        update_sets = []
        if "session_id" in colset:
            update_sets.append("session_id = EXCLUDED.session_id")
        if "question" in colset:
            update_sets.append("question = EXCLUDED.question")
        if "answer" in colset:
            update_sets.append("answer = EXCLUDED.answer")
        if "tags" in colset:
            update_sets.append("tags = EXCLUDED.tags")

        query = f"""
            INSERT INTO consultations ({", ".join(insert_cols)})
            VALUES ({", ".join(insert_vals)})
            ON CONFLICT (consultation_id)
            DO UPDATE SET {", ".join(update_sets) if update_sets else "user_id = EXCLUDED.user_id"}
        """
        db_manager.execute_update(query, tuple(params))

        return json.dumps({"success": True, "consultation_id": cid}, ensure_ascii=False)

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
