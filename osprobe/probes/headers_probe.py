"""Probe de cabeceras HTTP con huellas de sistema operativo.

Se examina cada cabecera de respuesta del origen contra una tabla de
firmas con pesos. Un mismo indicador no cuenta lo mismo si aparece en
``Server`` que en ``X-Powered-By``: los proxies pueden añadir la suya.

Firmas destacadas:
    *Microsoft-IIS*, *ASP.NET*, *Azure*             -> Windows con confianza;
    *Apache*, *nginx*, *OpenBSD httpd*, *PHP*      -> tipicamente Linux;
    *X-AspNet-Version*                -> Windows (IIS lo inyecta por defecto).
"""

from __future__ import annotations

from typing import Dict, Tuple

from ..http_client import RequestSpec
from ..models import OSType, ProbeCertainty
from .base import Probe, ProbeContext

# Cabecera -> (diccionario de patrones -> (tú tslader OS, peso))
_SIGNATURES: Dict[str, Tuple[str, float]] = {
    "microsoft-iis": (OSType.WINDOWS, 1.0),
    "x-aspnet-version": (OSType.WINDOWS, 1.0),
    "x-powered-by: asp.net": (OSType.WINDOWS, 0.9),
    "x-aspnetmvc-version": (OSType.WINDOWS, 0.9),
    "x-recursive": (OSType.WINDOWS, 0.3),  # huellas de Azure CDN
    "windows-azure": (OSType.WINDOWS, 0.8),
    "frontpage": (OSType.WINDOWS, 0.9),
    "apache": (OSType.LINUX, 0.7),  # Apache también existe en Windows, menos común
    "nginx": (OSType.LINUX, 0.55),
    "litespeed": (OSType.LINUX, 0.6),
    "openresty": (OSType.LINUX, 0.5),
    "unix": (OSType.LINUX, 0.6),
    "php": (OSType.LINUX, 0.35),  # PHP también corre en Windows, peso menor
    "express": (OSType.LINUX, 0.45),
}

# Patrones que conviene buscar en el value de una cabecera, key+«: »+value.
_Windows_STRONG = ("microsoft-iis", "asp.net", "x-aspnet-version")


class HeadersProbe(Probe):
    """Lee las cabeceras del servidor y vota con pesos por firma."""

    name = "header-signatures"
    weight = 25.0
    description = (
        "Inspecciona Server, X-Powered-By, X-AspNetVersion y otras cabeceras "
        "contra ~14 firmas ponderadas (IIS/ASP.NET => Windows; Apache/nginx "
        "Unix-y PHP => Linux)."
    )

    async def run(self, ctx) -> "ProbeResult":  # type: ignore[name-defined]
        import time as _time

        result = self.make_result()
        try:
            snap = await ctx.client.send(RequestSpec(url=ctx.target.origin, method="GET"))
            if snap.headers:
                for header, value in snap.headers.items():
                    needle_low = f"{header}: {value}".lower()
                    for pattern, (os_vote, weight) in _SIGNATURES.items():
                        if pattern in needle_low:
                            result.votes[os_vote] = result.votes.get(os_vote, 0.0) + weight
                            result.evidence.append(f"{header}: {value} ↔ patrón {pattern!r} (+{weight:.2f} a {os_vote.value})")
            result.evidence.sort(key=len, reverse=True)
            if not result.votes:
                result.certainty = ProbeCertainty.SUSPICION
                result.evidence.append("[sig] No hay cabeceras con firma reconocible; el servidor está muy limpio.")
                return self._elapsed(_time.monotonic(), result)

            if result.votes:
                # Normalización: re-escala al intervalo [0,1] por clase.
                total_std = sum(result.votes.values())
                if total_std > 1:
                    dominant_total = max(result.votes, key=lambda k: result.votes[k])
                    result.votes = {dominant_total: 1.0}
                    result.certainty = ProbeCertainty.CONFIRMED
                else:
                    result.certainty = ProbeCertainty.SUSPICION
            return self._elapsed(_time.monotonic(), result)
        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"
            return self._elapsed(_time.monotonic(), result)
