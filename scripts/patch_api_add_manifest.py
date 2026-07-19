"""Patch api.py: 加 manifest router."""
import re
import sys

api_path = "/app/api.py"

with open(api_path, "r", encoding="utf-8") as f:
    content = f.read()

# The pattern  "v2 registry mounted: /v2/registry/*" - use this as marker
# Insert AFTER the except clause, before any app.on_event lines
marker = 'v2 registry mounted: /v2/registry/*'
if marker not in content:
    print("FAIL: marker not found")
    sys.exit(1)

# Find the end of the try-except block for registry mount.
# Pattern: "    print(f\"[hostapi] registry mount failed: {_e}\")"
# followed by some lines, possibly followed by print(f"[hostapi] v2 multi-model endpoints mount failed...")
# followed by traceback.print_exc()
# followed by blank line

insert_after_pattern = re.compile(
    r"(    print\(f\"\[hostapi\] registry mount failed: \{_e\}\"\)\s*\n"
    r"(?:.*\n)*?    traceback\.print_exc\(\)\s*\n\n)",
    re.MULTILINE
)

m = insert_after_pattern.search(content)
if not m:
    print("FAIL: regex no match, trying simpler pattern")
    # fallback: just find 'registry mount failed' line and insert after traceback.print_exc()
    simpler = re.compile(
        r"(    traceback\.print_exc\(\))\s*\n",
        re.MULTILINE
    )
    m = simpler.search(content)
    if not m:
        print("FAIL: no print_exc")
        sys.exit(1)
    insert_at = m.end()
else:
    insert_at = m.end()

manifest_block = """
# 阶段48-21: Domain Manifest API
try:
    from A2AServer.v2.manifest_endpoints import router as manifest_router
    app.include_router(manifest_router)
    print("[hostapi] v2 manifest mounted: /v2/manifest* (domain config)")
except Exception as _e:
    print(f"[hostapi] manifest mount failed: {_e}")

"""

new_content = content[:insert_at] + manifest_block + content[insert_at:]

# verify not double-insert
if "v2 manifest mounted" in new_content[new_content.find("v2 manifest mounted")+1:]:
    print("FAIL: looks like already patched")
    sys.exit(1)

with open(api_path, "w", encoding="utf-8") as f:
    f.write(new_content)
print(f"OK: patched at offset {insert_at}, new size {len(new_content)}")
