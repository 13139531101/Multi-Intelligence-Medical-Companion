import asyncio
from typing import Any, Dict, List, AsyncGenerator, Optional, Union


async def generate_with_mock(
    conversation: List[Dict[str, Any]],
    model_cfg: Dict[str, Any],
    all_functions: List[Dict[str, Any]],
    stream: bool = False,
) -> Union[Dict[str, Any], AsyncGenerator[Dict[str, Any], None]]:
    text = "这是一个本地 mock 响应，用于验证 SSE 流式链路。"

    if not stream:
        return {"assistant_text": text, "tool_calls": []}

    async def gen() -> AsyncGenerator[Dict[str, Any], None]:
        for ch in text:
            await asyncio.sleep(0.02)
            yield {
                "assistant_text": ch,
                "tool_calls": [],
                "is_chunk": True,
                "token": True,
                "is_reasoning": False,
            }
        yield {"assistant_text": text, "tool_calls": [], "is_chunk": False}

    return gen()
