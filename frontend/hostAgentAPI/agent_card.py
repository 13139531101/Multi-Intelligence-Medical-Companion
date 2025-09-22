import requests
from A2AServer.common.A2Atypes import AgentCard

def get_agent_card(remote_agent_address: str) -> AgentCard:
  """Get the agent card."""
  print(f"开始获取{remote_agent_address}的agent card")
  try:
    if remote_agent_address.startswith("http") or remote_agent_address.startswith("https"):
      agent_card = requests.get(
          f"{remote_agent_address}/.well-known/agent.json",
          timeout=5
      )
    else:
      agent_card = requests.get(
          f"http://{remote_agent_address}/.well-known/agent.json",
          timeout=5
      )
    agent_card.raise_for_status()
    return AgentCard(**agent_card.json())
  except Exception as e:
    print(f"无法获取{remote_agent_address}的agent card: {e}")
    # 返回一个默认的AgentCard或者None
    return None
