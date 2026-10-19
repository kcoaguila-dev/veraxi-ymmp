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
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from .director import DirectorProvider
from .ir import TimelineIR


@runtime_checkable
class TTSBackend(Protocol):
    """Protocol defining the interface for TTS backends."""

    def is_available(self) -> bool:
        ...

    def synthesize(self, text: str, speaker_id: int) -> Tuple[bytes, float, Dict[str, Any]]:
        ...

    def get_speakers(self) -> List[Dict[str, Any]]:
        ...


class NullTTSBackend:
    """A dummy TTS backend for testing or placeholder generation."""

    def is_available(self) -> bool:
        return True

    def get_audio_query(self, text: str, speaker_id: int) -> Dict[str, Any]:
        return {}

    def synthesize(self, text: str, speaker_id: int) -> Tuple[bytes, float, Dict[str, Any]]:
        return b"", 0.0, {}

    def get_speakers(self) -> List[Dict[str, Any]]:
        return []


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
    "NullTTSBackend",
    "DirectorProvider",
]
