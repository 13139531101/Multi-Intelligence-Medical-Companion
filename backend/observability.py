"""
PHA v2 可观测性模块（阶段1）
- 自动接入 LangSmith（如果配置了 LANGCHAIN_API_KEY）
- 自动接入 Langfuse（如果配置了 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY）
- 自动接入 OpenTelemetry（如果配置了 OTEL_EXPORTER_OTLP_ENDPOINT）

**设计原则**：
- 现有代码零侵入：只需要在服务入口 import 一次
- 没配置环境变量时静默跳过（不影响开发）
- 自动给所有 LangChain / LangGraph 调用打 trace

**使用方式**（在每个服务的入口文件最顶部）：

```python
from observability import setup_observability
setup_observability(service_name="host-agent-api")
```

环境变量（任选其一或全部）：
- LANGCHAIN_TRACING_V2=true
- LANGCHAIN_API_KEY=lsv2_pt_xxxx
- LANGCHAIN_PROJECT=pha-prod

- LANGFUSE_PUBLIC_KEY=pk-lf-xxxx
- LANGFUSE_SECRET_KEY=sk-lf-xxxx
- LANGFUSE_HOST=https://cloud.langfuse.com  # 或自建地址

- OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
- OTEL_SERVICE_NAME=pha-host-agent
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def setup_observability(service_name: str = "pha-service") -> None:
    """
    初始化可观测性（LangSmith / Langfuse / OpenTelemetry）。
    任何环境变量没配都安全跳过。
    """
    _setup_langsmith(service_name)
    _setup_langfuse(service_name)
    _setup_opentelemetry(service_name)


def _setup_langsmith(service_name: str) -> None:
    """接入 LangSmith（LangChain 官方 tracing 平台）。"""
    api_key = os.getenv("LANGCHAIN_API_KEY")
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"

    if not (api_key and tracing):
        logger.debug("[observability] LangSmith 未启用（缺 API_KEY 或 TRACING_V2）")
        return

    os.environ.setdefault("LANGCHAIN_PROJECT", f"pha-{service_name}")
    try:
        # LangChain 1.x 自动读取环境变量
        from langsmith import Client  # noqa: F401

        logger.info(
            "[observability] LangSmith 已启用：project=%s",
            os.environ["LANGCHAIN_PROJECT"],
        )
    except ImportError:
        logger.warning("[observability] langsmith 未安装，跳过")


def _setup_langfuse(service_name: str) -> None:
    """接入 Langfuse（开源 LLM 可观测平台）。"""
    public = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret = os.getenv("LANGFUSE_SECRET_KEY")
    if not (public and secret):
        logger.debug("[observability] Langfuse 未启用（缺 PUBLIC_KEY / SECRET_KEY）")
        return

    try:
        from langfuse import Langfuse  # noqa: F401

        os.environ.setdefault("LANGFUSE_SERVICE_NAME", service_name)
        logger.info("[observability] Langfuse 已启用：service=%s", service_name)
    except ImportError:
        logger.warning("[observability] langfuse 未安装，跳过")


def _setup_opentelemetry(service_name: str) -> None:
    """接入 OpenTelemetry（统一 trace/exporter）。"""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.debug("[observability] OpenTelemetry 未启用（缺 OTEL_EXPORTER_OTLP_ENDPOINT）")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # 自动埋点 FastAPI + httpx
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
            logger.info("[observability] OTel: HTTPX 已埋点")
        except ImportError:
            pass

        logger.info(
            "[observability] OpenTelemetry 已启用：service=%s, endpoint=%s",
            service_name,
            endpoint,
        )
    except ImportError:
        logger.warning("[observability] opentelemetry-sdk 未安装，跳过")


def instrument_fastapi(app) -> None:
    """给 FastAPI app 注入 OTel 埋点（在 app 创建之后调用）。"""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("[observability] FastAPI app 已埋点")
    except ImportError:
        logger.warning("[observability] opentelemetry-instrumentation-fastapi 未安装")


# 启动时自动检测（方便直接在入口 import）
if __name__ == "__main__":
    setup_observability("pha-cli")
    print("[OK] 可观测性已初始化")
