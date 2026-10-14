"""Probe de huella de la página 404.

Cada servidor web tiene su manera de decir «esto no existe». La página
de error 404 es un mapa del stack: IIS/ASP.NET presentan un HTML
característico con textos tipo *«The resource you are looking for has
been removed»* o el clásico *«Server Error in '/' Application»*, junto
a cabeceras muy delatoras (``X-Powered-By: ASP.NET``, ETags IIS), y
mientras tanto Apache esconde frases como *«Not Found»«Apache»* o un
«Additionally, a 404 error was encountered» del handler.

Pero ojo, el 404 breve de nginx no dice el OS del *host* — sólo que
nginx corre ahí — de ahí el peso bajo de sus firmas.
"""

from __future__ import annotations

from ..models import OSType, ProbeCertainty
from .base import Probe, ProbeContext

# Agente (firma de cuerpo de 404) -> (OS, peso, descripción para el informe)
_BODY_SIGNATURES = {
    "the resource you are looking for": (OSType.WINDOWS, 0.9, "Mensaje 404 nativo de IIS"),
    "server error in '/' application": (OSType.WINDOWS, 1.0, "Página de error ASP.NET amarilla"),
    "httperror": (OSType.WINDOWS, 0.5, "Word HttpError de frameworks Microsoft"),
    "runtime error": (OSType.WINDOWS, 0.55, "Página runtime ASP.NET"),
    "a 404 error was encountered": (OSType.LINUX, 0.6, "Handler de error tipo Apache/CPython"),
    "apache": (OSType.LINUX, 0.5, "Firma de Apache en la 404"),
    "nginx": (OSType.LINUX, 0.45, "404 de nginx (evidencia débil del host)"),
}

_HEADER_SIGNATURES = {
    "microsoft-iis": (OSType.WINDOWS, 0.9),
    "x-aspnet-version": (OSType.WINDOWS, 1.0),
    "x-powered-by: asp.net": (OSType.WINDOWS, 0.8),
}


class NotFoundFingerprintProbe(Probe):
    """Firmas del cuerpo 404 que delatan el stack del servidor."""

    name = "finger-404"
    weight = 15.0
    description = (
        "Solicita una ruta inexistente aleatoria y hace fingerprint del "
        "cuerpo/cabeceras de respuesta 404 (mensajes nativos de IIS, "
        "ASP.NET, Apache, nginx...)."
    )

    async def run(self, ctx) -> "ProbeResult":  # type: ignore[name-defined]
        import time as _time

        result = self.make_result()
        try:
            # Tres peticiones a rutas al azar: reduce el ruido de una
            # 404 custom que el admin definió a mano.
            totals = {OSType.LINUX: 0.0, OSType.WINDOWS: 0.0}
            hits = 0
            for _ in range(3):
                ghost = ctx.random_notfound_path()
                await self._sleep_jitter(ctx)
                snap = await ctx.client.path_exists(ctx.target.origin, ghost)
                result.evidence.append(f"/{ghost} -> HTTP {snap.status}")
                if snap.status >= 400:
                    hits += 1
                blob = snap.body.lower()
                headers_blob = " ".join(f"{k}: {v}" for k, v in snap.headers.items()).lower()
                combined = blob + "\n" + headers_blob
                for needle, (os_vote, weight, why) in _BODY_SIGNATURES.items():
                    if needle in combined:
                        totals[os_vote] += weight
                        result.evidence.append(f"Huella 404 ⇒ {why!r} (+{weight:.2f} a {os_vote.value})")
                for needle, (os_vote, weight) in _HEADER_SIGNATURES.items():
                    if needle in headers_blob:
                        totals[os_vote] += weight
                        result.evidence.append(f"Cabecera 404 ⇒ {needle!r} (+{weight:.2f} a {os_vote.value})")

            if hits == 0:
                result.error = "El objetivo responde 2xx a TODO; no hay 404 para fingerprint."
                return self._elapsed(_time.monotonic(), result)

            if totals[OSType.LINUX] == totals[OSType.WINDOWS] == 0:
                result.certainty = ProbeCertainty.SUSPICION
                result.evidence.append("404 sin firmas reconocibles.")
                return self._elapsed(_time.monotonic(), result)

            ganador = max(totals, key=lambda k: totals[k])
            perdedor = min(totals, key=lambda k: totals[k])
            if totals[ganador] > totals[perdedor]:
                ratio = totals[ganador] / (totals[ganador] + totals[perdedor])
                result.votes = {ganador: min(1.0, ratio)}
                result.certainty = ProbeCertainty.CONFIRMED if ratio >= 0.9 else ProbeCertainty.SUSPICION
            else:
                result.certainty = ProbeCertainty.NO_VOTE
            return self._elapsed(_time.monotonic(), result)
        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"
            return self._elapsed(_time.monotonic(), result)
