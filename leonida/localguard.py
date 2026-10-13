"""Só o próprio computador conversa com os apps locais.

Bloqueia DNS rebinding (Host diferente de localhost) e CSRF (POST/PUT/PATCH/DELETE
vindos de outro site), para que uma página aberta no navegador não envie arquivos,
rode o radar ou altere posts pelo servidor local. Outros nomes de host podem ser
liberados em LEONIDA_ALLOWED_HOSTS (separados por vírgula).
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def allowed_hosts() -> set[str]:
    extra = os.environ.get("LEONIDA_ALLOWED_HOSTS", "")
    return set(LOCAL_HOSTS) | {h.strip().lower() for h in extra.split(",") if h.strip()}


def _hostname(netloc: str) -> str | None:
    try:
        return (urlsplit("//" + netloc).hostname or "").lower() or None
    except ValueError:
        return None


def rejection(method: str, headers: dict[str, str]) -> str | None:
    """Motivo da recusa, ou None quando a requisição veio do próprio app."""
    hosts = allowed_hosts()
    if _hostname(headers.get("host", "")) not in hosts:
        return "Host não permitido: abra o app por http://127.0.0.1"
    if method.upper() in UNSAFE_METHODS:
        origin = headers.get("origin")
        if origin is not None:
            try:
                parts = urlsplit(origin)
                ok = parts.scheme in ("http", "https") and (parts.hostname or "").lower() in hosts
            except ValueError:
                ok = False
            if not ok:
                return "Origem não permitida: só o próprio app pode alterar dados"
        elif headers.get("sec-fetch-site") in ("cross-site", "same-site"):
            return "Origem não permitida: só o próprio app pode alterar dados"
    return None


class LocalOnly:
    """Middleware ASGI; responde 403 antes de qualquer rota ou upload ser lido."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            reason = rejection(scope.get("method", "GET"), headers)
            if reason:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                body = json.dumps({"detail": reason}, ensure_ascii=False).encode("utf-8")
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def install(app) -> None:
    app.add_middleware(LocalOnly)
