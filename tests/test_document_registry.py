"""
Tests for DocumentCaptureRegistry and multi-source dispatch.
"""

import pytest

from veraxi_ymmp.epistemic.document_registry import DocumentCaptureRegistry, get_default_document_registry
from veraxi_ymmp.epistemic.edgar_capture import EdgarDocumentCaptureAdapter
from veraxi_ymmp.epistemic.facts import DocumentSourceType
from veraxi_ymmp.epistemic.fred_capture import FredDocumentCaptureAdapter
from veraxi_ymmp.core.ports import OfficialDocumentCapturePort


def test_registry_registration_and_lookup() -> None:
    """Verify registration, lookup, and error handling in DocumentCaptureRegistry."""
    registry = DocumentCaptureRegistry()
    assert not registry.has(DocumentSourceType.SEC_EDGAR)

    edgar_adapter = EdgarDocumentCaptureAdapter(prefer_offline=True)
    registry.register(DocumentSourceType.SEC_EDGAR, edgar_adapter)

    assert registry.has(DocumentSourceType.SEC_EDGAR)
    adapter = registry.get(DocumentSourceType.SEC_EDGAR)
    assert isinstance(adapter, OfficialDocumentCapturePort)

    with pytest.raises(KeyError, match="No document capture adapter registered"):
        registry.get(DocumentSourceType.CUSTOM)


def test_default_registry_contains_sec_and_fred() -> None:
    """Verify default registry provides SEC EDGAR, FRED, and WEB adapters."""
    registry = get_default_document_registry(prefer_offline=True)
    assert registry.has(DocumentSourceType.SEC_EDGAR)
    assert registry.has(DocumentSourceType.FRED)
    assert registry.has(DocumentSourceType.WEB)

    sec_adapter = registry.get(DocumentSourceType.SEC_EDGAR)
    assert isinstance(sec_adapter, EdgarDocumentCaptureAdapter)

    fred_adapter = registry.get(DocumentSourceType.FRED)
    assert isinstance(fred_adapter, FredDocumentCaptureAdapter)

    web_adapter = registry.get(DocumentSourceType.WEB)
    assert isinstance(web_adapter, OfficialDocumentCapturePort)
