#!/usr/bin/env python3
"""
AI Sysadmin OpenAI-Compatible API Server

Provides an OpenAI-compatible API that wraps the Meta Model with full
system administration capabilities. This is what external frontends
(like OpenWebUI, LibreChat, etc.) should connect to.

Port 8083 by default.
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union, Literal
import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

# Import AI Sysadmin components
from meta_model import MetaModel
from context_manager import ContextManager
from executor import SafeExecutor


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None


class OpenAIAPIServer:
    """OpenAI-compatible API server for AI Sysadmin"""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8083,
        meta_model: Optional[MetaModel] = None,
        context_manager: Optional[ContextManager] = None,
        executor: Optional[SafeExecutor] = None,
        autonomy_level: str = "suggest",
        require_auth: bool = False,
        api_key: Optional[str] = None
    ):
        self.app = FastAPI(
            title="AI Sysadmin API",
            description="OpenAI-compatible API with system administration capabilities",
            version="1.0.0"
        )
        self.host = host
        self.port = port
        self.meta_model = meta_model
        self.context_manager = context_manager
        self.executor = executor
        self.autonomy_level = autonomy_level
        self.require_auth = require_auth
        self.api_key = api_key
        
        # Conversation history tracking
        self.conversations: Dict[str, List[Message]] = {}
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/v1/models")
        async def list_models():
            """List available models"""
            return {
                "object": "list",
                "data": [
                    {
                        "id": "ai-sysadmin-meta",
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "ai-sysadmin"
                    }
                ]
            }
        
        @self.app.post("/v1/chat/completions")
        async def chat_completions(
            request: ChatCompletionRequest,
            authorization: Optional[str] = Header(None)
        ):
            """OpenAI-compatible chat completions endpoint"""
            
            # Authentication check
            if self.require_auth:
                if not authorization or not authorization.startswith("Bearer "):
                    raise HTTPException(status_code=401, detail="Missing or invalid authorization")
                token = authorization.replace("Bearer ", "")
                if token != self.api_key:
                    raise HTTPException(status_code=403, detail="Invalid API key")
            
            # Extract conversation
            messages = request.messages
            
            # Get current system context
            context = ""
            if self.context_manager:
                context = self.context_manager.get_current_context()
            
            # Build the full prompt with context
            user_message = messages[-1].content if messages else ""
            
            # Check if this is a tool-enabled request
            if request.tools:
                # Handle tool-based interaction
                return await self._handle_tool_request(request, user_message, context)
            else:
                # Standard chat interaction
                return await self._handle_chat_request(request, user_message, context)
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "autonomy_level": self.autonomy_level,
                "meta_model_available": self.meta_model is not None
            }
        
        @self.app.get("/v1/system/status")
        async def system_status():
            """Get current system status (custom endpoint)"""
            if not self.context_manager:
                return {"error": "Context manager not available"}
            
            return {
                "context": self.context_manager.get_current_context(),
                "autonomy_level": self.autonomy_level,
                "timestamp": datetime.now().isoformat()
            }
    
    async def _handle_chat_request(
        self,
        request: ChatCompletionRequest,
        user_message: str,
        context: str
    ) -> Union[ChatCompletionResponse, StreamingResponse]:
        """Handle standard chat request"""
        
        if not self.meta_model:
            raise HTTPException(status_code=503, detail="Meta model not available")
        
        # Get response from meta model
        try:
            response_text = self.meta_model.chat_with_user(user_message, context)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error generating response: {e}")
        
        # Format as OpenAI response
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        
        if request.stream:
            # Handle streaming
            async def generate_stream():
                # Split response into chunks for streaming
                words = response_text.split()
                for i, word in enumerate(words):
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": request.model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "content": word + " " if i < len(words) - 1 else word
                            },
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    await asyncio.sleep(0.01)
                
                # Final chunk
                final_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(generate_stream(), media_type="text/event-stream")
        else:
            # Non-streaming response
            return ChatCompletionResponse(
                id=completion_id,
                created=int(time.time()),
                model=request.model,
                choices=[{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    },
                    "finish_reason": "stop"
                }],
                usage={
                    "prompt_tokens": len(user_message.split()),
                    "completion_tokens": len(response_text.split()),
                    "total_tokens": len(user_message.split()) + len(response_text.split())
                }
            )
    
    async def _handle_tool_request(
        self,
        request: ChatCompletionRequest,
        user_message: str,
        context: str
    ) -> ChatCompletionResponse:
        """Handle tool-based request (function calling)"""
        
        if not self.meta_model or not self.executor:
            raise HTTPException(status_code=503, detail="Tools not available")
        
        # Define available tools
        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "Execute a shell command on the system",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute"
                            },
                            "justification": {
                                "type": "string",
                                "description": "Why this command is needed"
                            }
                        },
                        "required": ["command", "justification"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_service_status",
                    "description": "Check the status of a systemd service",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {
                                "type": "string",
                                "description": "Name of the systemd service"
                            }
                        },
                        "required": ["service_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "apply_nixos_config",
                    "description": "Apply NixOS configuration changes",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "config_changes": {
                                "type": "string",
                                "description": "Description of configuration changes"
                            },
                            "action": {
                                "type": "string",
                                "enum": ["switch", "boot", "test"],
                                "description": "nixos-rebuild action"
                            }
                        },
                        "required": ["config_changes", "action"]
                    }
                }
            }
        ]
        
        # For now, return a response indicating tool capabilities
        # Full tool integration would involve parsing the user's intent
        # and deciding which tool to call
        
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        
        # Analyze the request and determine if a tool should be called
        response_text = self.meta_model.chat_with_user(
            f"{user_message}\n\nAvailable tools: {json.dumps(available_tools, indent=2)}\n\nRespond with tool call if needed.",
            context
        )
        
        return ChatCompletionResponse(
            id=completion_id,
            created=int(time.time()),
            model=request.model,
            choices=[{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }]
        )
    
    def run(self):
        """Run the API server"""
        import uvicorn
        print(f"Starting AI Sysadmin OpenAI API on {self.host}:{self.port}")
        print(f"Autonomy level: {self.autonomy_level}")
        print(f"Connect OpenWebUI or other frontends to: http://{self.host}:{self.port}/v1")
        uvicorn.run(self.app, host=self.host, port=self.port)


async def run_server_async(server: OpenAIAPIServer):
    """Run server in async context"""
    import uvicorn
    config = uvicorn.Config(server.app, host=server.host, port=server.port)
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


if __name__ == "__main__":
    # Test server
    import sys
    
    print("AI Sysadmin OpenAI API Server")
    print("=" * 50)
    print("This server provides an OpenAI-compatible API")
    print("that wraps the Meta Model with system administration tools.")
    print()
    print("External frontends (OpenWebUI, LibreChat, etc.) should")
    print("connect to this server, NOT directly to llama.cpp.")
    print("=" * 50)
    
    # Create test server (without actual Meta Model for standalone testing)
    server = OpenAIAPIServer(
        host="0.0.0.0",
        port=8083,
        autonomy_level="suggest"
    )
    
    server.run()

