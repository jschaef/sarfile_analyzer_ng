"""Token auth against the existing SQLite user DB (userstable / hashing.py).

POST /api/v1/token with username/password returns a signed bearer token.
Tokens are stateless HMAC tokens: base64(username|expiry|purpose[|nonce])
plus a signature. Set SAR_API_SECRET for tokens that survive an API restart;
otherwise a random per-process secret is used.

Two purposes exist:
- 'api'  regular bearer for all data endpoints (default; tokens without a
         purpose field are treated as 'api' for backward compatibility)
- 'ui'   short-lived, single-use token handed to a browser in an SSO redirect
         URL. Only /sso/validate accepts it, never a data endpoint.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import bootstrap  # noqa: F401

import sql_stuff

TOKEN_TTL_SECONDS = int(os.getenv("SAR_API_TOKEN_TTL", 24 * 3600))
UI_TOKEN_TTL_SECONDS = int(os.getenv("SAR_SSO_UI_TTL", 180))
_SECRET = os.getenv("SAR_API_SECRET") or secrets.token_hex(32)

_bearer = HTTPBearer(auto_error=False)

# Fallback store for single-use UI tokens when Redis is unavailable. Redis is
# preferred so the guarantee also holds across API restarts / workers.
_used_ui_tokens: set[str] = set()


def _sign(payload: bytes) -> str:
    return hmac.new(_SECRET.encode(), payload, hashlib.sha256).hexdigest()


def create_token(
    username: str, purpose: str = "api", ttl: int | None = None
) -> dict:
    """Issue a signed bearer token. UI tokens get a nonce so each one is unique."""
    if ttl is None:
        ttl = UI_TOKEN_TTL_SECONDS if purpose == "ui" else TOKEN_TTL_SECONDS
    expiry = int(time.time()) + ttl
    fields = [username, str(expiry), purpose]
    if purpose == "ui":
        fields.append(secrets.token_urlsafe(12))
    payload = "|".join(fields).encode()
    token = base64.urlsafe_b64encode(payload).decode() + "." + _sign(payload)
    return {"access_token": token, "token_type": "bearer", "expires_at": expiry}


def _decode(token: str) -> tuple[str, str, str]:
    """Verify signature/expiry and return (username, purpose, nonce)."""
    try:
        payload_b64, signature = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(payload_b64.encode())
        fields = payload.decode().split("|")
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed token")
    if not hmac.compare_digest(_sign(payload), signature):
        raise HTTPException(status_code=401, detail="Invalid token signature")
    if len(fields) < 2:
        raise HTTPException(status_code=401, detail="Malformed token")
    username, expiry = fields[0], fields[1]
    purpose = fields[2] if len(fields) > 2 else "api"
    nonce = fields[3] if len(fields) > 3 else ""
    try:
        expired = int(expiry) < time.time()
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed token")
    if expired:
        raise HTTPException(status_code=401, detail="Token expired")
    return username, purpose, nonce


def verify_credentials(username: str, password: str) -> bool:
    return bool(sql_stuff.login_user(username, password))


def require_admin(username: str) -> str:
    if sql_stuff.get_role(username) != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return username


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Auth dependency for all data endpoints: requires an 'api' token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username, purpose, _ = _decode(credentials.credentials)
    if purpose != "api":
        raise HTTPException(
            status_code=401, detail="This token is not valid for API access"
        )
    return username


def consume_ui_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Auth dependency for /sso/validate: requires a single-use 'ui' token."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    username, purpose, nonce = _decode(credentials.credentials)
    if purpose != "ui":
        raise HTTPException(status_code=401, detail="Not an SSO UI token")
    if not _claim_ui_token(nonce or credentials.credentials):
        raise HTTPException(status_code=401, detail="SSO token already used")
    return username


def _claim_ui_token(jti: str) -> bool:
    """Atomically mark a UI token as used; False if it was used before."""
    try:
        import redis_mng

        connection = redis_mng.get_redis_conn()
        if connection:
            return bool(
                connection.set(
                    f"sar:sso:ui:{jti}", "1", nx=True, ex=UI_TOKEN_TTL_SECONDS + 60
                )
            )
    except Exception:
        pass
    if jti in _used_ui_tokens:
        return False
    _used_ui_tokens.add(jti)
    return True
