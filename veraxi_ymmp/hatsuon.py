# Adapted from akazdayo/AutoYukkuri (GPL-3.0)
# https://github.com/akazdayo/AutoYukkuri/blob/main/src/hatsuon.py

from unicodedata import normalize
import alkana
import MeCab
import ipadic
from pykakasi import kakasi
import re
import warnings

# Suppress standard warnings if necessary, initialize tagger
m = MeCab.Tagger(ipadic.MECAB_ARGS)

class Hatsuon:
    def __init__(self) -> None:
        self.kakasi = kakasi()

    def unify(self, sentence):
        to_upper = sentence.upper()
        to_normalize = normalize('NFKC', to_upper)
        return to_normalize

    def word_replace(self, sentence):
        sentence = sentence.replace("は", "わ")
        word = [x for x in sentence.split()]

        for x in word:
            yomi = alkana.get_kana(x)
            if yomi is not None:
                sentence = sentence.replace(x, yomi)

        return sentence

    def bunsetsuWakachi(self, text):
        m_result = m.parse(text).splitlines()
        m_result = m_result[:-1] # 最後の1行は不要な行なので除く
        break_pos = ['名詞','動詞','接頭詞','副詞','感動詞','形容詞','形容動詞','連体詞']
        wakachi = ['']
        afterPrepos = False
        afterSahenNoun = False
        for v in m_result:
            if '\t' not in v: continue
            surface = v.split('\t')[0]
            pos = v.split('\t')[1].split(',')
            pos_detail = ','.join(pos[1:4])

            noBreak = pos[0] not in break_pos
            noBreak = noBreak or '接尾' in pos_detail
            noBreak = noBreak or (pos[0]=='動詞' and 'サ変接続' in pos_detail)
            noBreak = noBreak or '非自立' in pos_detail
            noBreak = noBreak or afterPrepos
            noBreak = noBreak or (afterSahenNoun and pos[0]=='動詞' and pos[4]=='サ変・スル')

            if noBreak == False:
                wakachi.append("")
            wakachi[-1] += surface
            afterPrepos = pos[0]=='接頭詞'
            afterSahenNoun = 'サ変接続' in pos_detail

        if wakachi and wakachi[0] == '': wakachi = wakachi[1:]
        return wakachi

    def kanji_reverse_conv(self, word):
        result = []
        for x in word:
            raw = self.kakasi.convert(x)
            hira = [y['hira'] for y in raw]
            result.append("".join(hira))
        return "/".join(result)

    def number(self, sentence):
        pattern = r"\d+"
        matches = re.findall(pattern, sentence)
        for match in matches:
            # We don't use the original AutoYukkuri <NUMK> placeholder as we just need standard reading
            # But converting numbers to reading is tricky, keeping simple or preserving as is for now
            # YMM4 / AquesTalk often handles simple numbers or needs them converted to kana
            pass
        return sentence

    def convert(self, sentence: str) -> str:
        try:
            unified = self.unify(sentence)
            replaced = self.unify(self.word_replace(unified))
            bunsetu = self.bunsetsuWakachi(replaced)
            kanji = self.kanji_reverse_conv(bunsetu)
            # AquesTalk typically doesn't want the slash separators produced by the above function,
            # so we'll remove them.
            result = kanji.replace("/", "")
            return result
        except Exception as e:
            warnings.warn(f"Failed to derive Hatsuon for '{sentence}': {e}. Falling back to verbatim string.")
            return sentence
