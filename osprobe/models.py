"""Modelos de datos compartidos por todos los módulos de OSProbe.

Todo el motor pasa por aquí: Target describe a la víctima (URL objetivo),
ProbeResult describe lo que votó cada fingerprint, y FinalVerdict es el
veredicto del consenso ponderado final.
"""

from __future__ import annotations

import time
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class OSType(str, Enum):
    """Sistemas que OSProbe puede predecir. La abstención también existe."""

    LINUX = "Linux"
    WINDOWS = "Windows"
    UNKNOWN = "Desconocido"


class ProbeCertainty(str, Enum):
    """Fuerza con la que un probe vota."""

    CONFIRMED = "confirmado"
    SUSPICION = "sospecha"
    NO_VOTE = "abstención"


@dataclass
class Target:
    """URL objetivo normalizada.

    Almacena esquema, host, puerto y la ruta base sobre la que operan los
    probes. Si el usuario pasa sólo ``host:puerto`` se asume ``http://``.
    """

    url: str
    base_path: str = ""
    _parsed: urllib.parse.ParseResult = field(init=False, repr=False, default=None)  # type: ignore

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlsplit(self.url if "://" in self.url else f"http://{self.url}")
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Esquema no soportado: {parsed.scheme!r} (sólo http/https)")
        if not parsed.netloc:
            raise ValueError(f"Host vacío en la URL {self.url!r}")
        self._parsed = parsed
        self.base_path = parsed.path.rstrip("/")

    # ---- Propiedades de conveniencia -------------------------------------
    @property
    def scheme(self) -> str:
        return self._parsed.scheme

    @property
    def host(self) -> str:
        return self._parsed.hostname or ""

    @property
    def port(self) -> int:
        if self._parsed.port:
            return self._parsed.port
        return 443 if self._parsed.scheme == "https" else 80

    @property
    def origin(self) -> str:
        """URL sin ruta: ``http://host:puerto``."""
        return urllib.parse.urlunsplit((self._parsed.scheme, self._parsed.netloc, "", "", ""))


@dataclass
class ProbeResult:
    """Salida estandarizada de un probe de huella.

    ``votes`` reparte una puntuación normalizada entre las clases
    OSType.LINUX/WINDOWS (el resto es abstención). ``evidence`` guarda
    una lista legible de qué se pidió y qué se recibió.
    """

    probe_name: str
    description: str
    certainty: ProbeCertainty = ProbeCertainty.NO_VOTE
    votes: Dict[OSType, float] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    error: Optional[str] = None
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class FinalVerdict:
    """Veredicto ponderado de la sesión completa."""

    decision: OSType = OSType.UNKNOWN
    confidence: float = 0.0
    score_linux: float = 0.0
    score_windows: float = 0.0
    probes: list[ProbeResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    target_url: str = ""

    @property
    def elapsed(self) -> float:
        return self.finished_at - self.started_at
