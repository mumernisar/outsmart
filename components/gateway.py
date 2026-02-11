"""
Gateway connection UI components for Outsmart.

Uses glueco-sdk v0.4.0 env-only design:
- GLUECO_PRIVATE_KEY env var for signing
- App saves only: app_id, proxy_url
"""

# Version for deployment verification
GATEWAY_VERSION = "4.1.0"

import streamlit as st
from typing import List
from datetime import datetime, timezone
import os


def init_gateway_state():
    """Initialize gateway-related session state."""
    if "gateway_app_id" not in st.session_state:
        st.session_state.gateway_app_id = None
    if "gateway_proxy_url" not in st.session_state:
        st.session_state.gateway_proxy_url = None
    if "gateway_expires_at" not in st.session_state:
        st.session_state.gateway_expires_at = None
    if "gateway_error" not in st.session_state:
        st.session_state.gateway_error = None


def handle_gateway_callback():
    """
    Handle the callback from gateway approval.
    
    Call this early in your app to process returning users.
    """
    params = st.query_params
    status = params.get("status")
    app_id = params.get("app_id")
    expires_at = params.get("expires_at")
    proxy_url = params.get("proxy_url")  # May be in query or session
    
    if status == "approved" and app_id:
        try:
            from glueco_sdk import handle_callback
            
            callback = handle_callback(status, app_id, expires_at)
            
            if callback["approved"]:
                st.session_state.gateway_app_id = callback["app_id"]
                st.session_state.gateway_expires_at = callback.get("expires_at")
                # Restore proxy_url from query params (session state is lost on redirect)
                if proxy_url:
                    st.session_state.gateway_proxy_url = proxy_url
                st.session_state.gateway_error = None
                
                # Clear URL params
                st.query_params.clear()
                
        except Exception as e:
            st.session_state.gateway_error = str(e)
            st.query_params.clear()
    
    elif status == "denied":
        st.session_state.gateway_error = "Connection was denied by the gateway owner."
        st.query_params.clear()


def display_gateway_connection():
    """
    Display gateway connection UI in the sidebar.
    """
    init_gateway_state()
    
    st.markdown("### 🔐 Gateway Connection")
    st.caption(f"v{GATEWAY_VERSION}")
    
    if is_gateway_connected():
        _display_connected_state()
    else:
        _display_connect_form()


def _display_connected_state():
    """Display the connected session state."""
    app_id = st.session_state.gateway_app_id
    proxy_url = st.session_state.gateway_proxy_url
    expires = st.session_state.gateway_expires_at
    
    remaining = "Unknown"
    if expires:
        now = datetime.now(timezone.utc)
        if isinstance(expires, datetime):
            delta = expires - now
            if delta.total_seconds() > 0:
                hours = int(delta.total_seconds() // 3600)
                minutes = int((delta.total_seconds() % 3600) // 60)
                remaining = f"{hours}h {minutes}m"
            else:
                remaining = "Expired"
    
    st.success("🟢 Connected")
    st.caption(f"**Proxy:** {proxy_url}")
    st.caption(f"**Expires in:** {remaining}")
    
    if st.button("Disconnect", key="gateway_disconnect"):
        st.session_state.gateway_app_id = None
        st.session_state.gateway_proxy_url = None
        st.session_state.gateway_expires_at = None
        st.rerun()


def _display_connect_form():
    """Display the connection form."""
    # Check env key first
    if not os.environ.get("GLUECO_PRIVATE_KEY"):
        st.warning("⚠️ GLUECO_PRIVATE_KEY not set in environment")
        st.caption("Add it to Streamlit secrets or .env file")
    
    if st.session_state.gateway_error:
        st.error(st.session_state.gateway_error)
    
    pairing = st.text_area(
        "Pairing String",
        placeholder="pair::https://gateway.example.com::abc123...",
        height=80,
        key="gateway_pairing_input",
    )
    
    if st.button("Connect to Gateway", key="gateway_connect"):
        if not pairing.strip():
            st.session_state.gateway_error = "Please enter a pairing string"
            st.rerun()
            return
        
        _initiate_connection(pairing.strip())


def _initiate_connection(pairing_string: str):
    """Initiate the connection flow."""
    try:
        from glueco_sdk import connect, parse_pairing_string
        
        # Parse to get proxy URL
        pairing_info = parse_pairing_string(pairing_string)
        
        # Save proxy_url now (needed after callback)
        st.session_state.gateway_proxy_url = pairing_info.proxy_url
        
        # Request LLM permissions
        duration = {"type": "preset", "value": "1_hour"}
        permissions = [
            {
                "resource_id": "llm:openai",
                "actions": ["chat.completions"],
                "requested_duration": duration,
            },
            {
                "resource_id": "llm:groq",
                "actions": ["chat.completions"],
                "requested_duration": duration,
            },
            {
                "resource_id": "llm:gemini",
                "actions": ["chat.completions"],
                "requested_duration": duration,
            },
            {
                "resource_id": "llm:anthropic",
                "actions": ["chat.completions"],
                "requested_duration": duration,
            },
        ]
        
        # Get callback URL
        app_url = None
        try:
            app_url = st.secrets.get("APP_URL")
        except Exception:
            pass
        
        if not app_url:
            app_url = os.environ.get("APP_URL", "http://localhost:8501")
        
        # Include proxy_url in callback so it survives the redirect
        from urllib.parse import urlencode
        callback_url = app_url.rstrip("/") + "/?" + urlencode({"proxy_url": pairing_info.proxy_url})
        
        # Connect (SDK reads env key, sends public_key to proxy)
        result = connect(
            pairing_string=pairing_string,
            app_name="Outsmart Arena",
            requested_permissions=permissions,
            redirect_uri=callback_url,
            app_description="LLM battle arena game",
        )
        
        st.session_state.gateway_error = None
        
        # Show approval link
        approval_url = result["approval_url"]
        st.success("✅ Connection prepared! Click below to approve:")
        st.link_button("🔐 Go to Gateway Approval", approval_url, use_container_width=True)
        st.caption(f"URL: {approval_url}")
        st.stop()
        
    except Exception as e:
        st.session_state.gateway_error = f"Connection failed: {e}"
        st.rerun()


def get_gateway_models() -> List[str]:
    """Get list of available models from gateway."""
    if not is_gateway_connected():
        return []
    return [
        "Gateway: openai",
        "Gateway: groq",
        "Gateway: gemini",
        "Gateway: anthropic",
    ]


def is_gateway_connected() -> bool:
    """Check if gateway is connected and valid."""
    app_id = st.session_state.get("gateway_app_id")
    proxy_url = st.session_state.get("gateway_proxy_url")
    expires = st.session_state.get("gateway_expires_at")
    
    if not app_id or not proxy_url:
        return False
    
    if expires:
        now = datetime.now(timezone.utc)
        if isinstance(expires, datetime) and expires < now:
            return False
    
    return True


def get_gateway_transport():
    """
    Get a GatewayTransport from session state.
    
    Returns:
        GatewayTransport if connected, None otherwise
    """
    if not is_gateway_connected():
        return None
    
    from glueco_sdk import create_transport
    
    return create_transport(
        proxy_url=st.session_state.gateway_proxy_url,
        app_id=st.session_state.gateway_app_id,
    )


def get_llm_client():
    """
    Get an LLMClient from the current session.
    
    Returns:
        LLMClient if connected, None otherwise
    """
    transport = get_gateway_transport()
    if not transport:
        return None
    
    from glueco_plugin_llm import llm_client
    return llm_client(transport)
