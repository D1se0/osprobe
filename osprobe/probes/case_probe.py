"""Probe estrella: discriminación por sensibilidad a mayúsculas/minúsculas.

La idea (técnica clásica, descrita a mediados de los 2000 y aún válida):

    * Los sistemas de ficheros de Linux (ext4, xfs, ...) **sí distinguen
      mayúsculas**. Si ``/images`` existe en disco, ``/Images`` no existe
      y el servidor responde 404.
    * NTFS (Windows) es **case-preserving pero case-insensitive**:
      ``/images`` y ``/Images`` resuelven al mismo fichero y ambos
      devuelven 200.

Protocolo del probe:
    1. Se confirma la existencia de la ruta semilla (``--seed-path`` o la
       ruta de la URL objetivo). Si la semilla no existe el probe
       abstiene su voto — no confiamos en comparar fantasmas.
    2. Se generan variantes de mayúsculas/minúsculas de la semilla
       (título, mayúsculas totales, inversión por fragmentos).
    3. Para cada variante se mide si el servidor la considera *«existente»*
       (código != 404/410) o *«inexistente»* (404/410).
    4. Interpretación:
           * 100 % de variantes inexistentes  -> FS sensitivo -> Linux.
           * 100 % de variantes existentes    -> FS insensitivo -> Windows.
           * Resultado mixto                  -> reescritura o proxy —
                                                se emite sospecha, no certeza.
"""

from __future__ import annotations

from typing import List, Tuple  # noqa: F401  (Tuple reservado para extensiones futuras)

from ..models import OSType, ProbeCertainty
from .base import Probe, ProbeContext

# Códigos que entendemos como «ruta existe pero te la escondo».
# Los contraste con 404/410 ( realmente no existe ).
EXISTENCE_ALTERNATIVES = (200, 201, 202, 204, 301, 302, 303, 307, 308, 403)


def case_variants(seed: str, deep: bool = False) -> List[str]:
    """Genera variantes de mayúsculas/minúsculas de una ruta.

    Siempre muta **un fragmento por vez** (p.ej. ``a/b`` -> ``A/b``,
    ``a/B``), porque un FS case-sensitive fallaría igualmente en
    cualquier fragmento y así medimos cada caso de forma aislada.
    En modo profundo añade variantes con inversión intercalada
    (``a/b`` -> ``Ab/Bb`` estilo camel) contra middlewares que sólo
    "normalizan" la primera letra.
    """
    seed = seed.strip("/")
    if not seed:
        return []
    parts = seed.split("/")

    def toggle(p: str) -> List[Tuple[str, str]]:
        out = [
            ("primera_capital", p[:1].upper() + p[1:]),
            ("TODO_MAYÚSCULAS", p.upper()),
            ("todo_minúsculas", p.lower()),
        ]
        if len(p) > 1:
            out.append(("última_capital", p[:-1] + p[-1].upper()))
        return out

    full: List[str] = []
    seen: set = {seed}
    for part_index, part in enumerate(parts):
        for _label, candidate in toggle(part):
            mutated = list(parts)
            mutated[part_index] = candidate
            ruta = "/".join(mutated)
            if ruta not in seen:
                seen.add(ruta)
                full.append(ruta)
        if deep:
            mixed = "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(part))
            mutated = list(parts)
            mutated[part_index] = mixed
            ruta = "/".join(mutated)
            if ruta not in seen:
                seen.add(ruta)
                full.append(ruta)
    # Ordena de menor a mayor agresividad: primero una letra, luego TODO.
    full.sort(key=lambda p: sum(c.isupper() for c in p))
    return full


class CaseSensitivityProbe(Probe):
    """Discrimina Linux vs Windows por comportamiento del FS ante casing."""

    name = "case-sensitivity"
    weight = 40.0
    description = (
        "Alterna mayúsculas de la ruta semilla. FS que devuelve 404 en las "
        "variantes => case-sensitive (Linux); si continúan respondiendo, "
        "el FS es case-insensitive (Windows/NTFS)."
    )

    async def run(self, ctx: ProbeContext) -> "ProbeResult":  # type: ignore[name-defined]
        result = self.make_result()
        import time as _time

        try:
            seed = ctx.seed_path.strip("/") or "images"
            base_url = ctx.target.origin

            # -- 1. Confirmar la semilla ----------------------------------
            baseline = await ctx.client.path_exists(base_url, seed)
            result.evidence.append(f"Semilla /{seed} -> HTTP {baseline.status}")
            if baseline.is_not_found:
                result.certainty = ProbeCertainty.NO_VOTE
                result.error = (
                    f"La semilla /{seed} devuelve 404; sin ruta confirmada no "
                    "puedo comparar nada. Usa --seed-path para señalar una ruta real."
                )
                return self._elapsed(_time.monotonic(), result)

            # -- 2. Pedir variantes -------------------------------------
            variants = case_variants(seed, deep=ctx.deep)[: 12 if not ctx.deep else 20]
            if not variants:
                result.error = "Semilla vacía: nada que mutar."
                return self._elapsed(_time.monotonic(), result)

            results = []
            for variant in variants:
                await self._sleep_jitter(ctx)
                snap = await ctx.client.path_exists(base_url, variant)
                exists = not snap.is_not_found
                results.append((variant, snap.status, exists))
                result.evidence.append(f"/{variant} -> HTTP {snap.status} ({'existe' if exists else '404'})")

            # -- 3. Registrar el veredicto parcial ---------------------------------
            existente = sum(1 for _, _, e in results if e)
            total = len(results)
            ratio = existente / total

            if existente == 0:
                result.certainty = ProbeCertainty.CONFIRMED
                result.votes = {OSType.LINUX: 1.0}
            elif existente == total:
                result.certainty = ProbeCertainty.CONFIRMED
                result.votes = {OSType.WINDOWS: 1.0}
            elif ratio >= 0.8 or ratio <= 0.2:
                result.certainty = ProbeCertainty.SUSPICION
                dominant = OSType.LINUX if ratio <= 0.2 else OSType.WINDOWS
                result.votes = {dominant: 0.55}
                result.evidence.append("Resultado mixto: posible reescritura/proxy delante (sospecha).")
            else:
                result.certainty = ProbeCertainty.SUSPICION
                result.evidence.append("Resultado totalmente ambiguo; no voto con convicción.")
                result.votes = {}

            return self._elapsed(_time.monotonic(), result)
        except Exception as exc:  # noqa: BLE001 — contrato de Probe
            result.error = f"{type(exc).__name__}: {exc}"
            return self._elapsed(_time.monotonic(), result)
