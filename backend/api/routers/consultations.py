from __future__ import annotations

from typing import List

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

router.add_api_route(
    "/api/consultations/history",
    legacy.get_consultation_history,
    methods=["GET"],
    response_model=List[legacy.Consultation],
)
router.add_api_route(
    "/api/consultations/create",
    legacy.create_consultation,
    methods=["POST"],
    response_model=legacy.Consultation,
)
router.add_api_route(
    "/api/consultations/delete/{consultation_id}",
    legacy.delete_consultation,
    methods=["DELETE"],
)
router.add_api_route(
    "/api/consultations/message", legacy.save_consultation_message, methods=["POST"]
)
router.add_api_route(
    "/api/consultations/{consultation_id}/messages",
    legacy.get_consultation_messages,
    methods=["GET"],
)
