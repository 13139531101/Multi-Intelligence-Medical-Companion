import os
import sys
import json
import time
import threading
import asyncio
from datetime import datetime

# Add backend to path to import notification_service
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from notification_service import notification_service
except ImportError:
    notification_service = None

# Mock AI Analysis (replace with actual logic or import from ai_analysis_tool)
def mock_analyze_trends(user_id, feature, period):
    time.sleep(5) # Simulate long processing
    return {
        "feature": feature,
        "trend": "Stable",
        "advice": "Keep up the good work.",
        "data_points": [1, 2, 3]
    }

def background_task(user_id, feature, period, openid):
    try:
        # 1. Perform Analysis
        # In a real scenario, we would call the actual analysis function here.
        # For now, we mock it.
        result = mock_analyze_trends(user_id, feature, period)

        # 2. Prepare Notification Data
        # Template data depends on the configured template in WeChat
        # Assuming a template like:
        # {{thing1.DATA}}: 任务名称 (Task Name)
        # {{thing2.DATA}}: 完成状态 (Status)
        # {{thing3.DATA}}: 结果摘要 (Result Summary)

        data = {
            "thing1": {"value": f"健康趋势分析: {feature}"},
            "thing2": {"value": "已完成"},
            "thing3": {"value": f"趋势: {result['trend']}, 建议: {result['advice'][:15]}..."}
        }

        # 3. Send Notification
        # We need an event loop for async send
        if notification_service and openid:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(notification_service.send_subscribe_message(
                openid=openid,
                template_id=notification_service.template_ids.get("task_complete", ""),
                data=data,
                page="pages/health-trends/index"
            ))
            loop.close()
            print(f"Notification sent to {openid}")
        else:
            print("Notification service not available or openid missing.")

    except Exception as e:
        print(f"Background task failed: {e}")

def analyze_health_trends_async(user_id: str, feature: str, period: str = "90d") -> str:
    """
    Start an asynchronous health trend analysis.
    Returns a message indicating the task has started.
    """
    # Need to get openid from DB or passed in.
    # For now, we assume we can fetch it or it's passed.
    # But the tool signature is fixed by what the LLM provides.
    # We'll try to fetch openid from user_id.

    openid = None
    try:
        import psycopg
        from psycopg.rows import dict_row
        # Re-use logic to get DB connection
        db_url = os.environ.get("DATABASE_URL") or "postgresql://pha:pha_pass@localhost:5432/personal_health_assistant"
        conn = psycopg.connect(db_url, row_factory=dict_row)
        with conn.cursor() as cur:
            cur.execute("SELECT openid FROM users WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            if res:
                openid = res.get("openid")
        conn.close()
    except Exception as e:
        print(f"Failed to fetch openid: {e}")
        # Fallback: if we can't get openid, we can't notify via WeChat.
        # But we can still run the task and maybe update a notification center in-app.

    if not openid:
        return f"分析任务已启动，但未找到关联的微信OpenID，无法发送通知。分析结果稍后可在健康趋势页面查看。"

    # Start background thread
    t = threading.Thread(target=background_task, args=(user_id, feature, period, openid))
    t.daemon = True # Daemon thread dies when main process dies, but BasicAgent should stay alive.
    t.start()

    return f"已启动针对 {feature} 的健康趋势分析任务。分析预计需要几分钟，完成后将通过微信服务通知发送给您。"

if __name__ == "__main__":
    # Simple test
    # python mcpserver/async_analysis_tool.py
    import sys
    # Mocking input for testing
    if len(sys.argv) > 1:
        print(analyze_health_trends_async("test_user", "blood_pressure"))
