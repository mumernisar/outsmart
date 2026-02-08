"""
Gateway connection UI components for Outsmart.

This module provides Streamlit UI components for:
1. Gateway connection in the sidebar
2. Session status display
3. Available resources display
"""

import streamlit as st
from typing import Optional, List
from datetime import datetime, timezone


def init_gateway_state():
    """Initialize gateway-related session state."""
    if "gateway_session" not in st.session_state:
        st.session_state.gateway_session = None
    if "gateway_pending" not in st.session_state:
        st.session_state.gateway_pending = None
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
    
    if status == "approved" and app_id:
        try:
            # Try to load pending state from disk (survives redirect)
            pending = _load_pending_state()
            
            if not pending:
                # No pending state - might be stale callback, just clear params
                st.query_params.clear()
                return
            
            # Import SDK
            from glueco_sdk import create_session, handle_callback, KeyPair
            
            callback = handle_callback(status, app_id, expires_at)
            
            if callback.approved:
                # Reconstruct KeyPair from saved dict
                keypair = KeyPair(
                    public_key=pending["keypair"]["public_key"],
                    private_key=pending["keypair"]["private_key"],
                )
                
                # Create full session with resource fetching
                session = create_session(
                    proxy_url=pending["proxy_url"],
                    app_id=callback.app_id,
                    keypair=keypair,
                    expires_at=callback.expires_at,
                    fetch_resources=True,
                )
                st.session_state.gateway_session = session
                st.session_state.gateway_pending = None
                st.session_state.gateway_error = None
                
                # Clear pending state file
                _clear_pending_state()
                
                # Clear URL params
                st.query_params.clear()
                
        except Exception as e:
            st.session_state.gateway_error = str(e)
            st.query_params.clear()
    
    elif status == "denied":
        st.session_state.gateway_error = "Connection was denied by the gateway owner."
        st.session_state.gateway_pending = None
        _clear_pending_state()
        st.query_params.clear()


def _get_pending_file_path():
    """Get path to pending state file."""
    import os
    return os.path.join(os.path.dirname(__file__), ".gateway_pending.json")


def _save_pending_state(pending: dict):
    """Save pending connection state to disk."""
    import json
    with open(_get_pending_file_path(), "w") as f:
        json.dump(pending, f)


def _load_pending_state():
    """Load pending connection state from disk."""
    import json
    import os
    path = _get_pending_file_path()
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def _clear_pending_state():
    """Clear pending state file."""
    import os
    path = _get_pending_file_path()
    if os.path.exists(path):
        os.remove(path)


def display_gateway_connection():
    """
    Display gateway connection UI in the sidebar.
    
    Shows:
    - Connection status
    - Pairing string input (if not connected)
    - Session info (if connected)
    - Disconnect button
    """
    init_gateway_state()
    
    st.markdown("### 🔐 Gateway Connection")
    
    session = st.session_state.gateway_session
    
    # Check if session is expired
    if session and session.is_expired():
        st.session_state.gateway_session = None
        session = None
    
    if session:
        # Connected state
        _display_connected_state(session)
    else:
        # Disconnected state
        _display_connect_form()


def _display_connected_state(session):
    """Display the connected session state."""
    remaining = session.time_remaining_formatted()
    
    st.success(f"🟢 Connected")
    st.caption(f"**Proxy:** {session.proxy_url}")
    st.caption(f"**Expires in:** {remaining}")
    
    # Show available resources
    llm_resources = session.get_resources_by_type("llm")
    if llm_resources:
        st.markdown("**Available LLMs:**")
        for resource in llm_resources:
            st.caption(f"• {resource.provider}")
    
    # Disconnect button
    if st.button("Disconnect", key="gateway_disconnect"):
        st.session_state.gateway_session = None
        st.rerun()


def _display_connect_form():
    """Display the connection form."""
    # Show any errors
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
        # Import SDK
        from glueco_sdk import (
            connect, AppInfo, PermissionRequest, RequestedDuration,
            parse_pairing_string,
        )
        
        # Parse to get proxy URL for discovery
        pairing_info = parse_pairing_string(pairing_string)
        
        # Request common LLM permissions with 1-hour duration
        duration = RequestedDuration(type="preset", value="1_hour")
        permissions = [
            PermissionRequest(
                resource_id="llm:openai",
                actions=["chat.completions"],
                requested_duration=duration,
            ),
            PermissionRequest(
                resource_id="llm:groq",
                actions=["chat.completions"],
                requested_duration=duration,
            ),
            PermissionRequest(
                resource_id="llm:gemini",
                actions=["chat.completions"],
                requested_duration=duration,
            ),
        ]
        
        # Get current URL for callback
        # Set APP_URL in Streamlit Cloud secrets for production
        # e.g., APP_URL = "https://your-app.streamlit.app"
        import os
        
        # Check Streamlit secrets first (for Streamlit Cloud), then env var
        app_url = None
        try:
            # Streamlit secrets accessed via dict-style or attribute
            if "APP_URL" in st.secrets:
                app_url = st.secrets["APP_URL"]
        except Exception:
            pass
        
        if not app_url:
            app_url = os.environ.get("APP_URL", "http://localhost:8501")
        
        callback_url = app_url.rstrip("/") + "/"
        
        # DEBUG: Show what URL we're using (visible to user)
        st.info(f"🔧 Debug: Using callback URL: {callback_url}")
        
        # Initiate connection
        result = connect(
            pairing_string=pairing_string,
            app=AppInfo(
                name="Outsmart Arena",
                description="LLM battle arena game",
            ),
            requested_permissions=permissions,
            redirect_uri=callback_url,
        )
        
        # Store pending connection (both session state AND disk for redirect survival)
        pending_data = {
            "proxy_url": result.proxy_url,
            "keypair": {
                "public_key": result.keypair.public_key,
                "private_key": result.keypair.private_key,
            },
        }
        st.session_state.gateway_pending = pending_data
        _save_pending_state(pending_data)  # Save to disk for redirect survival
        st.session_state.gateway_error = None
        
        # Redirect to approval URL
        st.markdown(
            f'<meta http-equiv="refresh" content="0;url={result.approval_url}">',
            unsafe_allow_html=True,
        )
        st.info("Redirecting to gateway for approval...")
        st.stop()
        
    except Exception as e:
        st.session_state.gateway_error = f"Connection failed: {e}"
        st.rerun()


def get_gateway_models() -> List[str]:
    """
    Get list of available models from gateway.
    
    Returns:
        List of model identifiers (e.g., "gateway:openai:gpt-4o")
    """
    session = st.session_state.get("gateway_session")
    if not session or session.is_expired():
        return []
    
    models = []
    for resource in session.get_resources_by_type("llm"):
        # Format: provider name for display
        models.append(f"Gateway: {resource.provider}")
    
    return models


def is_gateway_connected() -> bool:
    """Check if gateway is connected and valid."""
    session = st.session_state.get("gateway_session")
    return session is not None and not session.is_expired()


def get_gateway_client():
    """
    Get a GatewayClient from the current session.
    
    Returns:
        GatewayClient if connected, None otherwise
    """
    session = st.session_state.get("gateway_session")
    if not session or session.is_expired():
        return None
    
    from glueco_sdk import GatewayClient
    return GatewayClient.from_session(session)
