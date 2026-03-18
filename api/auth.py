from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from jose import JWTError, jwt

from api.config import Settings

logger = logging.getLogger(__name__)


def get_current_user_id(request: Request) -> str:
    """Extract and validate user_id from Supabase JWT in Authorization header."""
    settings = Settings()
    if not settings.jwt_secret:
        raise HTTPException(status_code=503, detail="Auth not configured (JWT_SECRET missing).")

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no subject.")
        return user_id
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
