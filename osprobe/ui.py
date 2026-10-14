"""UI rica, banner animado y tablas de resultados para OSProbe.

Aquí vive toda la estética: gradiente HSL sobre arte ASCII, efecto
máquina de escribir, spinners contextualizados, medidor animado de
probabilidades (Live) y panel de veredicto final.

Todo el color respeta ``NO_COLOR`` y los terminales no-TTY
(rich lo hace solo), y ``--quiet`` desactiva las animaciones.
"""

from __future__ import annotations

import colorsys
import os
import sys
import time
from typing import Iterable, Optional

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

BANNER = r"""
  ___  ____  ____    _  _____  ____
 / _ \|  _ \|  _ \  / \|_   _|/ ___|
| | | | |_) | |_) || |> || |  \___ \
| |_| |  __/|  __/ | |> || | _ ___) |
 \___/|_|   |_|    |_|\__/|_|(_)____/
"""

TAGLINE = "fingerprint de SO remoto vía sensibilidad a mayúsculas · v1.0"

# Paleta graciosa: Tux (pico) vs Windows (azul con transparencia).
COLOR_STEALTH = "cyan"
COLOR_LINUX = "yellow"
COLOR_WINDOWS = "cyan"


def _hex_gradient(text: str, color_a=(0.55, 0.85, 0.60), color_b=(0.05, 0.45, 0.65)) -> Text:
    """Colorea cada línea del banner con un gradiente HSL suave."""
    lines = [line for line in text.split("\n") if line.strip()]
    n = max(len(lines) - 1, 1)
    out = Text()
    for i, line in enumerate(lines):
        h1, s1, v1 = color_a
        h2, s2, v2 = color_b
        t = i / n
        r, g, b = colorsys.hls_to_rgb(
            (h1 + (h2 - h1) * t) % 1.0,
            v1 + (v2 - v1) * t,
            s1 + (s2 - s1) * t,
        )
        color = "#{:02x}{:02x}{:02x}".format(
            int(r * 255), int(g * 255), int(b * 255)
        )
        out.append(line + "\n", style=f"bold {color}")
    return out


def _typewriter(console: Console, text: str, delay: float = 0.012) -> None:
    """Efecto de escritura progresiva (estética terminal annos 80)."""
    for ch in text:
        console.print(ch, end="", soft_wrap=True, highlight=False)
        console.file.flush()
        time.sleep(delay)
    console.print()


class UI:
    """Orquestación visual de una sesión de CLI OSProbe."""

    def __init__(self, quiet: bool = False, no_color: bool = False) -> None:
        self.quiet = quiet
        self.no_color = no_color or bool(os.environ.get("NO_COLOR"))
        self.console = Console(highlight=False, soft_wrap=True)
        self.progress: Optional[Progress] = None
        self._live: Optional[Live] = None

    # ------------------------------------------------------------------ #
    def banner(self) -> None:
        if self.quiet:
            return
        self.console.clear() if sys.stdout.isatty() else None
        art = _hex_gradient(BANNER)
        panel = Panel(
            Align.center(art) if self.console.width > 44 else art,
            subtitle=f"[italic]{TAGLINE}[/]",
            border_style="bold cyan",
            padding=(0, 2),
        )
        self.console.print(panel)
        self.console.print(
            Align.center(
                Text.from_markup(
                    "[dim]Detección pasiva del sistema operativo · "
                    "[/][bold]técnicas HTTP upstream[/]"
                )
            )
        )
        self.console.print(
            Align.center(
                Text.from_markup(
                    "[dim italic]D1se0 · uso responsable con permiso · MIT[/]",
                    style="dim",
                )
            )
        )
        self.console.print()
        if not self.quiet and sys.stdout.isatty():
            _typewriter(self.console, "  » Inicializando módulos de reconocimiento...\n", 0.008)
            _typewriter(self.console, "  » Cargando probes: case-sensitivity, headers, 404, backslash\n", 0.008)
            self.console.print()

    # ------------------------------------------------------------------ #
    def start_progress(self, total: int, label: str = "Escaneando") -> None:
        if self.quiet:
            return
        self.progress = Progress(
            SpinnerColumn(style="magenta"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="magenta", complete_style="cyan"),
            TextColumn("[magenta]{task.completed}/{task.total}[/]"),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
        )
        self.progress_task = self.progress.add_task(label, total=total)
        self._live = Live(self.progress, console=self.console, refresh_per_second=12)
        self._live.start()

    def advance(self, description: str) -> None:
        if self.progress is not None:
            self.progress.update(self.progress_task, description=description, advance=1)

    def stop_progress(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
            self.progress = None

    # ------------------------------------------------------------------ #
    def print_probe_result(self, nombre: str, ok: bool, description: str, extra: str = "") -> None:
        icon = "[bold green]✔[/]" if ok else "[bold red]✘[/]"
        body = f" {icon} [bold]{nombre}[/]"
        if description:
            body += f" [dim]· {description}[/]"
        self.console.print(body)
        if extra and not self.quiet:
            self.console.print(f"   [dim]{extra}[/]")

    def print_step(self, msg: str) -> None:
        if not self.quiet:
            self.console.print(f"  [cyan]▶[/] {msg}")

    # ------------------------------------------------------------------ #
    def render_verdict(self, verdict) -> None:  # FinalVerdict
        """Panel final: barra Linux vs Windows + veredicto + evidencia."""
        self.stop_progress()
        table = Table(
            show_header=False, box=None, padding=(0, 2, 0, 2), collapse_padding=True
        )
        table.add_column(justify="right", width=10)
        table.add_column(width=36)
        table.add_column(justify="right", width=6)

        def bar_row(label: str, pct: float, color: str) -> None:
            filled = int(round(pct / 100 * 24))
            bar = "▮" * filled + "▯" * (24 - filled)
            table.add_row(
                Text(label, style=f"bold {color}"),
                Text(bar, style=color),
                Text(f"{pct:.1f}%", style=f"bold {color}"),
            )

        lw = verdict.score_linux
        ww = verdict.score_windows
        if lw + ww == 0:
            lw = ww = 0.5  # para pintar 50/50 en vez de NaN
        total = lw + ww
        bar_row("Linux", verdict.score_linux * (100 / total), COLOR_LINUX)
        bar_row("Windows", verdict.score_windows * (100 / total), COLOR_WINDOWS)

        conf = verdict.confidence
        conf_label = "alta" if conf >= 0.66 else "media" if conf >= 0.35 else "baja"
        emoji = "🐧" if verdict.decision.value == "Linux" else "🪟" if verdict.decision.value == "Windows" else "❔"
        head = (
            f" {emoji}  [bold]{verdict.decision.value}[/] "
            f"[dim]· confianza {conf_label}[/] [bold cyan]{conf * 100:.0f}%[/]"
        )
        panel = Panel(
            Group(Text.from_markup(head), Text(""), table),
            title="[bold]Veredicto[/]",
            border_style="magenta",
            padding=(0, 1),
        )
        self.console.print()
        self.console.print(panel)

        # Tabla de evidencia por probe
        details = Table(
            title="[bold]Detalles por probe[/]", box=None, show_lines=False, pad_edge=False,
            title_justify="left",
        )
        details.add_column("Probe", style="cyan", no_wrap=True)
        details.add_column("Estado", no_wrap=True)
        details.add_column("Certeza", no_wrap=True)
        details.add_column("Evidencia", overflow="fold")
        for r in verdict.probes:
            state = "[green]ok[/]" if r.ok else f"[red]error[/]"
            details.add_row(
                r.probe_name,
                state,
                r.certainty.value,
                "\n".join(r.evidence) or ("—"),
            )
        self.console.print(details)

    def print_error(self, msg: str) -> None:
        self.console.print(f"[bold red][!][/][red] {msg}[/]")

    def print_info(self, msg: str) -> None:
        if not self.quiet:
            self.console.print(f"[cyan][*][/][dim] {msg}[/]")
