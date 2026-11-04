"""
Application-Layer Official Document Capture Registry.

Maps DocumentSourceType to concrete OfficialDocumentCapturePort implementations.
Enables dynamic multi-source document ingestion (SEC EDGAR, St. Louis Fed FRED, etc.)
without leaking source-specific details into caller layers.
"""

from __future__ import annotations

from typing import Dict

from .edgar_capture import EdgarDocumentCaptureAdapter
from .facts import DocumentSourceType
from .fred_capture import FredDocumentCaptureAdapter
from .ports import OfficialDocumentCapturePort


class DocumentCaptureRegistry:
    """Registry coordinating official primary authority document capture adapters."""

    def __init__(self) -> None:
        self._adapters: Dict[DocumentSourceType, OfficialDocumentCapturePort] = {}

    def register(
        self,
        source_type: DocumentSourceType,
        adapter: OfficialDocumentCapturePort,
    ) -> None:
        """Register an adapter for a document source type."""
        self._adapters[source_type] = adapter

    def get(self, source_type: DocumentSourceType) -> OfficialDocumentCapturePort:
        """Retrieve adapter for source_type, raising KeyError if not found."""
        if source_type not in self._adapters:
            raise KeyError(
                f"No document capture adapter registered for {source_type}. "
                f"Available sources: {list(self._adapters.keys())}"
            )
        return self._adapters[source_type]

    def has(self, source_type: DocumentSourceType) -> bool:
        """Return True if an adapter is registered for source_type."""
        return source_type in self._adapters


def get_default_document_registry(prefer_offline: bool = False) -> DocumentCaptureRegistry:
    """Instantiate and populate default capture registry with official sources."""
    registry = DocumentCaptureRegistry()
    registry.register(DocumentSourceType.SEC_EDGAR, EdgarDocumentCaptureAdapter(prefer_offline=prefer_offline))
    registry.register(DocumentSourceType.FRED, FredDocumentCaptureAdapter(prefer_offline=prefer_offline))
    return registry
