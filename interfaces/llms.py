"""
LLM Interface Module

Provides a unified interface to various LLM providers.
Supports both direct API calls (built-in) and gateway-routed requests.

Architecture:
- LLM: Abstract base class
- Provider subclasses: GPT, Claude, Groq, Gemini, Grok
- GatewayLLM: Routes requests through the Glueco Gateway

This module has no knowledge of the game logic.
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from openai import OpenAI
import anthropic
from groq import Groq


# =============================================================================
# CONSTANTS
# =============================================================================

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROK_BASE_URL = "https://api.x.ai/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OLLAMA_BASE_URL = "http://localhost:11434/v1"


# =============================================================================
# GATEWAY HELPERS
# =============================================================================

def is_gateway_connected() -> bool:
    """Check if a gateway session is active and not expired."""
    try:
        import streamlit as st
        session = st.session_state.get("gateway_session")
        return session is not None and not session.is_expired()
    except Exception:
        return False


def get_gateway_client():
    """Get the GatewayClient from session state, if available."""
    try:
        import streamlit as st
        from glueco_sdk import GatewayClient
        session = st.session_state.get("gateway_session")
        if session and not session.is_expired():
            return GatewayClient.from_session(session)
    except Exception:
        pass
    return None


# =============================================================================
# BASE LLM CLASS
# =============================================================================

class LLM(ABC):
    """
    Abstract base class for LLM interfaces.
    
    Usage:
        llm = LLM.for_model_name("gpt-5-nano", temperature=0.7)
        response = llm.send(system_prompt, user_prompt, max_tokens)
    """
    
    model_names: List[str] = []
    model_name: str
    temperature: float
    client: Any
    
    def __init__(self, model_name: str, temperature: float = 1.0):
        self.model_name = model_name
        self.temperature = temperature
        self._setup_error: Optional[str] = None
        try:
            self.setup_client()
        except Exception as e:
            import logging
            logging.warning(f"Failed to setup {model_name}: {e}")
            self._setup_error = str(e)
            self.client = None
    
    @abstractmethod
    def setup_client(self) -> None:
        """Initialize the API client. Implemented by subclasses."""
        pass
    
    @abstractmethod
    def send(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        """
        Send a request to the LLM.
        
        Args:
            system_prompt: System-level instructions
            user_prompt: User message
            max_tokens: Maximum tokens in response
            
        Returns:
            The LLM's response text
        """
        pass
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.model_name} temp={self.temperature}>"
    
    # -------------------------------------------------------------------------
    # Class Methods for Model Resolution
    # -------------------------------------------------------------------------
    
    @classmethod
    def model_map(cls) -> Dict[str, Type["LLM"]]:
        """Map model names to their LLM subclasses."""
        mapping = {}
        for subclass in cls.__subclasses__():
            for name in subclass.model_names:
                mapping[name] = subclass
        return mapping
    
    @classmethod
    def for_model_name(cls, model_name: str, temperature: float = 0.7) -> "LLM":
        """
        Create an LLM instance for the given model name.
        
        Routes through gateway if connected and provider is available.
        Falls back to direct API otherwise.
        """
        import streamlit as st
        
        # Check gateway routing
        if is_gateway_connected():
            provider = cls._get_gateway_provider(model_name)
            if provider:
                return GatewayLLM(model_name, temperature, provider)
        
        # Fallback to direct API
        mapping = cls.model_map()
        if model_name not in mapping:
            raise KeyError(f"Model '{model_name}' not found. Available: {list(mapping.keys())}")
        
        return mapping[model_name](model_name, temperature)
    
    @classmethod
    def _get_gateway_provider(cls, model_name: str) -> Optional[str]:
        """
        Get the gateway provider for a model from the active session.
        
        Provider is extracted from the gateway session resources.
        The proxy exposes resources as 'llm:provider-name', so we use
        resource.provider directly - no hardcoding needed.
        """
        import streamlit as st
        
        session = st.session_state.get("gateway_session")
        if not session:
            return None
        
        # Search through all LLM resources for this model
        for resource in session.get_resources_by_type("llm"):
            # Check if model is in this resource's models list
            if model_name in getattr(resource, 'models', []):
                return resource.provider
        
        return None
    
    @classmethod
    def all_model_names(cls) -> List[str]:
        """Get all supported model names."""
        return list(cls.model_map().keys())
    
    @classmethod
    def available_model_names(cls) -> List[str]:
        """Get model names that have their API keys configured."""
        available = []
        for name, llm_class in cls.model_map().items():
            if llm_class.is_configured():
                available.append(name)
        return available
    
    @classmethod
    def is_configured(cls) -> bool:
        """Check if this LLM class has required API keys. Override in subclasses."""
        return True


# =============================================================================
# PROVIDER IMPLEMENTATIONS
# =============================================================================

class GPT(LLM):
    """OpenAI GPT models."""
    
    model_names = ["gpt-5-nano"]  # Only allowed model for built-in
    
    def setup_client(self) -> None:
        self.client = OpenAI()
    
    def send(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))


class Claude(LLM):
    """Anthropic Claude models."""
    
    model_names = ["claude-haiku-4-5"]  # Only allowed model for built-in
    
    def setup_client(self) -> None:
        self.client = anthropic.Anthropic()
    
    def send(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))


class GroqLLM(LLM):
    """Groq-hosted models (Llama, Mixtral, etc.)."""
    
    model_names = ["openai/gpt-oss-120b"]  # Only allowed model for built-in
    
    def setup_client(self) -> None:
        self.client = Groq()
    
    def send(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("GROQ_API_KEY"))


class Gemini(LLM):
    """Google Gemini models via OpenAI-compatible API."""
    
    model_names = ["gemini-2.5-flash-lite"]  # Only allowed model for built-in
    
    def setup_client(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
    
    def send(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


class Grok(LLM):
    """xAI Grok models."""
    
    model_names = ["grok-4-fast"]  # Only allowed model for built-in
    
    def setup_client(self) -> None:
        api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
        self.client = OpenAI(api_key=api_key, base_url=GROK_BASE_URL)
    
    def send(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY"))


# =============================================================================
# GATEWAY LLM
# =============================================================================

class GatewayLLM(LLM):
    """
    Routes LLM requests through the Glueco Gateway.
    
    Uses PoP-authenticated requests to the proxy, which forwards
    to the appropriate provider.
    
    IMPORTANT: The gateway client is captured at construction time because
    the send() method runs in ThreadPoolExecutor threads which don't have
    access to st.session_state.
    """
    
    model_names: List[str] = []  # Not in static model list
    provider: str
    _gateway_client: Any = None  # Captured at construction
    
    def __init__(self, model_name: str, temperature: float = 1.0, provider: str = "openai"):
        self.provider = provider
        # Capture the gateway client NOW from session state (main thread)
        self._gateway_client = get_gateway_client()
        super().__init__(model_name, temperature)
    
    def setup_client(self) -> None:
        # Client is captured in __init__
        pass
    
    def send(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        import logging
        
        if self._gateway_client is None:
            raise RuntimeError(
                f"Gateway not connected. Cannot use GatewayLLM for {self.model_name}. "
                "Please connect to a gateway first."
            )
        
        logging.info(f"[GatewayLLM] Making request to {self.provider}/{self.model_name} via {self._gateway_client.proxy_url}")
        
        try:
            response = self._gateway_client.chat_completion(
                provider=self.provider,
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            
            logging.info(f"[GatewayLLM] Got response successfully for {self.model_name}")
            return response.content
        except Exception as e:
            logging.error(f"[GatewayLLM] Request failed: {e}")
            raise
    
    def __repr__(self) -> str:
        return f"<GatewayLLM {self.model_name} via {self.provider} temp={self.temperature}>"
