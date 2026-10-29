"""
LangChain BaseCallbackHandler 适配器：把 LangChain 的 LLM 调用回写到 cost_endpoints.record_call。

数据源（按可用顺序）:
1. response.llm_output["token_usage"]            — ChatOpenAI / DeepSeek / DashScope 兼容模式
2. response.llm_output["usage"] (dict)            — 一些 OpenAI 兼容网关
3. response.generations[0][0].message.usage_metadata  — LangChain 1.0 标准字段
4. response.generations[0][0].message.response_metadata["token_usage"]  — 兜底

provider 名约定: 从 model 字符串前缀猜，详见 _infer_provider()。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

try:
    # langchain-core 0.3+ 提供 BaseCallbackHandler
    from langchain_core.callbacks import BaseCallbackHandler
    _HAVE_LC = True
except Exception:  # pragma: no cover
    BaseCallbackHandler = object  # type: ignore
    _HAVE_LC = False

logger = logging.getLogger(__name__)


def _infer_provider(model: str, base_url: Optional[str] = None) -> str:
    """从 model 字符串或 base_url 推断 provider 名（与 multi_model.PROVIDERS 对齐）"""
    m = (model or "").lower()
    if m.startswith("deepseek"):
        return "deepseek"
    if m.startswith("qwen") or m.startswith("dashscope") or m.startswith("tongyi"):
        return "dashscope"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("moonshot") or m.startswith("kimi"):
        return "moonshot"
    b = (base_url or "").lower()
    if "deepseek.com" in b:
        return "deepseek"
    if "dashscope" in b or "aliyun" in b:
        return "dashscope"
    if "anthropic" in b:
        return "anthropic"
    if "moonshot" in b or "moonshot.cn" in b:
        return "moonshot"
    return "openai"


def _extract_usage(response: Any) -> Dict[str, int]:
    """从 LLMResult / AIMessage 上抠 token_usage，兼容多种字段位置"""
    out: Dict[str, int] = {}
    # 1) llm_output
    llm_output = getattr(response, "llm_output", None) or {}
    if isinstance(llm_output, dict):
        tu = llm_output.get("token_usage") or llm_output.get("usage") or {}
        if isinstance(tu, dict):
            pt = tu.get("prompt_tokens") or tu.get("input_tokens")
            ct = tu.get("completion_tokens") or tu.get("output_tokens")
            if pt is not None:
                out["prompt_tokens"] = int(pt)
            if ct is not None:
                out["completion_tokens"] = int(ct)
        if "prompt_tokens" in out and "completion_tokens" in out:
            return out
    # 2) generations[0][0].message
    try:
        gens = response.generations or []
        if gens and gens[0]:
            msg = getattr(gens[0][0], "message", None)
            if msg is not None:
                um = getattr(msg, "usage_metadata", None)
                if isinstance(um, dict):
                    pt = um.get("input_tokens")
                    ct = um.get("output_tokens")
                    if pt is not None:
                        out["prompt_tokens"] = int(pt)
                    if ct is not None:
                        out["completion_tokens"] = int(ct)
                if "prompt_tokens" in out and "completion_tokens" in out:
                    return out
                rm = getattr(msg, "response_metadata", None) or {}
                if isinstance(rm, dict):
                    tu = rm.get("token_usage") or rm.get("usage") or {}
                    if isinstance(tu, dict):
                        pt = tu.get("prompt_tokens") or tu.get("input_tokens")
                        ct = tu.get("completion_tokens") or tu.get("output_tokens")
                        if pt is not None:
                            out["prompt_tokens"] = int(pt)
                        if ct is not None:
                            out["completion_tokens"] = int(ct)
    except Exception:  # pragma: no cover
        pass
    return out


if _HAVE_LC:

    class CostTrackingHandler(BaseCallbackHandler):  # type: ignore[misc]
        """挂到 ChatOpenAI 的 callbacks=[...] 上，每次 LLM 完成时推一条到 cost_endpoints.record_call"""

        def __init__(self) -> None:
            super().__init__()
            # run 级别：on_chat_model_start → on_llm_end 共享 model 名
            self._last_model: str = ""
            self._last_base_url: Optional[str] = None

        def on_chat_model_start(self, serialized: Dict[str, Any], messages: Any, **kwargs: Any) -> None:  # noqa: D401
            try:
                # serialized = {"id": [...], "name": "...", "type": "openai-chat", "kwargs": {"model": "...", ...}}
                node_name = ""
                if isinstance(serialized, dict):
                    node_name = str(serialized.get("name") or "")
                    id_list = serialized.get("id") or []
                    if isinstance(id_list, list) and id_list:
                        last = id_list[-1]
                        if isinstance(last, str):
                            node_name = node_name or last
                inner = (serialized or {}).get("kwargs") or {}
                model = inner.get("model") or inner.get("model_name") or node_name
                self._last_model = str(model or "")
            except Exception:  # pragma: no cover
                pass

        def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: D401
            try:
                usage = _extract_usage(response)
                if not usage:
                    return
                # 优先用 on_chat_model_start 抓到的 model；fallback llm_output
                llm_output = getattr(response, "llm_output", None) or {}
                model = (
                    self._last_model
                    or llm_output.get("model_name")
                    or llm_output.get("model")
                    or ""
                )
                provider = _infer_provider(model)
                try:
                    from .cost_endpoints import record_call
                except Exception:  # pragma: no cover
                    return
                record_call(
                    provider=provider,
                    model=str(model or provider),
                    task_type="chat",
                    prompt_tokens=int(usage.get("prompt_tokens", 0)),
                    completion_tokens=int(usage.get("completion_tokens", 0)),
                    latency_ms=0.0,
                    feature="",
                )
            except Exception as e:  # pragma: no cover
                logger.debug(f"[cost-cb] on_llm_end failed: {e}")
else:  # pragma: no cover

    class CostTrackingHandler(object):  # type: ignore[no-redef]
        def on_llm_end(self, *args, **kwargs):  # noqa: D401
            return
        def on_chat_model_start(self, *args, **kwargs):  # noqa: D401
            return
