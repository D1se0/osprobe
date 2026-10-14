"""Servidores simulados para proveer un banco de pruebas sin Windows real.

``make_fake_app(os_type)`` levanta una app aiohttp que se comporta
**exactamente igual** que un server de verdad para nuestros probes:

Simulación Linux:
    * Sistema de ficheros virtual sensible a mayúsculas/manúsculas:
      ``/images`` existe; ``/Images`` y ``/IMAGES`` devuelven 404.
    * ``Server: Apache/2.4.57 (Unix)`` y cuerpo 404 estilo Apache.
    * El backslash ``\\`` se trata como carácter de fichero (404).

Simulación Windows/IIS:
    * NTFS virtual: lookup case-insensitive (``/IMAGES`` resuelve igual).
    * ``Server: Microsoft-IIS/10.0``, ``X-AspNet-Version`` y mensaje
      404 nativo «The resource you are looking for has been removed».
    * El backslash se normaliza como separador (IIS lo acepta).

Estas simulaciones son las mismas que usan los tests; si un día un
probe "adivina" Linux de un IIS simulado, el CI explota — nunca más la
vergüenza de subir un detector que no detecta.
"""

from __future__ import annotations

import os
import random
import string
from typing import Dict, Optional

from aiohttp import web

#: Rutas "reales" del sitio simulado.
_VIRTUAL_FILES: Dict[str, str] = {
    "": "<html><head><title>Sim!</title></head><body>Welcome to the simulation.</body></html>",
    "images": "<html><body><h1>Gallery</h1><ul><li>a.png</li><li>b.png</li></ul></body></html>",
    "reports": "<html><body><h1>Quarterly Reports</h1></body></html>",
    "docs": "<html><body><h1>Docs index</h1></body></html>",
}

IIS_NOT_FOUND = (
    "<!DOCTYPE html><html><head><title>404 Not Found</title></head><body>"
    "<h1>HTTP Error 404. The resource you are looking for does not exist.</h1>"
    "</body></html>\r\n"
)
APACHE_NOT_FOUND = (
    "<!DOCTYPE HTML><html><head><title>404 Not Found</title></head><body>"
    "<h1>Not Found</h1><p>The requested URL was not found on this server.</p>"
    "<hr><address>Apache/2.4.57 (Unix) OpenSSL/1.1.1t Server at target.com Port 80</address>"
    "</body></html>\n"
)


def make_fake_app(os_type: str) -> web.Application:
    """Crea la app simulada del tipo ``'linux'`` o ``'windows'``."""

    async def index(request: web.Request) -> web.Response:
        return _response(request, os_type, "", 200)

    async def route(request: web.Request) -> web.Response:
        raw = request.match_info["path"]
        norm = raw.rstrip("/")
        if os_type == "windows":
            # IIS/Win32 trata '\\' como '/' y no distingue mayúsculas.
            norm = norm.replace("\\", "/").lower()
        else:
            # Linux: mantiene el backslash como carácter de ruta real.
            pass
        body = _VIRTUAL_FILES.get(norm)
        if body is None:
            return _response(request, os_type, raw, 404)
        return _response(request, os_type, norm, 200, content=body)

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/{path:.*}", route)
    return app


def _response(
    request: web.Request,
    os_type: str,
    path: str,
    status: int,
    content: Optional[str] = None,
) -> web.Response:
    headers = {}
    if os_type == "windows":
        headers["Server"] = "Microsoft-IIS/10.0"
        headers["X-Powered-By"] = "ASP.NET"
        headers["X-AspNet-Version"] = "4.0.30319"
        notfound = IIS_NOT_FOUND
    else:
        headers["Server"] = "Apache/2.4.57 (Unix)"
        notfound = APACHE_NOT_FOUND
    if status == 404:
        return web.Response(status=404, text=notfound, headers=headers, content_type="text/html")
    return web.Response(status=status, text=content or "", headers=headers, content_type="text/html")


async def start_fake_server(os_type: str) -> int:
    """Arranca el servidor simulado en un puerto libre; devuelve el puerto."""
    runner = web.AppRunner(make_fake_app(os_type))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    runner.app["__runner"] = runner  # para poder pararlo luego
    return port
