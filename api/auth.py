"""Token auth against the existing SQLite user DB (userstable / hashing.py).

POST /api/v1/token with username/password returns a signed bearer token.
Tokens are stateless HMAC tokens: base64(username|expiry) + signature.
Set SAR_API_SECRET for tokens that survive an API restart; otherwise a
random per-process secret is used.
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
_SECRET = os.getenv("SAR_API_SECRET") or secrets.token_hex(32)

_bearer = HTTPBearer(auto_error=False)


def _sign(payload: bytes) -> str:
    return hmac.new(_SECRET.encode(), payload, hashlib.sha256).hexdigest()


def create_token(username: str) -> dict:
    expiry = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{username}|{expiry}".encode()
    token = base64.urlsafe_b64encode(payload).decode() + "." + _sign(payload)
    return {"access_token": token, "token_type": "bearer", "expires_at": expiry}


def verify_credentials(username: str, password: str) -> bool:
    return bool(sql_stuff.login_user(username, password))


def require_admin(username: str) -> str:
    if sql_stuff.get_role(username) != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return username


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload_b64, signature = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(payload_b64.encode())
        username, expiry = payload.decode().rsplit("|", 1)
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed token")
    if not hmac.compare_digest(_sign(payload), signature):
        raise HTTPException(status_code=401, detail="Invalid token signature")
    if int(expiry) < time.time():
        raise HTTPException(status_code=401, detail="Token expired")
    return username
