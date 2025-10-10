#!/usr/bin/env python3
"""
Ollama Queue Worker - Daemon that processes queued Ollama requests
"""

import sys
import requests
from pathlib import Path
from ollama_queue import OllamaQueue

class OllamaClient:
    """Simple Ollama API client for the queue worker"""
    
    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host
    
    def generate(self, payload: dict) -> dict:
        """Call /api/generate"""
        response = requests.post(
            f"{self.host}/api/generate",
            json=payload,
            timeout=payload.get("timeout", 300),
            stream=False
        )
        response.raise_for_status()
        return response.json()
    
    def chat(self, payload: dict) -> dict:
        """Call /api/chat"""
        response = requests.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=payload.get("timeout", 300),
            stream=False
        )
        response.raise_for_status()
        return response.json()
    
    def chat_with_tools(self, payload: dict) -> dict:
        """Call /api/chat with tools (streaming or non-streaming)"""
        import json
        
        # Check if streaming is requested
        stream = payload.get("stream", False)
        
        response = requests.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=payload.get("timeout", 300),
            stream=stream
        )
        response.raise_for_status()
        
        if not stream:
            # Non-streaming: return response directly
            return response.json()
        
        # Streaming: accumulate response
        full_response = {"message": {"role": "assistant", "content": "", "tool_calls": []}}
        
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                
                if "message" in chunk:
                    msg = chunk["message"]
                    # Preserve role from first chunk
                    if "role" in msg and not full_response["message"].get("role"):
                        full_response["message"]["role"] = msg["role"]
                    if "content" in msg:
                        full_response["message"]["content"] += msg["content"]
                    if "tool_calls" in msg:
                        full_response["message"]["tool_calls"].extend(msg["tool_calls"])
                
                if chunk.get("done"):
                    full_response["done"] = True
                    # Copy any additional fields from final chunk
                    for key in chunk:
                        if key not in ("message", "done"):
                            full_response[key] = chunk[key]
                    break
        
        # Ensure role is set
        if "role" not in full_response["message"]:
            full_response["message"]["role"] = "assistant"
        
        return full_response

def main():
    """Main entry point for the worker"""
    print("Starting Ollama Queue Worker...")
    
    # Initialize queue and client
    queue = OllamaQueue()
    client = OllamaClient()
    
    # Cleanup old requests on startup
    queue.cleanup_old_requests(max_age_seconds=3600)
    
    # Start processing
    try:
        queue.start_worker(client)
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        queue.running = False
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

