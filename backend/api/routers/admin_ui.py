from __future__ import annotations

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

router.add_api_route("/admin", legacy.admin_page, methods=["GET"])
