"""
UI Components for Outsmart.
"""

from .gateway import (
    display_gateway_connection,
    handle_gateway_callback,
    init_gateway_state,
    get_gateway_models,
    is_gateway_connected,
    get_gateway_client,
)

__all__ = [
    "display_gateway_connection",
    "handle_gateway_callback",
    "init_gateway_state",
    "get_gateway_models",
    "is_gateway_connected",
    "get_gateway_client",
]
