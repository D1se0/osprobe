"""Clase base abstracta para todos los probes de OSProbe.

Un *probe* es un experimento HTTP aislado que compara cómo responde el
servidor ante pequeñas variaciones de una misma petición. Cada probe
devuelve votos ponderados hacia ``Linux`` o ``Windows``; el motor agrega
los votos de todos los probes en un veredicto de consenso.

Contrato de implementación:
    * ``run()`` nunca debe lanzar excepciones inesperadas: captura y
      conviértelas en ``ProbeResult(error=...)``.
    * Los votos se reparten en valores ``0.0 <= v <= 1.0``; la suma
      puede ser < 1 (abstención parcial) pero nunca > 1.
"""

from __future__ import annotations

import abc
import asyncio
import random
import string
import time

from ..models import ProbeCertainty, ProbeResult, Target

if False:  # pragma: no cover — sólo para type-checkers
    from ..http_client import HttpClient


class Probe(abc.ABC):
    """Vector de huella hacia un servidor remoto."""

    #: Nombre corto que aparece en la UI y en el informe
    name: str = "probe"
    #: Peso sobre el veredicto de consenso (0..100)
    weight: float = 10.0
    #: Descripción legible que se muestra en los informes
    description: str = ""

    def __repr__(self) -> str:  # pragma: no cover — cosmético
        return f"<{type(self).__name__} weight={self.weight}>"

    @abc.abstractmethod
    async def run(self, probe_ctx: "ProbeContext") -> ProbeResult:
        """Ejecuta el experimento y devuelve su ``ProbeResult``."""

    # ------------------------------------------------------------------ #
    # Utilidades compartidas por los probes                              #
    # ------------------------------------------------------------------ #
    def make_result(self) -> ProbeResult:
        return ProbeResult(
            probe_name=self.name,
            description=self.description or type(self).__doc__ or "",
        )

    def _elapsed(self, t0: float, result: ProbeResult) -> ProbeResult:
        result.elapsed = round(time.monotonic() - t0, 3)
        return result

    async def _sleep_jitter(self, ctx: "ProbeContext") -> None:
        """Rate-limit amable con jitter para no despertar WAFs groseros."""
        if ctx.delay > 0:
            await asyncio.sleep(random.uniform(ctx.delay * 0.5, ctx.delay))


class ProbeContext:
    """Lo que todo probe necesita para trabajar.

    Agrupa el cliente HTTP, el ``Target`` y las opciones globales del
    escaneo, de modo que un probe nuevo sólo necesita consumir esto.
    """

    def __init__(
        self,
        client: "HttpClient",
        target: Target,
        delay: float = 0.0,
        deep: bool = False,
        seed_path: str | None = None,
    ) -> None:
        self.client = client
        self.target = target
        self.delay = delay
        self.deep = deep
        # Ruta que el usuario confirma que existe (o autodetectada).
        self.seed_path = seed_path or (target.base_path or "/")

    # ------------------------------------------------------------------ #
    def random_notfound_path(self) -> str:
        """Ruta aleatoria que casi con seguridad no existe.

        El prefijo ``osprobe-`` permite filtrar nuestras basura en logs
        ajenos, y la entropía evita que un proxy cacheé la respuesta.
        """
        alphabet = string.ascii_lowercase + string.digits
        token = "".join(random.choice(alphabet) for _ in range(16))
        return f"osprobe-not-found-{token}.html"

    def url(self, path: str) -> str:
        """URL absoluta para ``path`` relativo al origen del Target."""
        base = self.target.origin.rstrip("/")
        return f"{base}/{path.lstrip('/')}"
