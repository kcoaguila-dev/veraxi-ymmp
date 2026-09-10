# Adapted from akazdayo/AutoYukkuri (GPL-3.0)
# https://github.com/akazdayo/AutoYukkuri/blob/main/src/hatsuon.py

"""
Hatsuon (発音) module for phonetic conversion of Japanese text.

This module provides pronunciation conversion for Japanese text to be used
with VOICEVOX and YMM4 voice synthesis. It handles:
- Text normalization (NFKC, uppercase)
- Word replacement and kana conversion
- Morphological analysis using MeCab
- Kanji to kana conversion using kakasi
"""

from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING, List, Optional
from unicodedata import normalize

import alkana
import ipadic
import MeCab
from pykakasi import kakasi

if TYPE_CHECKING:
    pass


class HatsuonError(Exception):
    """Exception raised when Hatsuon conversion fails."""
    pass


class Hatsuon:
    """
    Phonetic converter for Japanese text.

    Converts Japanese text to pronunciation format suitable for VOICEVOX/AquesTalk.
    Handles kanji, hiragana, katakana, and romanji conversion.

    Attributes:
        kakasi: The kakasi converter instance for kanji-to-kana conversion.
        _tagger: Lazy-loaded MeCab tagger for morphological analysis.
    """

    # Module-level constants for MeCab configuration
    _MECAB_ARGS = ipadic.MECAB_ARGS

    def __init__(self) -> None:
        """Initialize Hatsuon converter with kakasi instance."""
        self.kakasi = kakasi()
        self._tagger: Optional[MeCab.Tagger] = None

    def _get_tagger(self) -> MeCab.Tagger:
        """
        Lazy initialization of MeCab tagger.

        Returns:
            MeCab.Tagger: Initialized tagger instance.

        Raises:
            HatsuonError: If MeCab tagger cannot be initialized.
        """
        if self._tagger is None:
            try:
                self._tagger = MeCab.Tagger(self._MECAB_ARGS)
            except Exception as e:
                raise HatsuonError(f"Failed to initialize MeCab tagger: {e}")
        return self._tagger

    def unify(self, sentence: str) -> str:
        """
        Normalize and uppercase text.

        Args:
            sentence: Input text to normalize.

        Returns:
            Normalized text in uppercase with NFKC normalization.
        """
        to_upper = sentence.upper()
        to_normalize = normalize('NFKC', to_upper)
        return to_normalize

    def word_replace(self, sentence: str) -> str:
        """
        Replace specific words and convert kanji to kana.

        Handles special cases like は->わ and converts kanji to kana using alkana.

        Args:
            sentence: Input text to process.

        Returns:
            Processed text with replacements and kana conversion.
        """
        sentence = sentence.replace("は", "わ")
        words = [x for x in sentence.split()]

        for word in words:
            kana = alkana.get_kana(word)
            if kana is not None:
                sentence = sentence.replace(word, kana)

        return sentence

    def bunsetsuWakachi(self, text: str) -> List[str]:
        """
        Split text into phrases (bunsetsu) using MeCab.

        Uses morphological analysis to identify phrase boundaries.
        Breaks at nouns, verbs, adjectives, etc.

        Args:
            text: Input text to split.

        Returns:
            List of phrases.

        Raises:
            HatsuonError: If morphological analysis fails.
        """
        try:
            tagger = self._get_tagger()
            m_result = tagger.parse(text).splitlines()
            # Last line is EOS marker, skip it
            m_result = m_result[:-1]

            break_pos = ['名詞', '動詞', '接頭詞', '副詞', '感動詞', '形容詞', '形容動詞', '連体詞']
            wakachi: List[str] = ['']
            after_prepos = False
            after_sahen_noun = False

            for v in m_result:
                if '\t' not in v:
                    continue

                surface = v.split('\t')[0]
                pos = v.split('\t')[1].split(',')
                pos_detail = ','.join(pos[1:4])

                no_break = pos[0] not in break_pos
                no_break = no_break or '接尾' in pos_detail
                no_break = no_break or (pos[0] == '動詞' and 'サ変接続' in pos_detail)
                no_break = no_break or '非自立' in pos_detail
                no_break = no_break or after_prepos
                no_break = no_break or (after_sahen_noun and pos[0] == '動詞' and pos[4] == 'サ変・スル')

                if not no_break:
                    wakachi.append("")
                wakachi[-1] += surface
                after_prepos = pos[0] == '接頭詞'
                after_sahen_noun = 'サ変接続' in pos_detail

            if wakachi and wakachi[0] == '':
                wakachi = wakachi[1:]
            return wakachi

        except Exception as e:
            raise HatsuonError(f"Morphological analysis failed for '{text}': {e}")

    def kanji_reverse_conv(self, word: str) -> str:
        """
        Convert kanji to hiragana readings.

        Args:
            word: Input text containing kanji.

        Returns:
            Space-separated hiragana readings.
        """
        result: List[str] = []
        for char in word:
            raw = self.kakasi.convert(char)
            hira = [y['hira'] for y in raw]
            result.append("".join(hira))
        return "/".join(result)

    def number(self, sentence: str) -> str:
        """
        Handle numbers in text.

        Currently a placeholder - numbers are left as-is since YMM4/AquesTalk
        typically handles simple numbers or needs them converted to kana.

        Args:
            sentence: Input text containing numbers.

        Returns:
            Input text unchanged (placeholder implementation).
        """
        pattern = r"\d+"
        matches = re.findall(pattern, sentence)
        for match in matches:
            # YMM4 / AquesTalk often handles simple numbers or needs them converted to kana
            # This is a placeholder for future number-to-kana conversion
            pass
        return sentence

    def convert(self, sentence: str) -> str:
        """
        Convert text to pronunciation format.

        Main conversion method that applies all transformation steps:
        1. Unify and normalize text
        2. Apply word replacements
        3. Split into phrases
        4. Convert kanji to readings
        5. Remove slash separators (AquesTalk doesn't use them)

        Args:
            sentence: Input Japanese text to convert.

        Returns:
            Pronunciation string suitable for VOICEVOX/AquesTalk.
            Falls back to original sentence if conversion fails.
        """
        try:
            unified = self.unify(sentence)
            replaced = self.unify(self.word_replace(unified))
            bunsetu = self.bunsetsuWakachi(replaced)
            kanji = self.kanji_reverse_conv(bunsetu)
            # AquesTalk typically doesn't want the slash separators
            result = kanji.replace("/", "")
            return result
        except HatsuonError:
            raise
        except Exception as e:
            warnings.warn(
                f"Failed to derive Hatsuon for '{sentence}': {e}. "
                "Falling back to verbatim string."
            )
            return sentence
