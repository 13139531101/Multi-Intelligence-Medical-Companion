
import os
import logging
import json
import hashlib
import re
import atexit
import asyncio
import sys
import time
from typing import Dict, List, Any

# Set up logger
logger = logging.getLogger(__name__)

# Keep track of client resources that need cleanup
_active_clients = set()

# Track last request time for rate limiting
_last_request_time = 0.0

# Get rate limit from env var (in seconds) or default to 60 seconds (1 minute)
def get_rate_limit_seconds():
    try:
        return float(os.getenv("ANTHROPIC_RATE_LIMIT_SECONDS", "60"))
    except (ValueError, TypeError):
        logger.warning("Invalid ANTHROPIC_RATE_LIMIT_SECONDS value, using default of 60 seconds")
        return 60.0

def get_caching_enabled():
    try:
        return bool(os.getenv("ANTHROPIC_CACHING_ENABLED", "true"))
    except (ValueError, TypeError):
        logger.warning("Invalid ANTHROPIC_CACHING_ENABLED value, using default of True")
        return True

def _cleanup_clients():
    """Ensure all active clients are closed during interpreter shutdown"""
    # Skip if no clients to clean up
    if not _active_clients:
        return
        
    try:
        # Try to get or create an event loop for cleanup
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                # If the main loop is closed, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # No event loop in thread, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # Now use the loop to clean up clients
        for client in list(_active_clients):
            try:
                if hasattr(client, 'close'):
                    if asyncio.iscoroutinefunction(client.close):
                        try:
                            loop.run_until_complete(client.close())
                        except Exception as e:
                            logger.error(f"Error in async client close: {e}")
                    else:
                        client.close()
            except Exception as e:
                logger.error(f"Error cleaning up client during shutdown: {e}")
            finally:
                _active_clients.discard(client)
                
        # Close our temporary loop if we created one
        try:
            if not loop.is_closed():
                loop.close()
        except:
            pass
                
    except Exception as e:
        # Last resort - make sure we don't crash during interpreter shutdown
        logger.error(f"Error during client cleanup at exit: {e}")
        
    # Clear the set to help with garbage collection
    _active_clients.clear()

# Register the cleanup function to run at exit
atexit.register(_cleanup_clients)

def generate_tool_id(tool_name: str) -> str:
    """
    Generate a deterministic tool ID from the tool name.
    
    Args:
        tool_name: The name of the tool
        
    Returns:
        A string ID for the tool
    """
    # Create a hash from just the tool name
    name_underscored = re.sub(r'[^a-zA-Z0-9]', '_', tool_name)
    return name_underscored

def format_tools(all_functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format functions into Anthropic's tool format.
    
    Args:
        all_functions: List of function definitions
        
    Returns:
        List of formatted tools for Anthropic API
    """
    anthropic_tools = []
    
    for i, func in enumerate(all_functions):
        # Extract required fields
        name = func.get("name")
        description = func.get("description", "")
        parameters = func.get("parameters", {})
        
        if not name:
            logger.warning(f"Function at index {i} has no name, skipping")
            continue
        
        # Format exactly according to Anthropic's documentation
        tool = {
            "name": name,
            "description": description,
            "input_schema": parameters
        }
        
        # Verify input_schema is properly formatted
        if not isinstance(tool["input_schema"], dict):
            logger.warning(f"Invalid input_schema for function {name}, using default")
            tool["input_schema"] = {"type": "object", "properties": {}}
        
        # Ensure input_schema has required type field
        if "type" not in tool["input_schema"]:
            tool["input_schema"]["type"] = "object"
            
        anthropic_tools.append(tool)
    
    return anthropic_tools

async def generate_with_anthropic(conversation, model_cfg, all_functions):
    """
    Generate text using Anthropic's API.
    
    Args:
        conversation: The conversation history
        model_cfg: Configuration for the model
        all_functions: Available functions for the model to call
        
    Returns:
        Dict containing assistant_text and tool_calls
    """
    from anthropic import AsyncAnthropic, APIError as AnthropicAPIError
    
    global _last_request_time
    
    # Apply rate limiting
    rate_limit_seconds = get_rate_limit_seconds()
    current_time = time.time()
    time_since_last_request = current_time - _last_request_time
    
    if time_since_last_request < rate_limit_seconds:
        # Need to wait before making a new request
        wait_time = rate_limit_seconds - time_since_last_request
        logger.info(f"Rate limiting: Waiting {wait_time:.2f} seconds before making Anthropic API request")
        await asyncio.sleep(wait_time)
    
    # Update last request time after waiting (if needed)
    _last_request_time = time.time()

    anthro_api_key = model_cfg.get("apiKey", os.getenv("ANTHROPIC_API_KEY"))
    
    # Initialize result outside context manager
    result = {"assistant_text": "", "tool_calls": []}
    
    # Create the client
    client = None
    try:
        client = AsyncAnthropic(api_key=anthro_api_key)
        # Register for cleanup at interpreter shutdown - only if we need to
        if client:
            _active_clients.add(client)
    
        # Store tool ID mappings to ensure consistency
        tool_id_map = {}
        
        # Helper function to get or create a tool ID
        def get_or_create_tool_id(tool_name):
            if tool_name in tool_id_map:
                return tool_id_map[tool_name]
            else:
                new_id = generate_tool_id(tool_name)
                tool_id_map[tool_name] = new_id
                return new_id

        model_name = model_cfg["model"]
        temperature = model_cfg.get("temperature", 0.7)
        top_k = model_cfg.get("top_k", None)
        top_p = model_cfg.get("top_p", None)
        max_tokens = model_cfg.get("max_tokens", 1024)

        # Extract system messages and non-system messages
        system_messages = []
        non_system_messages = []
        last_assistant_content = None

        # Process conversation messages for Anthropic format
        for i, msg in enumerate(conversation):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "system":
                system_messages.append({
                    "type": "text",
                    "text": content,
                })
            elif role == "tool":
                new_msg = {
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id"),
                        "content": msg.get("content")
                    }]
                }
                non_system_messages.append(new_msg)
            elif role == "assistant" and isinstance(content, str) and msg.get("tool_calls"):
                # Create a new message with content blocks for text and tool_use
                new_msg = {"role": "assistant", "content": []}
                
                # Add text block if there's content
                if content:
                    last_assistant_content = {"type": "text", "text": content}
                    new_msg["content"].append(last_assistant_content)
                
                # Add tool_use blocks for each tool call
                for tool_call in msg.get("tool_calls", []):
                    if tool_call.get("type") == "function":
                        func = tool_call.get("function", {})
                        func_name = func.get("name", "")
                        tool_id = tool_call.get("id")
                        
                        # Parse arguments from string if needed
                        arguments = func.get("arguments", "{}")
                        if isinstance(arguments, str):
                            try:
                                tool_input = json.loads(arguments)
                            except:
                                tool_input = {"raw_input": arguments}
                        else:
                            tool_input = arguments
                        
                        # Create tool_use block
                        tool_use = {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": func_name,
                            "input": tool_input
                        }
                        new_msg["content"].append(tool_use)
                
                non_system_messages.append(new_msg)
            else:
                # Keep user and assistant messages as they are
                non_system_messages.append(msg)

        if get_caching_enabled() and last_assistant_content:
            last_assistant_content["cache_control"] = {"type": "ephemeral"}

        
        # Prepare API parameters, excluding None values
        api_params = {
            "model": model_name,
            "messages": non_system_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        # Format tools for Anthropic API
        if all_functions:
            # Format tools for Anthropic API
            anthropic_tools = format_tools(all_functions)
            
            # Only add tools if we have valid ones
            if anthropic_tools:
                api_params["tools"] = anthropic_tools

                # cache last tool (because this should be stable)
                if get_caching_enabled() and not last_assistant_content:
                    anthropic_tools[-1]["cache_control"] = {"type": "ephemeral"}
                
                # Let Claude decide when to use tools instead of forcing it
                api_params["tool_choice"] = {"type": "auto"}
            else:
                logger.warning("No valid tools to add to the request")
        
        # Only add parameters if they have valid values
        if system_messages:
            api_params["system"] = system_messages
            if get_caching_enabled() and not last_assistant_content:
                for msg in system_messages:
                    # do not cache if the first line contains "TODO.md"
                    if "TODO.md" not in msg["text"].split("\n")[0]:
                        msg["cache_control"] = {"type": "ephemeral"}
        if top_p is not None:
            api_params["top_p"] = top_p
        if top_k is not None and isinstance(top_k, int):
            api_params["top_k"] = top_k

        try:
            create_resp = await client.messages.create(**api_params)
            
            # Handle the case where content might be a list of TextBlock objects
            if create_resp.content:
                # Extract text properly from Anthropic response
                if isinstance(create_resp.content, list):
                    # If content is a list of blocks, extract text from each block
                    assistant_text = ""
                    for block in create_resp.content:
                        if hasattr(block, 'text'):
                            assistant_text += block.text
                        elif isinstance(block, dict) and 'text' in block:
                            assistant_text += block['text']
                        elif isinstance(block, str):
                            assistant_text += block
                else:
                    # If content is a single item
                    if hasattr(create_resp.content, 'text'):
                        assistant_text = create_resp.content.text
                    elif isinstance(create_resp.content, dict) and 'text' in create_resp.content:
                        assistant_text = create_resp.content['text']
                    else:
                        assistant_text = str(create_resp.content)
            else:
                assistant_text = ""
            
            # Check for tool calls in the response
            tool_calls = []
            if hasattr(create_resp, 'content') and create_resp.content:
                # Look for tool calls in content blocks
                content_blocks = create_resp.content if isinstance(create_resp.content, list) else [create_resp.content]
                for block in content_blocks:
                    if hasattr(block, 'type') and block.type == 'text':
                        assistant_text = block.text
                    
                    # Check if this is a tool use block
                    if hasattr(block, 'type') and block.type == 'tool_use':
                        # Get the tool name and input
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id
                        
                        # Generate a tool ID if one is not provided
                        if not tool_id:
                            tool_id = get_or_create_tool_id(tool_name)
                        
                        # Format as a function call for our system
                        tool_call = {
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_input) if isinstance(tool_input, dict) else tool_input
                            }
                        }
                        tool_calls.append(tool_call)
                        print(f"{assistant_text}")
            
            # Store the result to return after client is closed
            result = {"assistant_text": assistant_text, "tool_calls": tool_calls}

        except AnthropicAPIError as e:
            error_msg = str(e)
            logger.error(f"Anthropic API error: {error_msg}")
            result = {"assistant_text": f"Anthropic error: {error_msg}", "tool_calls": []}
            
        except Exception as e:
            import traceback
            logger.error(f"Unexpected error in Anthropic provider: {str(e)}")
            logger.error(traceback.format_exc())
            result = {"assistant_text": f"Unexpected Anthropic error: {str(e)}", "tool_calls": []}
    
    finally:
        # Always clean up the client
        if client:
            try:
                # First remove from active clients to prevent double cleanup
                _active_clients.discard(client)
                # Then close the client
                await client.close()
            except Exception as e:
                logger.error(f"Error closing Anthropic client: {e}")
    
    # Return result after everything is cleaned up
    return result
