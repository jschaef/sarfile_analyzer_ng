"""SSO auto-login for the Streamlit UI.

The support platform redirects a browser to
``https://<analyzer>/?sso_token=<token>[&file=<name>]``. This module validates
that token against the local REST API (the API stays the single token
authority - the UI holds no secret) and logs the user in.

The classic username/password form is untouched: without an sso_token nothing
here changes the flow.
"""

import os

import streamlit as st

API_URL = os.getenv("SAR_API_URL", "http://127.0.0.1:8100").rstrip("/")
API_PREFIX = "/api/v1"


def _validate(token: str) -> dict | None:
    """Ask the API who this UI token belongs to (consumes the token)."""
    try:
        import httpx

        response = httpx.get(
            f"{API_URL}{API_PREFIX}/sso/validate",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except Exception as exc:  # API down / not reachable
        st.error(f"SSO login failed: analyzer API not reachable ({exc})")
        return None
    if response.status_code == 200:
        return response.json()
    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text
    st.error(f"SSO login failed: {detail}")
    return None


def handle_sso_login() -> None:
    """Consume ?sso_token= from the URL and log the user in.

    Safe to call on every rerun: it only acts when a token is present and
    nobody is logged in yet.
    """
    token = st.query_params.get("sso_token")
    if not token or st.session_state.get("username"):
        return

    requested_file = st.query_params.get("file")
    # Drop the token from the URL before doing anything else, so a reload or a
    # shared link cannot replay it (it is single-use server side anyway).
    st.query_params.clear()

    identity = _validate(token)
    if not identity:
        return

    username = identity["username"]
    st.session_state["username"] = username
    st.session_state["auth_via_sso"] = True

    # Jump straight into the analysis view, optionally on the uploaded file.
    st.session_state["nav_top"] = "Analyze Data"
    if requested_file:
        preselect_sar_file(username, requested_file)
    st.rerun()


def preselect_sar_file(username: str, file_name: str) -> None:
    """Preselect a SAR file in the analyze view's file selectbox.

    Streamlit picks up a widget's value from session_state under its key, so
    seeding 'get_sarfiles' before the widget renders selects the file. Only
    done when the file really exists for that user, otherwise Streamlit would
    raise on a value that is not in the option list.
    """
    from config import Config

    base = f"{Config.upload_dir}/{username}"
    candidates = {file_name, f"{file_name}.parquet"}
    try:
        available = set(os.listdir(base))
    except OSError:
        return
    if candidates & available:
        st.session_state["get_sarfiles"] = file_name.removesuffix(".parquet")
