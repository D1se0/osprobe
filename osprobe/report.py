"""Generación de informes exportables (JSON y Markdown).

El JSON es la salida "cruda" (útil para pipelines); el Markdown es
legible para humanos y perfecto para adjuntar en reportes de pentest.
"""

from __future__ import annotations

import json
import datetime
from typing import Optional

from .models import FinalVerdict


def to_json(verdict: FinalVerdict) -> str:
    payload = {
        "herramienta": "osprobe",
        "version": "1.0.0",
        "fecha": datetime.datetime.fromtimestamp(verdict.started_at).isoformat(),
        "objetivo": verdict.target_url,
        "veredicto": {
            "decision": verdict.decision.value,
            "confianza": verdict.confidence,
            "score_linux": verdict.score_linux,
            "score_windows": verdict.score_windows,
            "duracion_segundos": round(verdict.elapsed, 3),
        },
        "probes": [
            {
                "nombre": p.probe_name,
                "estado": "ok" if p.ok else "error",
                "certeza": p.certainty.value,
                "votos": {k.value: v for k, v in p.votes.items()},
                "evidencia": p.evidence,
                "error": p.error,
                "segundos": p.elapsed,
            }
            for p in verdict.probes
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def to_markdown(verdict: FinalVerdict) -> str:
    emoji = "🐧" if verdict.decision.value == "Linux" else "🪟" if verdict.decision.value == "Windows" else "❔"
    out: list[str] = [
        "# 🛰️ Informe OSProbe",
        "",
        f"**Objetivo:** `{verdict.target_url}`  ",
        f"**Fecha:** {datetime.datetime.fromtimestamp(verdict.started_at).strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Duración:** {verdict.elapsed:.2f} s",
        "",
        f"## {emoji} Veredicto: **{verdict.decision.value}**",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Score *Linux* | **{verdict.score_linux:.1f} / 100** |",
        f"| Score *Windows* | **{verdict.score_windows:.1f} / 100** |",
        f"| Confianza | {verdict.confidence * 100:.0f} % |",
        "",
        "## 🔬 Evidencia por probe",
        "",
        "| Probe | Estado | Certeza | Evidencia |",
        "|---|---|---|---|",
    ]
    for p in verdict.probes:
        evid = "<br>".join(e.replace("|", "\\|") for e in p.evidence[:8]) or "—"
        out.append(
            f"| `{p.probe_name}` | {'✔ ok' if p.ok else '✘ ' + (p.error or 'error')} | {p.certainty.value} | {evid} |"
        )
    out += [
        "",
        "---",
        "_Informe generado con OSProbe — técnica de sensibilidad a mayúsculas. "
        "Úsalo sólo contra activos con autorización expresa._",
    ]
    return "\n".join(out)
