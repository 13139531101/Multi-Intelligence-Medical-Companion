"""Test DomainManifest loading + switching."""
import os
import sys
sys.path.insert(0, 'backend')
sys.path.insert(0, 'backend/A2AServer/src')

import A2AServer.v2.domain_manifest as dm

print(f"Manifest dir: {dm._MANIFEST_DIR}")
print(f"YAML files: {sorted(p.name for p in dm._MANIFEST_DIR.glob('*.yaml')) if dm._MANIFEST_DIR.exists() else 'NONE'}")

print("\n=== Test 1: 默认 (PHA) ===")
os.environ.pop('PHA_DOMAIN_MANIFEST', None)
m = dm.load_default()
print(f"  domain: {m.domain.name}")
print(f"  host_agent: {m.host_agent_name}")
for a in m.agents:
    print(f"    - {a.name} ({a.display_name}) port={a.port} dangerously={a.dangerously}")

print("\n=== Test 2: HR 企业助手 ===")
os.environ['PHA_DOMAIN_MANIFEST'] = 'hr.company'
m = dm.load_default()
print(f"  domain: {m.domain.name}")
print(f"  host_agent: {m.host_agent_name}")
for a in m.agents:
    print(f"    - {a.name} ({a.display_name}) port={a.port} dangerously={a.dangerously}")

print("\n=== Test 3: 电商 ===")
os.environ['PHA_DOMAIN_MANIFEST'] = 'ecommerce.support'
m = dm.load_default()
print(f"  domain: {m.domain.name}")
print(f"  host_agent: {m.host_agent_name}")
for a in m.agents:
    print(f"    - {a.name} ({a.display_name}) port={a.port} dangerously={a.dangerously}")

print("\n=== Test 4: 教育 ===")
os.environ['PHA_DOMAIN_MANIFEST'] = 'edu.tutor'
m = dm.load_default()
print(f"  domain: {m.domain.name}")
print(f"  host_agent: {m.host_agent_name}")
for a in m.agents:
    print(f"    - {a.name} ({a.display_name}) port={a.port} dangerously={a.dangerously}")

print("\n[OK] 4 个 yaml 都能加载")
