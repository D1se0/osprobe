"""Cliente HTTP asíncrono (aiohttp) para OSProbe.

Características:
    * Reutiliza la sesión aiohttp para todo el escaneo (keep-alive).
    * Timeout configurable por petición con cancelación por TaskGroup.
    * Soporta proxy HTTP/HTTPS (incluye ``socks5://`` si tienes
      ``aiohttp-socks`` instalado) y ``tor://`` transparente vía ``--proxy``.
    * Devuelve un snapshot inmutable (``ResponseSnap``) en vez del objeto
      aiohttp original, así los probes no dependedel ciclo de vida de la
      conexión.
"""

from __future__ import annotations

import asyncio
import sys
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional

import aiohttp

from .exceptions import NetworkError

DEFAULT_USER_AGENT = "OSProbe/1.0 (Case-Sensitivity Fingerprinter; +https://github.com/D1se0/osprobe)"


@dataclass(frozen=True)
class ResponseSnap:
    """Fotografía inmutable de la respuesta HTTP."""

    url: str
    status: int
    reason: str
    headers: Dict[str, str]
    body: str = ""
    elapsed: float = 0.0

    @property
    def is_not_found(self) -> bool:
        """¿El servidor respondió 404 (o variantes estándar de no existe)?"""
        return self.status in (404, 410)


@dataclass
class RequestSpec:
    """Petición que aún no se ha enviado."""

    url: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    follow_redirects: bool = False


class HttpClient:
    """Wrapper fino sobre aiohttp con reintentos y jitter."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 8.0,
        retries: int = 2,
        proxy: Optional[str] = None,
        delay: float = 0.0,
        verify: bool = True,
    ) -> None:
        self._ua = user_agent
        self._timeout = timeout
        self._retries = retries
        self._proxy = proxy
        self._delay = delay
        self._verify = verify
        self._session: Optional[aiohttp.ClientSession] = None
        self._sem = asyncio.Semaphore(8)

    async def __aenter__(self) -> "HttpClient":
        connector = aiohttp.TCPConnector(ssl=None if self._verify else False)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=self._timeout),
            trust_env=True,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------ #
    def _maybe_proxy(self, url: str) -> Optional[str]:
        """Devuelve el proxy para esquemas http/https, si hay."""
        if not self._proxy:
            return None
        return self._proxy

    async def path_exists(self, base_url: str, path: str, method: str = "GET") -> ResponseSnap:
        """Pide ``base_url + path`` y devuelve el snapshot de la respuesta."""
        request = RequestSpec(
            url=f"{base_url.rstrip('/')}/{path.lstrip('/')}",
            method=method,
        )
        return await self.send(request)

    async def send(self, spec: RequestSpec) -> ResponseSnap:
        """Envía una ``RequestSpec`` con reintentos exponenciales (2^n * 0.15s)."""
        if self._session is None:
            raise NetworkError("HttpClient no inicializado con async-with")
        import random
        import time

        headers = {"User-Agent": self._ua, "Accept": "*/*", **spec.headers}
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                if self._delay > 0 and attempt == 0:
                    # Rate limit amable: no quiero flamear el server del
                    # socio que me contrató a las 3AM.
                    await asyncio.sleep(random.uniform(0, self._delay))
                begin = time.monotonic()
                async with self._sem:
                    async with self._session.request(
                        spec.method,
                        spec.url,
                        headers=headers,
                        proxy=self._maybe_proxy(spec.url),
                        allow_redirects=spec.follow_redirects,
                        raise_for_status=False,
                    ) as resp:
                        # Leemos sólo una muestra del body: los 404 que
                        # buscamos caben en ~2KB y queremos fluidez.
                        raw = await resp.content.read(2048)
                        elapsed = time.monotonic() - begin
                        try:
                            text = raw.decode("utf-8", errors="replace")
                        except Exception:  # pragma: no cover - el decode nunca lanza
                            text = ""
                        headers_map = {k.lower(): v for k, v in resp.headers.items()}
                        return ResponseSnap(
                            url=str(resp.url),
                            status=resp.status,
                            reason=resp.reason or "",
                            headers=headers_map,
                            body=text,
                            elapsed=elapsed,
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt < self._retries:
                    await asyncio.sleep(min(1.5, 0.15 * (2**attempt)))
        raise NetworkError(f"Fallo de red contra {spec.url} -> {last_exc}") from last_exc


def normalize(url: str) -> str:
    """Normaliza rutas pidiendo a urlparse que arregle lo del usuario."""
    url = url.strip()
    if "://" not in url:
        url = "http://" + url
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


__all__ = ("HttpClient", "ResponseSnap", "RequestSpec", "normalize", "DEFAULT_USER_AGENT")
