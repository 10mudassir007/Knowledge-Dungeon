"""Vercel serverless entry point for the Knowledge Dungeon FastAPI app.

Vercel routes /api/* to this function. The frontend proxies /api/* to the
backend with the prefix stripped (see frontend/vite.config.ts), so this
wrapper removes /api from the ASGI path before handing the request to
FastAPI, whose routes live at /game/* and /health.

Static frontend assets are served by Vercel's static build; this function
only handles the dynamic API.
"""

from mangum import Mangum
from main import app


class _NoApiPrefixMiddleware:
    """Strip the /api prefix so FastAPI route matching works unchanged."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/api"):
                scope["path"] = path[4:] or "/"
                raw = scope.get("raw_path", b"")
                if raw.startswith(b"/api"):
                    scope["raw_path"] = raw[4:] or b"/"
        await self.app(scope, receive, send)


class _DebugPathMiddleware:
    """TEMP: echo the ASGI path the function actually receives."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and "__debug__" in scope.get("path", ""):
            body = (
                f"path={scope.get('path')!r} raw={scope.get('raw_path')!r} "
                f"qs={scope.get('query_string')!r}"
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"text/plain")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


handler = Mangum(_DebugPathMiddleware(_NoApiPrefixMiddleware(app)))
