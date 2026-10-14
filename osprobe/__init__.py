"""
OSProbe — Fingerprint del sistema operativo remoto vía técnicas HTTP.

Nunca hagas esto contra infraestructura que no te pertenece o que no
tengas autorización expresa para auditar. Ver LICENSE y DISCLAIMER.

Un saludo a la vieja escuela: la técnica de sensibilidad a mayúsculas
funciona desde los tiempos de IIS 5.0 y aún sigue siendo oro puro.
"""

__title__ = "osprobe"
__version__ = "1.0.0"
__author__ = "D1se0"
__license__ = "MIT"

from .engine import OSProbeEngine, ScanSession  # noqa: F401
from .models import FinalVerdict, ProbeResult, Target  # noqa: F401

__all__ = [
    "OSProbeEngine",
    "ScanSession",
    "FinalVerdict",
    "ProbeResult",
    "Target",
]
