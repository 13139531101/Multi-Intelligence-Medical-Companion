from __future__ import annotations

from typing import List

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

router.add_api_route(
    "/api/health-records",
    legacy.get_health_records,
    methods=["GET"],
    response_model=List[legacy.HealthRecord],
)
router.add_api_route(
    "/api/health-records/{record_id}",
    legacy.get_health_record,
    methods=["GET"],
    response_model=legacy.HealthRecord,
)
router.add_api_route(
    "/api/health-records",
    legacy.create_health_record,
    methods=["POST"],
    response_model=legacy.HealthRecord,
)
router.add_api_route(
    "/api/health-records/{record_id}",
    legacy.update_health_record,
    methods=["PUT"],
    response_model=legacy.HealthRecord,
)
router.add_api_route(
    "/api/health-records/{record_id}",
    legacy.delete_health_record,
    methods=["DELETE"],
)
router.add_api_route(
    "/api/health-records/statistics",
    legacy.get_health_statistics,
    methods=["GET"],
    response_model=legacy.HealthStatistics,
)
router.add_api_route(
    "/api/health-records/insights",
    legacy.get_health_insights,
    methods=["GET"],
    response_model=legacy.HealthInsightsResponse,
)
router.add_api_route(
    "/api/health-records/upload", legacy.upload_file, methods=["POST"]
)
router.add_api_route(
    "/api/health-records/upload/multiple",
    legacy.upload_multiple_files,
    methods=["POST"],
)
router.add_api_route(
    "/api/health-records/sync-to-hrm", legacy.sync_sqlite_to_hrm, methods=["POST"]
)
router.add_api_route(
    "/api/health-records/{record_id}/extracted",
    legacy.get_record_extracted_info,
    methods=["GET"],
)
router.add_api_route(
    "/api/health-records/files/{file_id}",
    legacy.get_file_attachment,
    methods=["GET"],
)
