"""Tests de integración del motor contra servidores simulados.

Ventaja clave: ambos simuladores viven en localhost, así validamos los
veredictos del motor sin tener que alquilar un Windows a nadie. Si un
día un probe "adivina" Linux contra el simulador IIS, estos tests
explotan en el CI — nunca más la vergüenza de un detector que miente.
"""

from __future__ import annotations

import asyncio

import pytest
from aiohttp import web

from osprobe.demo import make_fake_app
from osprobe.engine import OSProbeEngine, ScanSession
from osprobe.models import OSType, Target


async def _scan_inproc(os_type: str, url_path: str = "/images", seed: str = "images"):
    """Arranca el simulador, escanea de verdad y limpia por detrás."""
    runner = web.AppRunner(make_fake_app(os_type))
    await runner.setup()
    try:
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        target = Target(f"http://127.0.0.1:{port}{url_path}")
        session = ScanSession(
            target=target,
            seed_path=seed,
            timeout=5.0,
            retries=1,
            user_agent="OSProbe-Test/1.0",
        )
        return await OSProbeEngine().run(session)
    finally:
        await runner.cleanup()


def test_detecta_linux_con_alta_confianza():
    verdict = asyncio.run(_scan_inproc("linux"))
    assert verdict.decision is OSType.LINUX, verdict.probes
    assert verdict.confidence >= 0.6
    assert verdict.score_linux > verdict.score_windows


def test_detecta_windows_con_alta_confianza():
    verdict = asyncio.run(_scan_inproc("windows"))
    assert verdict.decision is OSType.WINDOWS, verdict.probes
    assert verdict.confidence >= 0.6
    assert verdict.score_windows > verdict.score_linux


def test_case_probe_votes():
    from osprobe.probes.case_probe import CaseSensitivityProbe

    linux_verdict = asyncio.run(_scan_inproc("linux"))
    case_l = next(p for p in linux_verdict.probes if p.probe_name == "case-sensitivity")
    assert case_l.ok and case_l.votes.get(OSType.LINUX, 0) > 0

    win_verdict = asyncio.run(_scan_inproc("windows"))
    case_w = next(p for p in win_verdict.probes if p.probe_name == "case-sensitivity")
    assert case_w.ok and case_w.votes.get(OSType.WINDOWS, 0) > 0


def test_seed_inexistente_abstiene():
    """Si la semilla no existe, el probe case NO debe inventar un veredicto."""
    from osprobe.probes.case_probe import CaseSensitivityProbe
    from osprobe.models import ProbeCertainty

    verdict = asyncio.run(_scan_inproc("linux", url_path="/no-existo", seed="fantasma"))
    case = next(p for p in verdict.probes if p.probe_name == CaseSensitivityProbe.name)
    assert case.certainty is ProbeCertainty.NO_VOTE or case.error


def test_generators_variantes():
    from osprobe.probes.case_probe import case_variants

    out = case_variants("images")
    assert "Images" in out and "IMAGES" in out and "imageS" in out
    assert "images" not in out  # la semilla sin mutar nunca sale
    # En deep: la variante camel intercalada de un fragmento de 5 chars
    # ("AbCdE") NO la genera el modo normal (la primera capital sería "Abcde").
    normal = case_variants("abcde")
    deep = case_variants("abcde", deep=True)
    assert "Abcde" in normal and "Abcde" in deep
    assert "AbCdE" in deep and "AbCdE" not in normal


def test_target_normalization():
    t1 = Target("10.10.10.10:8080/phpmyadmin")
    assert t1.scheme == "http" and t1.port == 8080 and t1.base_path == "/phpmyadmin"
    t2 = Target("https://ejemplo.com/")
    assert t2.port == 443 and t2.origin == "https://ejemplo.com"
    with pytest.raises(ValueError):
        Target("ftp://nope")
