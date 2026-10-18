"""
Architectural Ports and Protocols for Veraxi YMMP.

Defines the formal boundaries and interfaces (Ports) according to Clean Architecture:
- TimelineExporter: Exporter protocol for converting TimelineIR into target formats.
- ExportResult: Data transfer object describing exported artifacts.
- TTSBackend: Unified port for text-to-speech synthesis backends.
- DirectorProvider: Unified port for script directing engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .director import DirectorProvider
from .ir import TimelineIR
from .voicevox import TTSBackend


@dataclass
class ExportResult:
    """Result of exporting a TimelineIR representation to an external target format."""

    target_format: str
    output_path: Path
    artifacts: List[Path] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TimelineExporter(Protocol):
    """Protocol for timeline exporters that convert TimelineIR to target formats."""

    def export(
        self,
        ir: TimelineIR,
        output_path: Path,
        options: Optional[Dict[str, Any]] = None,
    ) -> ExportResult:
        """Export the given TimelineIR to output_path with optional exporter-specific options."""
        ...


__all__ = [
    "ExportResult",
    "TimelineExporter",
    "TTSBackend",
    "DirectorProvider",
]
