"""Optional HTTP Basic Auth gate for public deployment."""

from __future__ import annotations

import os
import secrets
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


def auth_enabled() -> bool:
    return bool(os.getenv("AUTH_USERNAME", "").strip() and os.getenv("AUTH_PASSWORD", "").strip())


def _check(username: str, password: str) -> bool:
    expected_user = os.getenv("AUTH_USERNAME", "").strip()
    expected_pass = os.getenv("AUTH_PASSWORD", "").strip()
    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(
        password, expected_pass
    )


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Require HTTP Basic Auth when AUTH_USERNAME / AUTH_PASSWORD are set."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not auth_enabled():
            return await call_next(request)

        path = request.url.path
        if path in {"/health", "/favicon.ico"}:
            return await call_next(request)

        header = request.headers.get("Authorization", "")
        if header.startswith("Basic "):
            import base64

            try:
                raw = base64.b64decode(header[6:].encode("ascii")).decode("utf-8")
                username, _, password = raw.partition(":")
                if _check(username, password):
                    return await call_next(request)
            except Exception:  # noqa: BLE001
                pass

        return Response(
            content="Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="fund-holdings-viz"'},
            media_type="text/plain",
        )


def login_status() -> dict:
    return {"auth_enabled": auth_enabled()}
