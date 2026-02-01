#!/usr/bin/env python3
"""
LLM Backend Abstraction Layer

Provides a unified interface for different LLM backends:
- LlamaCppBackend: For llama.cpp OpenAI-compatible API
- OllamaBackend: For legacy Ollama support
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import requests
from openai import OpenAI


class LLMBackend(ABC):
    """Abstract base class for LLM backends"""
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        **kwargs
    ) -> str:
        pass

    @abstractmethod
    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        **kwargs
    ) -> str:
        """
        Generate text from chat messages
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is available and responding"""
        pass


class LlamaCppBackend(LLMBackend):
    """Backend for llama.cpp with OpenAI-compatible API"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:40082/v1"):
        """
        Initialize llama.cpp backend
        
        Args:
            base_url: Base URL for llama.cpp API (should end with /v1)
                     Default uses localhost for security - internal services
                     should not be exposed externally.
        """
        self.base_url = base_url
        # OpenAI client configured for llama.cpp
        self.client = OpenAI(
            base_url=base_url,
            api_key="not-needed"  # llama.cpp doesn't require a key
        )
    
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        **kwargs
    ) -> str:
        """Generate text using llama.cpp"""
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=model or "local-model",  # llama.cpp often uses "local-model"
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs
            )
            
            if stream:
                # Handle streaming response
                full_response = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                return full_response
            else:
                return response.choices[0].message.content
        
        except Exception as e:
            print(f"Error generating from llama.cpp: {e}")
            return f"Error: {e}"

    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        **kwargs
    ) -> str:
        """Generate text using llama.cpp chat API"""
        try:
            response = self.client.chat.completions.create(
                model=model or "local-model",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs
            )
            
            if stream:
                full_response = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                return full_response
            else:
                return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating chat from llama.cpp: {e}")
            return f"Error: {e}"
    
    def is_available(self) -> bool:
        """Check if llama.cpp is responding"""
        try:
            # Try to list models
            response = requests.get(
                f"{self.base_url}/models",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False


class OllamaBackend(LLMBackend):
    """Legacy backend for Ollama"""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        """
        Initialize Ollama backend
        
        Args:
            base_url: Base URL for Ollama API
        """
        self.base_url = base_url
    
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        **kwargs
    ) -> str:
        """Generate text using Ollama"""
        
        # Ollama uses a different API format
        payload = {
            "model": model or "qwen3:14b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                **kwargs
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                return f"Error: HTTP {response.status_code}"
        
        except Exception as e:
            print(f"Error generating from Ollama: {e}")
            return f"Error: {e}"

    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        **kwargs
    ) -> str:
        """Generate text using Ollama chat API"""
        payload = {
            "model": model or "qwen3:14b",
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                **kwargs
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("message", {}).get("content", "")
            else:
                return f"Error: HTTP {response.status_code}"
        except Exception as e:
            print(f"Error generating chat from Ollama: {e}")
            return f"Error: {e}"
    
    def is_available(self) -> bool:
        """Check if Ollama is responding"""
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False


def create_backend(backend_type: str = "llama-cpp", **config) -> LLMBackend:
    """
    Factory function to create the appropriate backend
    
    Args:
        backend_type: "llama-cpp" or "ollama"
        **config: Backend-specific configuration
    
    Returns:
        Configured LLM backend
    """
    if backend_type == "llama-cpp":
        base_url = config.get("base_url", "http://localhost:40082/v1")
        return LlamaCppBackend(base_url=base_url)
    elif backend_type == "ollama":
        base_url = config.get("base_url", "http://localhost:11434")
        return OllamaBackend(base_url=base_url)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")


if __name__ == "__main__":
    # Test the backends
    print("Testing LLM Backend Abstraction")
    
    # Test llama.cpp backend
    print("\n1. Testing llama.cpp backend...")
    llama_backend = LlamaCppBackend("http://localhost:40082/v1")
    
    if llama_backend.is_available():
        print("✓ llama.cpp is available")
        response = llama_backend.generate("Say hello!", temperature=0.3, max_tokens=50)
        print(f"Response: {response}")
    else:
        print("✗ llama.cpp is not available")
    
    # Test Ollama backend (legacy)
    print("\n2. Testing Ollama backend...")
    ollama_backend = OllamaBackend("http://localhost:11434")
    
    if ollama_backend.is_available():
        print("✓ Ollama is available")
        response = ollama_backend.generate("Say hello!", model="qwen3:14b", temperature=0.3, max_tokens=50)
        print(f"Response: {response}")
    else:
        print("✗ Ollama is not available")

