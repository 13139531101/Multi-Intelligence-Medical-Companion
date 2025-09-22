"""
LMStudio provider implementation.
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Callable

import lmstudio as lms

logger = logging.getLogger("mcp_client")

async def generate_with_lmstudio(conversation: List[Dict], model_cfg: Dict, 
                               all_functions: List[Dict], stream: bool = False) -> Union[Dict, AsyncGenerator]:
    """
    Generate text using LMStudio's SDK.
    
    Args:
        conversation: The conversation history
        model_cfg: Configuration for the model
        all_functions: Available functions for the model to call
        stream: Whether to stream the response (not currently supported by LMStudio)
        
    Returns:
        Dict containing assistant_text and tool_calls
    """
    try:
        # Get model configuration
        model_name = model_cfg["model"]
        
        # Initialize the model
        model = lms.llm(model_name)
        
        # Extract system message if present
        system_message = ""
        for message in conversation:
            if message.get("role") == "system":
                system_message += message.get("content", "") + "\n"
        
        # Initialize chat with system message
        chat = lms.Chat(system_message.strip() if system_message else None)
        
        # Add conversation history to chat
        for message in conversation:
            role = message.get("role", "")
            content = message.get("content", "")
            
            if role == "user":
                chat.add_user_message(content)
            elif role == "assistant" and not message.get("tool_calls"):
                # Only add assistant messages without tool calls
                chat.add_assistant_response(content)
            # Skip system messages (already handled) and tool messages
        
        # Check if we have functions to use
        if all_functions:
            # Convert functions to callable Python functions
            tool_functions = _convert_functions_to_callables(all_functions)
            
            # Get the last user message for the prompt
            prompt = ""
            for message in reversed(conversation):
                if message.get("role") == "user":
                    prompt = message.get("content", "")
                    break
            
            # Create a new chat for capturing the response
            response_chat = lms.Chat()
            
            # Use model.act() for tool calling
            model.act(
                prompt,
                tool_functions,
                on_message=response_chat.append
            )
            
            # Extract tool calls from the response
            return _extract_tool_calls_from_response(str(response_chat))
        else:
            # Use model.respond() for regular chat
            response = model.respond(chat)
            
            # Add the response to the chat history
            chat.add_assistant_response(response)
            
            # Return the response without tool calls
            return {"assistant_text": response, "tool_calls": []}
        
    except Exception as e:
        logger.error(f"LMStudio error: {str(e)}")
        return {"assistant_text": f"LMStudio error: {str(e)}", "tool_calls": []}

def _convert_functions_to_callables(all_functions: List[Dict]) -> List:
    """
    Convert function definitions to callable Python functions for LMStudio.
    
    Args:
        all_functions: List of function definitions
        
    Returns:
        List of callable functions
    """
    def create_tool_function(name, description, params):
        """Create a tool function with the given name, description, and parameters."""
        def tool_function(*args, **kwargs):
            # Create a unique ID for this tool call
            call_id = f"call_{name}_{hash(str(kwargs))}"
            
            # Return a dictionary with the tool call information
            return {
                "id": call_id,
                "function": {
                    "name": name,
                    "arguments": json.dumps(kwargs)
                }
            }
        
        # Set function metadata for introspection
        tool_function.__name__ = name
        tool_function.__doc__ = description
        
        return tool_function
    
    # Create a tool function for each function definition
    tool_functions = []
    for func_def in all_functions:
        # Extract function details
        func_name = func_def.get("name", "unknown_function")
        func_description = func_def.get("description", "")
        func_params = func_def.get("parameters", {})
        
        # Create and add the tool function
        tool_function = create_tool_function(func_name, func_description, func_params)
        tool_functions.append(tool_function)
    
    return tool_functions

def _extract_tool_calls_from_response(response: Any) -> Dict:
    """
    Extract tool calls from the model's response.
    
    Args:
        response: The response from the model.act() call or Chat object
        
    Returns:
        Dict containing assistant_text and tool_calls
    """
    assistant_text = ""
    tool_calls = []
    
    # Convert to string if not already
    if not isinstance(response, str):
        response_str = str(response)
    else:
        response_str = response
    
    # Check if the response contains any tool calls
    # Tool calls might be embedded in the text as JSON objects
    try:
        # Look for JSON-like patterns in the response
        json_pattern = r'\{[^{}]*\}'
        potential_jsons = re.findall(json_pattern, response_str)
        
        for json_str in potential_jsons:
            try:
                # Try to parse as JSON
                json_obj = json.loads(json_str)
                
                # Check if this looks like a tool call
                if isinstance(json_obj, dict) and "function" in json_obj:
                    # This might be a tool call
                    if isinstance(json_obj["function"], dict) and "name" in json_obj["function"]:
                        # This is a tool call
                        tool_calls.append({
                            "id": json_obj.get("id", f"call_{len(tool_calls)}"),
                            "function": {
                                "name": json_obj["function"].get("name", "unknown_function"),
                                "arguments": json_obj["function"].get("arguments", "{}")
                            }
                        })
                        
                        # Remove the tool call from the response text
                        response_str = response_str.replace(json_str, "")
            except json.JSONDecodeError:
                # Not valid JSON, ignore
                pass
    except Exception as e:
        # If anything goes wrong, just use the response as is
        logger.warning(f"Error extracting tool calls: {str(e)}")
    
    # Use the remaining text as the assistant's response
    assistant_text = response_str.strip()
    
    # If we couldn't extract any tool calls but the response is a dictionary or list,
    # try to extract them directly
    if not tool_calls and not isinstance(response, str):
        if isinstance(response, dict):
            # Check if this is a tool call
            if "function" in response and "name" in response.get("function", {}):
                # This is a tool call
                tool_calls.append({
                    "id": response.get("id", "call_id"),
                    "function": {
                        "name": response["function"].get("name", "unknown_function"),
                        "arguments": response["function"].get("arguments", "{}")
                    }
                })
        elif isinstance(response, list):
            # Might be a list of responses or tool calls
            for item in response:
                if isinstance(item, dict) and "function" in item:
                    # This is a tool call
                    tool_calls.append({
                        "id": item.get("id", f"call_{len(tool_calls)}"),
                        "function": {
                            "name": item["function"].get("name", "unknown_function"),
                            "arguments": item["function"].get("arguments", "{}")
                        }
                    })
    
    return {"assistant_text": assistant_text, "tool_calls": tool_calls}
