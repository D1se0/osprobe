r"""Probe secundario: separador de rutas con backslash (`\`).

Tanto IIS como muchas aplicaciones ASP.NET **normalizan el backslash
como separador de rutas** (comportamiento heredado de Win32, donde
``C:\dir`` y ``C:/dir`` son equivalentes). Si pedimos:

        /images/../web.config   -> bloqueado por WAFs decentes
        /docs\readme.txt        -> IIS puede devolver 200

mientras que Apache/nginx sobre Linux tratan ``\`` como un carácter
más del nombre de fichero y responden 404.

Protocolo:
    1. Se confirma que el fondo (una ruta existente) responde 200.
    2. Se piden variantes con ``\`` en vez de ``/``.
    3. Si el servidor sigue respondiendo 200 con ``\`` => Windows (sospecha).
    4. Si responde 404/400 => Linux (sospecha).
"""

from __future__ import annotations

from typing import List

from ..models import OSType, ProbeCertainty
from .base import Probe, ProbeContext


class BackslashProbe(Probe):
    """Comprueba si el backslash es aceptado como separador de rutas."""

    name = "backslash-separator"
    weight = 20.0
    description = (
        "Sustituye '/' por '\\\\' en la ruta semilla. Windows (Win32) acepta "
        "ambos separadores; Linux los trata como nombres de fichero distintos."
    )

    async def run(self, ctx) -> "ProbeResult":  # type: ignore[name-defined]
        import time as _time

        result = self.make_result()
        try:
            seed = ctx.seed_path.strip("/") or ""
            if not seed:
                result.error = "Sin ruta semilla: el probe backslash no puede operar."
                return self._elapsed(_time.monotonic(), result)

            base_url = ctx.target.origin

            # -- Baseline ------------------------------------------------ #
            baseline = await ctx.client.path_exists(base_url, seed)
            result.evidence.append(f"Baseline /{seed} -> HTTP {baseline.status}")
            if baseline.is_not_found:
                result.certainty = ProbeCertainty.NO_VOTE
                result.error = "La semilla no existe; el probe backslash no compara contra nada."
                return self._elapsed(_time.monotonic(), result)

            # -- Variantes con backslash --------------------------------- #
            variants: List[str] = [seed.replace("/", "\\")]
            if ctx.deep:
                variants.append(f"{seed}\\%2e%2e\\web.config")  # travesía suave
                variants.append(f"\\{seed}")

            existente = 0
            total = 0
            for bad_path in variants:
                await self._sleep_jitter(ctx)
                snap = await ctx.client.path_exists(base_url, bad_path)
                total += 1
                okay = not snap.is_not_found and snap.status < 400
                result.evidence.append(f"/{bad_path!r} -> HTTP {snap.status}")
                if okay:
                    existente += 1

            ratio = existente / total
            if ratio == 1.0:
                result.certainty = ProbeCertainty.SUSPICION
                result.votes = {OSType.WINDOWS: 0.8}
            elif ratio == 0.0:
                # Nota: un 404 no es la única evidencia Linux, porque un
                # WAF puede bloquear el '\\'. De ahí que sólo votemos
                # con sospecha: humilde v1.
                result.certainty = ProbeCertainty.SUSPICION
                result.votes = {OSType.LINUX: 0.6}
            else:
                result.certainty = ProbeCertainty.SUSPICION
                result.evidence.append("Respuesta mixta al backslash; mejor no votar.")

            return self._elapsed(_time.monotonic(), result)
        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"
            return self._elapsed(_time.monotonic(), result)
