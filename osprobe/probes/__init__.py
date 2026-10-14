"""Registro dinámico de probes del paquete."""

from .base import Probe, ProbeContext
from .case_probe import CaseSensitivityProbe
from .backslash_probe import BackslashProbe
from .headers_probe import HeadersProbe
from .notfound_probe import NotFoundFingerprintProbe

#: Orden canónico en el que el motor intenta correr los probes.
ALL_PROBES = (
    CaseSensitivityProbe,
    HeadersProbe,
    NotFoundFingerprintProbe,
    BackslashProbe,
)

__all__ = ["Probe", "ProbeContext", "CaseSensitivityProbe", "BackslashProbe", "HeadersProbe", "NotFoundFingerprintProbe", "ALL_PROBES"]
