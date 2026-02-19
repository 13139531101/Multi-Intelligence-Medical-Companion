from __future__ import annotations

"""
管理端 UI 路由

- 该路由用于挂载 legacy 实现的 /admin 页面（服务端 HTML 页面）。
- 这里不做业务逻辑，直接复用 health_records_api 中的 admin_page 实现。
"""

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

# legacy.admin_page 已在 health_records_api 中实现为 FastAPI handler，这里直接挂载到当前 app 的路由树上。
router.add_api_route("/admin", legacy.admin_page, methods=["GET"])
