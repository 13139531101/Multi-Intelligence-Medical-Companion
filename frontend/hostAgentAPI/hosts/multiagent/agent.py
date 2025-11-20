import json
import os
from .host_agent import HostAgent

# 读取当前目录下的 agents.json（位于 ../../agents.json）并按 url 列表初始化
def _load_agent_urls_from_json():
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        agents_json_path = os.path.join(base_dir, "hostAgentAPI", "agents.json")
        with open(agents_json_path, "r", encoding="utf-8") as f:
            agents = json.load(f)
        return [a.get("url") for a in agents if a.get("url")]
    except Exception:
        # 兜底返回空列表，避免阻塞
        return []

root_agent = HostAgent(_load_agent_urls_from_json()).create_agent()
