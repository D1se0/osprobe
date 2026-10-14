"""Interfaz de línea de comandos de OSProbe.

Opciones (todas documentadas en detalle en ``docs/USAGE.md``):

    objetivo                URL o host:puerto de la víctima (posicional).
    --path, -p              Ruta semilla confirmada (default: la ruta de la URL).
    --timeout, -t           Timeout por petición en segundos (default 8).
    --retries, -r           Reintentos ante error de red (default 2).
    --delay, -d             Segundos máximos de espera entre peticiones (0 = off).
    --proxy, -x             Proxy http(s)/socks5 para todas las peticiones.
    --insecure, -k          Deshabilita verificación TLS (app with --proxy típico)...
    --user-agent, -a        User-Agent personalizado.
    --deep                  Más variantes de casing y de backslash (más peticiones).
    --export json|md|txt    Exporta el informe a ``osprobe-informe.<ext>``.
    --export-dir RUTA       Carpeta para el informe (default: .).
    --quiet, -q             Sin animaciones ni banners; sólo el veredicto.
    --demo                  Corre un escaneo contra servidores simulados
                            (IIS-Windows + Linux) para probar la herramienta
                            sin tocar ningún host externo.
    --version               Muestra la versión y sale.

Todo el pipeline es asíncrono; ``main()`` anhela el bucle con asyncio.run.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from typing import List, Optional

from . import __version__
from .engine import OSProbeEngine, ScanSession
from .exceptions import OSProbeError
from .http_client import normalize
from .models import FinalVerdict, Target
from .report import to_json, to_markdown
from .ui import UI

EXIT_OK = 0
EXIT_TARGET_INVALID = 2
EXIT_NETWORK = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osprobe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "🛰️  OSProbe — fingerprint del sistema operativo remoto mediante "
            "técnicas HTTP (técnica estrella: sensibilidad a mayúsculas de las rutas).\n\n"
            "Uso RESPONSABLE: sólo contra activos tuyos o con autorización firmada."
        ),
        epilog="Repo: https://github.com/D1se0/osprobe",
    )
    parser.add_argument("objetivo", nargs="?", help="URL o host:puerto del objetivo (p.ej. http://10.0.0.5, ejemplo.com)")
    parser.add_argument("-p", "--path", default=None, help="Ruta base que SABES que existe (p.ej. 'images'); default: ruta de la URL")
    parser.add_argument("-t", "--timeout", type=float, default=8.0, help="Timeout por petición en segundos (default: 8)")
    parser.add_argument("-r", "--retries", type=int, default=2, help="Reintentos ante fallo de red (default: 2)")
    parser.add_argument("-d", "--delay", type=float, default=0.0, help="Retardo máximo entre peticiones en segundos (0 = sin límite)")
    parser.add_argument("-x", "--proxy", default=None, help="Proxy http:// | https:// | socks5:// (requiere aiohttp-socks para socks)")
    parser.add_argument("-k", "--insecure", action="store_true", help="No validar el certificado TLS (tipo nmap -k, curl -k)")
    parser.add_argument("-a", "--user-agent", default="OSProbe/1.0 (+https://github.com/D1se0/osprobe)", help="User-Agent personalizado (default: OSProbe/1.0)")
    parser.add_argument("--deep", action="store_true", help="Modo profundo: más variantes de casing/normalización (más peticiones)")
    parser.add_argument("--export", choices=("json", "md", "txt", "both"), default=None, help="Exportar informe: json, md, txt o both (md+json)")
    parser.add_argument("--export-dir", default=".", help="Directorio donde escribir el informe (default: cwd)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Modo silencioso: sin banners ni animaciones")
    parser.add_argument("--no-color", action="store_true", help="Fuerza sin color (respeta NO_COLOR)")
    parser.add_argument("--demo", action="store_true", help="Escanea servidores simulados (IIS-Windows + Linux) en localhost: sandbox completo")
    parser.add_argument("--version", action="version", version=f"OSProbe {__version__}")
    return parser


async def _scan_one(url: str, args: argparse.Namespace, seed: Optional[str], ui: UI) -> FinalVerdict:
    target = Target(url=normalize(url))
    session = ScanSession(
        target=target,
        timeout=args.timeout,
        retries=args.retries,
        delay=args.delay,
        verify=not args.insecure,
        proxy=args.proxy,
        user_agent=args.user_agent,
        deep=args.deep,
        seed_path=seed,
    )
    engine = OSProbeEngine()
    ui.start_progress(total=len(engine.probes), label=f"Probing {target.host}")

    def on_event(step: str, payload: dict) -> None:
        if step == "probe_inicio" and not args.quiet:
            ui.print_step(f"{payload['nombre']} — {payload['descripcion'][:72]}…")
        elif step == "probe_fin":
            ui.advance(payload["nombre"])
            ui.print_probe_result(
                payload["nombre"],
                payload["ok"],
                "" if payload["ok"] else f"error: {payload['error']}",
            )

    try:
        verdict = await engine.run(session, on_event=on_event)
    finally:
        ui.stop_progress()

    ui.render_verdict(verdict)
    return verdict


def _save_report(verdict: FinalVerdict, args: argparse.Namespace) -> List[str]:
    esc = args.export
    if not esc or esc == "none":
        return []
    os.makedirs(args.export_dir, exist_ok=True)
    base = os.path.join(args.export_dir, "osprobe-informe")
    escritos: List[str] = []
    if esc in ("json", "both"):
        p = f"{base}.json"
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(to_json(verdict))
        escritos.append(p)
    if esc in ("md", "txt", "both"):
        p = f"{base}.{(esc if esc == 'md' else 'md' if esc == 'both' else 'txt')}"
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(verdict))
        escritos.append(p)
    return escritos


async def _run_demo(args: argparse.Namespace, ui: UI) -> int:
    """Levanta los dos servidores simulados y los escanea ambos."""
    from .demo import make_fake_app

    from aiohttp import web

    resultados = []
    for os_type, etiqueta in (("linux", "Simulación de Linux (Apache)"), ("windows", "Simulación de Windows (IIS)")):
        runner = web.AppRunner(make_fake_app(os_type))
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        target_url = f"http://127.0.0.1:{port}/images"
        ui.print_info(f"Servidor simulado levantado: {etiqueta} en :{port}")
        verdict = await _scan_one(target_url, args, seed="images", ui=ui)
        resultados.append((etiqueta, verdict.decision.value, verdict.confidence))
        # Export con nombre distintivo por mock, para no pisar informes.
        if args.export:
            os.makedirs(args.export_dir, exist_ok=True)
            base = os.path.join(args.export_dir, f"osprobe-informe-{os_type}-mock")
            if args.export in ("json", "both"):
                with open(f"{base}.json", "w", encoding="utf-8") as fh:
                    fh.write(to_json(verdict))
                ui.print_info(f"Informe escrito en {base}.json")
            if args.export in ("md", "txt", "both"):
                ext = "md" if args.export in ("md", "both") else "txt"
                with open(f"{base}.{ext}", "w", encoding="utf-8") as fh:
                    fh.write(to_markdown(verdict))
                ui.print_info(f"Informe escrito en {base}.{ext}")
        await runner.cleanup()

    # Resumen comparativo del sandbox
    if not args.quiet:
        ui.console.print()
        ui.print_info("Comparativa sandbox completa: revisa los veredictos de arriba.")
    return EXIT_OK


async def async_main(args: argparse.Namespace) -> int:
    ui = UI(quiet=args.quiet, no_color=args.no_color)
    if not args.quiet:
        ui.banner()
    if args.demo:
        return await _run_demo(args, ui)

    if not args.objetivo:
        build_parser().error("falta el objetivo (o usa --demo para un sandbox local)")
    try:
        verdict = await _scan_one(args.objetivo, args, seed=args.path, ui=ui)
    except OSProbeError as exc:
        ui.print_error(str(exc))
        from .exceptions import InvalidTargetError, NetworkError

        return EXIT_TARGET_INVALID if isinstance(exc, InvalidTargetError) else EXIT_NETWORK

    escritos = _save_report(verdict, args)
    for f in escritos:
        ui.print_info(f"Informe escrito en {f}")
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\n[!] Escaneo interrumpido por el usuario (Ctrl-C).")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
