"""Tests for the Hatsuon phonetic conversion module."""

import pytest
from veraxi_ymmp.hatsuon import Hatsuon, HatsuonError


@pytest.fixture
def hatsuon():
    """Create a Hatsuon instance for testing."""
    return Hatsuon()


def test_hatsuon_unify(hatsuon):
    """Test text unification."""
    # Test uppercase conversion
    assert hatsuon.unify("hello") == "HELLO"
    # Test NFKC normalization - halfwidth katakana to fullwidth
    result = hatsuon.unify("ﾊﾟﾊﾟ")
    assert isinstance(result, str)


def test_hatsuon_word_replace(hatsuon):
    """Test word replacement (は -> わ)."""
    # The word replace should convert は to わ
    result = hatsuon.word_replace("こんにちは")
    # The function replaces は with わ
    assert "わ" in result


def test_hatsuon_convert_basic(hatsuon):
    """Test basic conversion."""
    result = hatsuon.convert("こんにちは")
    # Should return some phonetic representation
    assert isinstance(result, str)
    assert len(result) > 0


def test_hatsuon_convert_empty(hatsuon):
    """Test conversion of empty string."""
    result = hatsuon.convert("")
    assert result == ""


def test_hatsuon_convert_ascii(hatsuon):
    """Test conversion of ASCII text."""
    result = hatsuon.convert("hello")
    assert isinstance(result, str)


def test_hatsuon_number_placeholder(hatsuon):
    """Test number handling (placeholder implementation)."""
    result = hatsuon.number("123")
    # Numbers are currently passed through unchanged
    assert result == "123"


def test_hatsuon_lazy_mecab_initialization(hatsuon):
    """Test that MeCab tagger is lazily initialized."""
    # The tagger should not be initialized yet
    assert hatsuon._tagger is None
    # Trigger initialization by calling a method that uses it
    hatsuon.bunsetsuWakachi("こんにちは")
    # Now it should be initialized
    assert hatsuon._tagger is not None


def test_hatsuon_error_handling(hatsuon):
    """Test that HatsuonError can be raised."""
    # This is a bit tricky to test without mocking
    # But we can at least verify the error class exists
    assert issubclass(HatsuonError, Exception)


def test_hatsuon_convert_with_kana(hatsuon):
    """Test conversion of text with various kana."""
    test_cases = [
        "こんにちは",  # Hiragana
        "コニチハ",    # Katakana
        "混合",      # Mixed
    ]
    for text in test_cases:
        result = hatsuon.convert(text)
        assert isinstance(result, str)
        assert len(result) > 0
