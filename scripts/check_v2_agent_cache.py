"""查看 V2Agent._agent_instance_cache 内容"""
from A2AServer.v2.v2_agent import V2Agent
print('cache keys:', list(V2Agent._agent_instance_cache.keys()))
for k, v in V2Agent._agent_instance_cache.items():
    print(f'  {k}: {type(v).__name__}')
    print(f'    attrs: {[x for x in dir(v) if not x.startswith("_")][:15]}')
    if hasattr(v, 'name'):
        print(f'    name: {v.name}')
    if hasattr(v, 'model'):
        print(f'    model: {v.model}')