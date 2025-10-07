"""
DashScope (Qwen) provider implementation using OpenAI-compatible API.

This provider leverages OpenAI's AsyncOpenAI client pointed to DashScope's
OpenAI-compatible endpoint, enabling tool calls and streaming similarly
to other providers in this codebase.
"""

import os
import json
from typing import Dict, List, Any, AsyncGenerator, Optional, Union

from openai import AsyncOpenAI, APIError, RateLimitError


async def generate_with_dashscope_stream(
    client: AsyncOpenAI,
    model_name: str,
    conversation: List[Dict],
    formatted_functions: List[Dict],
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncGenerator:
    """Internal function for streaming generation"""
    try:
        tools = [{"type": "function", "function": f} for f in formatted_functions] if formatted_functions else None
        response = await client.chat.completions.create(
            model=model_name,
            messages=conversation,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice="auto",
            stream=True,
        )

        current_tool_calls = []
        current_content = ""

        async for chunk in response:
            delta = chunk.choices[0].delta

            if delta.content:
                # Yield tokens immediately
                yield {"assistant_text": delta.content, "tool_calls": [], "is_chunk": True, "token": True}
                current_content += delta.content

            # Handle tool call deltas (OpenAI-compatible streaming format)
            if delta.tool_calls:
                for tool_call in delta.tool_calls:
                    while tool_call.index >= len(current_tool_calls):
                        current_tool_calls.append({
                            "id": "",
                            "function": {"name": "", "arguments": ""}
                        })

                    current_tool = current_tool_calls[tool_call.index]
                    if tool_call.id:
                        current_tool["id"] = tool_call.id
                    if tool_call.function.name:
                        current_tool["function"]["name"] = (
                            current_tool["function"]["name"] + tool_call.function.name
                        )
                    if tool_call.function.arguments:
                        args = tool_call.function.arguments
                        cur = current_tool["function"]["arguments"]
                        if args.startswith("{") and not cur:
                            current_tool["function"]["arguments"] = args
                        elif args.endswith("}") and cur:
                            # Try to fix incomplete JSON
                            if not cur.startswith("{"):
                                cur = "{" + cur
                            if not cur.endswith("}"):
                                cur = cur + "}"
                            try:
                                parsed = json.loads(cur)
                                current_tool["function"]["arguments"] = json.dumps(parsed)
                            except json.JSONDecodeError:
                                current_tool["function"]["arguments"] = "{}"

                # Yield accumulated content with best-effort tool calls
                final_tool_calls = []
                for tc in current_tool_calls:
                    args = tc["function"]["arguments"]
                    if not args:
                        args = "{}"
                    try:
                        json.loads(args)
                        final_tool_calls.append(tc)
                    except json.JSONDecodeError:
                        tc["function"]["arguments"] = "{}"
                        final_tool_calls.append(tc)

                yield {
                    "assistant_text": current_content,
                    "tool_calls": final_tool_calls,
                    "is_chunk": False,
                }

    except Exception as e:
        yield {"assistant_text": f"DashScope error: {str(e)}", "tool_calls": [], "is_chunk": False}


async def generate_with_dashscope_sync(
    client: AsyncOpenAI,
    model_name: str,
    conversation: List[Dict],
    formatted_functions: List[Dict],
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Dict:
    """Internal function for non-streaming generation"""
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=conversation,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            tools=[{"type": "function", "function": f} for f in formatted_functions],
            tool_choice="auto",
            stream=False,
        )

        choice = response.choices[0]
        assistant_text = choice.message.content or ""
        tool_calls = []

        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                if tc.type == "function":
                    tool_call = {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    try:
                        json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_call["function"]["arguments"] = "{}"
                    tool_calls.append(tool_call)
        return {"assistant_text": assistant_text, "tool_calls": tool_calls}

    except APIError as e:
        return {"assistant_text": f"DashScope API error: {str(e)}", "tool_calls": []}
    except RateLimitError as e:
        return {"assistant_text": f"DashScope rate limit: {str(e)}", "tool_calls": []}
    except Exception as e:
        return {"assistant_text": f"Unexpected DashScope error: {str(e)}", "tool_calls": []}


async def generate_with_dashscope(
    conversation: List[Dict],
    model_cfg: Dict,
    all_functions: List[Dict],
    stream: bool = False,
) -> Union[Dict, AsyncGenerator]:
    """
    Generate text using DashScope's OpenAI-compatible API.

    Reads API key from model_cfg["apiKey"] or env var `DASHSCOPE_API_KEY`.
    If model_cfg contains `apiBase`, it will be used; otherwise defaults to
    DashScope's OpenAI-compatible endpoint.
    """
    api_key = model_cfg.get("apiKey") or os.getenv("DASHSCOPE_API_KEY")
    # Default to DashScope's OpenAI-compatible endpoint
    base_url = model_cfg.get("apiBase", "https://dashscope.aliyuncs.com/compatible/v1")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    model_name = model_cfg["model"]
    temperature = model_cfg.get("temperature", None)
    top_p = model_cfg.get("top_p", None)
    max_tokens = model_cfg.get("max_tokens", None)

    formatted_functions = [
        {
            "name": func["name"],
            "description": func["description"],
            "parameters": func["parameters"],
        }
        for func in all_functions
    ]

    if stream:
        return generate_with_dashscope_stream(
            client, model_name, conversation, formatted_functions, temperature, top_p, max_tokens
        )
    else:
        return await generate_with_dashscope_sync(
            client, model_name, conversation, formatted_functions, temperature, top_p, max_tokens
        )