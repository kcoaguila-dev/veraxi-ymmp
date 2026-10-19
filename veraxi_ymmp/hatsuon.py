"""
Phonetic conversion engine for Japanese text (Hatsuon).
Copyright (c) 2026 Veraxi Project Contributors.
Licensed under the MIT License.

Provides Japanese pronunciation normalization, kana conversion, morphological
segmentation via MeCab, and kanji-to-hiragana conversion via pykakasi for
YMM4 and VOICEVOX timeline generation.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from typing import List, Optional, Union
from unicodedata import normalize

import alkana
import ipadic
import MeCab
from pykakasi import kakasi


class HatsuonError(Exception):
    """Exception raised when phonetic conversion fails."""

    pass


class Hatsuon:
    """
    Phonetic converter for Japanese script.

    Transforms Japanese orthography into pronunciation format compatible with
    VOICEVOX and YMM4 timeline synthesis.
    """

    _MECAB_ARGS = ipadic.MECAB_ARGS

    def __init__(self) -> None:
        """Initialize Hatsuon converter with kakasi instance and deferred MeCab tagger."""
        self.kakasi = kakasi()
        self._tagger: Optional[MeCab.Tagger] = None

    def _get_tagger(self) -> MeCab.Tagger:
        """
        Lazily initializes the MeCab morphological tagger.

        Returns:
            MeCab.Tagger instance.

        Raises:
            HatsuonError: If MeCab initialization fails.
        """
        if self._tagger is None:
            try:
                self._tagger = MeCab.Tagger(self._MECAB_ARGS)
            except Exception as e:
                raise HatsuonError(f"Failed to initialize MeCab tagger: {e}")
        return self._tagger

    def unify(self, sentence: str) -> str:
        """
        Normalize and uppercase text using Unicode NFKC.

        Args:
            sentence: Input string.

        Returns:
            Normalized uppercase string.
        """
        return normalize("NFKC", sentence.upper())

    def word_replace(self, sentence: str) -> str:
        """
        Replace specific conversational particles and loanwords with kana.

        Args:
            sentence: Input sentence string.

        Returns:
            Processed sentence with phonetic particle replacement and alkana conversions.
        """
        from .phonetics import normalize_kaname_reading

        sentence = re.sub(r"^(ええ|エエ)([、,\s。！？!?]|$)", r"えー\2", sentence)
        sentence = re.sub(r"([。！？!?]\s*)(ええ|エエ)([、,\s。！？!?]|$)", r"\1えー\3", sentence)
        sentence = sentence.replace("は", "わ")
        sentence = sentence.replace("何でも", "なんでも")
        sentence = normalize_kaname_reading(sentence)
        words = sentence.split()

        for word in words:
            kana = alkana.get_kana(word)
            if kana is not None:
                sentence = sentence.replace(word, kana)

        return sentence

    def bunsetsuWakachi(self, text: str) -> List[str]:
        """
        Segment text into bunsetsu phrases using morphological analysis.

        Args:
            text: Japanese text string.

        Returns:
            List of segmented phrases.

        Raises:
            HatsuonError: If MeCab parsing fails.
        """
        try:
            tagger = self._get_tagger()
            m_result = tagger.parse(text).splitlines()
            if m_result and m_result[-1].startswith("EOS"):
                m_result = m_result[:-1]

            break_pos = {"名詞", "動詞", "接頭詞", "副詞", "感動詞", "形容詞", "形容動詞", "連体詞"}
            wakachi: List[str] = [""]
            after_prepos = False
            after_sahen_noun = False

            for v in m_result:
                if "\t" not in v:
                    continue

                parts = v.split("\t")
                surface = parts[0]
                pos = parts[1].split(",")
                pos_detail = ",".join(pos[1:4])

                no_break = (
                    pos[0] not in break_pos
                    or "接尾" in pos_detail
                    or (pos[0] == "動詞" and "サ変接続" in pos_detail)
                    or "非自立" in pos_detail
                    or after_prepos
                    or (
                        after_sahen_noun
                        and pos[0] == "動詞"
                        and len(pos) > 4
                        and pos[4] == "サ変・スル"
                    )
                )

                if not no_break:
                    wakachi.append("")
                wakachi[-1] += surface
                after_prepos = pos[0] == "接頭詞"
                after_sahen_noun = "サ変接続" in pos_detail

            if wakachi and wakachi[0] == "":
                wakachi = wakachi[1:]
            return wakachi

        except Exception as e:
            raise HatsuonError(f"Morphological analysis failed for '{text}': {e}")

    def kanji_reverse_conv(self, tokens: Union[str, Sequence[str]]) -> str:
        """
        Convert kanji phrases or words into slash-separated hiragana readings.

        Supports either a single string or a sequence of phrases.

        Args:
            tokens: String or sequence of phrases/words.

        Returns:
            Slash-delimited hiragana readings string.
        """
        token_list = [tokens] if isinstance(tokens, str) else list(tokens)
        result: List[str] = []
        for token in token_list:
            raw = self.kakasi.convert(token)
            hira = "".join(entry["hira"] for entry in raw)
            result.append(hira)
        return "/".join(result)

    def number(self, sentence: str) -> str:
        """
        Handle numbers in text (placeholder for kana expansion).

        Args:
            sentence: Input text containing numbers.

        Returns:
            Sentence string unchanged.
        """
        pattern = r"\d+"
        re.findall(pattern, sentence)
        return sentence

    def _number_conv(self, sentence: str) -> str:
        """Alias for number method for backward compatibility."""
        return self.number(sentence)

    def convert(self, sentence: str) -> str:
        """
        Convert text into pronunciation format.

        Applies normalization, word replacement, morphological phrase splitting,
        and kanji-to-hiragana conversion.

        Args:
            sentence: Input Japanese text string.

        Returns:
            Phonetic pronunciation string suitable for speech synthesis.
        """
        try:
            unified = self.unify(sentence)
            replaced = self.unify(self.word_replace(unified))
            bunsetu = self.bunsetsuWakachi(replaced)
            kanji = self.kanji_reverse_conv(bunsetu)
            return kanji.replace("/", "")
        except HatsuonError:
            raise
        except Exception as e:
            warnings.warn(
                f"Failed to derive Hatsuon for '{sentence}': {e}. Falling back to verbatim string."
            )
            return sentence
