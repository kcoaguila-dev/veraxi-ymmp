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


def test_hatsuon_number_conv_alias(hatsuon):
    """Test _number_conv backward compatibility alias."""
    assert hatsuon._number_conv("456") == "456"


def test_hatsuon_kanji_reverse_conv_types(hatsuon):
    """Test kanji_reverse_conv accepts both str and sequence of str."""
    res_str = hatsuon.kanji_reverse_conv("漢字")
    assert isinstance(res_str, str)
    assert len(res_str) > 0

    res_seq = hatsuon.kanji_reverse_conv(["今日", "は", "晴れ"])
    assert isinstance(res_seq, str)
    assert "/" in res_seq


def test_hatsuon_kaname_reading(hatsuon):
    """Test systematic conversion of '要' to 'かなめ' vs on-yomi compounds."""
    # Noun / keystone reading 'かなめ'
    assert "かなめ" in hatsuon.convert("防御の要ですわ。")
    assert "かなめ" in hatsuon.convert("扇の要が壊れた。")
    assert "かなめ" in hatsuon.convert("守りの要として活躍する。")
    assert "かなめ" in hatsuon.convert("肝心要")

    # On-yomi compound words must retain 'よう'
    assert "じゅうよう" in hatsuon.convert("極めて重要ですわね。")
    assert "ひつよう" in hatsuon.convert("必要です。")
    assert "ようそ" in hatsuon.convert("要素です。")
    assert "ようやく" in hatsuon.convert("要約")
