"""Add upload_pipeline routers to api.py."""
from pathlib import Path

api = Path("I:/A2A/3/A2AServer/backend/api.py")
text = api.read_text(encoding="utf-8")

# Insertion: 在 manifest_router 注册后加 upload router
search = "from A2AServer.v2.manifest_endpoints import router as manifest_router"
patch = """from A2AServer.v2.manifest_endpoints import router as manifest_router
from A2AServer.v2.upload_pipeline import router as upload_router_v2, file_router as upload_file_router"""

if "upload_router_v2" in text:
    print("[upload] routes already imported, skip")
else:
    text = text.replace(search, patch, 1)
    print("[upload] imports inserted")

# Add app.include_router after manifest include_router
search2 = "app.include_router(manifest_router)"
patch2 = """app.include_router(manifest_router)
    try:
        app.include_router(upload_router_v2)
        app.include_router(upload_file_router)
        print("[hostapi] v2 upload endpoints mounted: /v2/upload/file, /v2/upload/files, /v2/upload/file/{id}, /v2/files/{id}")
    except Exception as _e:
        print(f"[hostapi] v2 upload mount failed: {_e}")"""
if "upload_router_v2" in text and "v2 upload endpoints mounted" not in text:
    text = text.replace(search2, patch2, 1)
    print("[upload] routers registered")

api.write_text(text, encoding="utf-8")
print("[upload] done")
