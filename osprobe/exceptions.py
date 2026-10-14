"""Jerarquía de excepciones de OSProbe."""

from __future__ import annotations


class OSProbeError(Exception):
    """Error base del paquete."""


class InvalidTargetError(OSProbeError):
    """La URL objetivo no es válida o usa un esquema no soportado."""


class NetworkError(OSProbeError):
    """No se pudo hablar con el objetivo (DNS, timeouts, TLS, refusals)."""


class ProbeAbort(OSProbeError):
    """El objetivo no cumple las precondiciones para correr los probes."""
