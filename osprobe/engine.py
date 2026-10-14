"""Motor de escaneo y veredicto de consenso ponderado de OSProbe.

El ``OSProbeEngine``:

    1. Prepara el ``ProbeContext`` con el cliente HTTP y la ruta semilla.
    2. Corre cada ``Probe`` (en serie, para respetar el rate-limit; los
       probes internos ya son asíncronos y ligeros).
    3. Agrega los votos: ``score_os = Σ (voto_os × weight_probe) / Σ weight``.
    4. Publica un ``FinalVerdict`` con los porcentajes Linux/Windows y la
       confianza global (cuántos probes han votado de verdad).
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from .http_client import HttpClient
from .models import FinalVerdict, OSType, ProbeResult, Target
from .probes import ALL_PROBES, Probe, ProbeContext

EventCallback = Callable[[str, dict], None]


class ScanSession:
    """Parámetros combinados de Target + opciones de CLI."""

    def __init__(
        self,
        target: Target,
        timeout: float = 8.0,
        retries: int = 2,
        delay: float = 0.0,
        verify: bool = True,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        deep: bool = False,
        seed_path: Optional[str] = None,
    ) -> None:
        self.client = HttpClient(
            timeout=timeout,
            retries=retries,
            proxy=proxy,
            delay=delay,
            verify=verify,
            user_agent=user_agent or "OSProbe/1.0",
        )
        self.target = target
        self.deep = deep
        self.seed_path = seed_path
        self.timeout = timeout
        self.retries = retries
        self.delay = delay


class OSProbeEngine:
    """Orquesta los probes y calcula el veredicto."""

    def __init__(self, probes: Optional[List[Probe]] = None) -> None:
        self.probes: List[Probe] = list(probes) if probes is not None else [K() for K in ALL_PROBES]

    async def run(self, session: ScanSession,
                  on_event: Optional[EventCallback] = None) -> FinalVerdict:
        """Ejecuta todos los probes contra la sesión y devuelve el veredicto."""

        async def emit(step: str, payload: Optional[dict] = None) -> None:
            if on_event:
                on_event(step, payload or {})

        verdict = FinalVerdict(target_url=session.target.url, started_at=time.time())
        async with session.client as client:
            ctx = ProbeContext(
                client=client,
                target=session.target,
                delay=session.delay,
                deep=session.deep,
                seed_path=session.seed_path,
            )

            await emit("inicio", {"url": session.target.url})
            for probe in self.probes:
                await emit("probe_inicio", {"nombre": probe.name, "descripcion": probe.description})
                try:
                    result: ProbeResult = await probe.run(ctx)
                except Exception as exc:  # noqa: BLE001 — defensa en profundidad
                    result = ProbeResult(
                        probe_name=probe.name,
                        description=probe.description,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                verdict.probes.append(result)
                await emit("probe_fin", {
                    "nombre": probe.name,
                    "ok": result.ok,
                    "certeza": result.certainty.value,
                    "puntos": len(result.evidence),
                    "error": result.error,
                })
                # Respiremos entre probes para no macetear el servidor
                if session.delay:
                    import asyncio
                    await asyncio.sleep(session.delay * 0.5)

        # ---------------------------------------------------------- #
        #            Agregación ponderada de votos                   #
        # ---------------------------------------------------------- #
        w_total = 0.0
        for probe_instance, result in zip(self.probes, verdict.probes):
            if not result.ok or result.certainty.value == "abstención":
                continue
            for os_type, vote in result.votes.items():
                contrib = vote * probe_instance.weight
                if os_type is OSType.LINUX:
                    verdict.score_linux += contrib
                elif os_type is OSType.WINDOWS:
                    verdict.score_windows += contrib
            w_total += probe_instance.weight

        if w_total > 0:
            verdict.score_linux = round((verdict.score_linux / w_total) * 100, 1)
            verdict.score_windows = round((verdict.score_windows / w_total) * 100, 1)

        if verdict.score_linux > verdict.score_windows:
            verdict.decision = OSType.LINUX
        elif verdict.score_windows > verdict.score_linux:
            verdict.decision = OSType.WINDOWS

        # Confianza = proporción de probes que emitieron votos reales.
        votantes = [r for r in verdict.probes if r.ok and r.votes]
        if votantes:
            peso_votado = sum(
                next(p.weight for p in self.probes if p.name == r.probe_name) for r in votantes
            )
            verdict.confidence = round(peso_votado / sum(p.weight for p in self.probes), 4)

        verdict.finished_at = time.time()
        await emit("fin", {"veredicto": verdict.decision.value})
        return verdict
