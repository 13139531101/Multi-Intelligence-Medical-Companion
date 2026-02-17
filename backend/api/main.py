from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import health_records_api as legacy

from .routers import (
    admin_ui,
    consultations,
    dashboard,
    health_records,
    health_trends,
    medical_kb,
    rag,
    visit_summaries,
)

app = FastAPI(
    title="健康档案管理API",
    description="提供健康档案的创建、查询、更新、删除等功能",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag.router)
app.include_router(medical_kb.router)
app.include_router(dashboard.router)
app.include_router(visit_summaries.router)
app.include_router(consultations.router)
app.include_router(health_records.router)
app.include_router(health_trends.router)
app.include_router(admin_ui.router)


@app.on_event("startup")
async def startup_event():
    await legacy.startup_event()


@app.on_event("shutdown")
async def shutdown_event():
    try:
        pool = getattr(legacy, "_db_pool", None)
        if pool is not None:
            try:
                pool.close()
            except Exception:
                pass
    except Exception:
        pass
