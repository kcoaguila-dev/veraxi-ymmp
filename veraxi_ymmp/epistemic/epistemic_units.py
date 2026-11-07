"""Epistemic unit registry, dimensional safety engine, and magnitude extraction.

Pure domain module (zero outer-layer imports).
Enforces physical and financial dimensional invariants using Pint:
- Multi-currency dimensions are mutually orthogonal (USD, JPY, EUR, GBP, CNY, etc.).
- Cross-currency operations without conversion rates raise DimensionalityError.
- SI unit conversions (GW <-> MW <-> kW, TB <-> GB <-> MB) resolve seamlessly.
- Dimensionless percentages, basis points, and multipliers are safely handled.
"""

from __future__ import annotations

import ast
import operator
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple
import pint

try:
    import MeCab
    import ipadic
    _MECAB_TAGGER = MeCab.Tagger(ipadic.MECAB_ARGS)
except Exception:
    _MECAB_TAGGER = None

_UREG = pint.UnitRegistry()

# Define orthogonal currencies
_UREG.define("currency_usd = [currency_usd] = USD = dollar = dollars")
_UREG.define("currency_jpy = [currency_jpy] = JPY = yen")
_UREG.define("currency_eur = [currency_eur] = EUR = euro = euros")
_UREG.define("currency_gbp = [currency_gbp] = GBP = pound = pounds")
_UREG.define("currency_cny = [currency_cny] = CNY = yuan = rmb")
_UREG.define("currency_krw = [currency_krw] = KRW = won")
_UREG.define("currency_inr = [currency_inr] = INR = rupee = rupees")
_UREG.define("currency_aud = [currency_aud] = AUD")
_UREG.define("currency_cad = [currency_cad] = CAD")
_UREG.define("currency_chf = [currency_chf] = CHF")

_UREG.define("basis_point = 1e-4 = bp = bps")
_UREG.define("percent_unit = 1e-2 = pct")

_PINT_ENV: Dict[str, Any] = {
    # Currencies
    "usd": _UREG.USD, "jpy": _UREG.JPY, "eur": _UREG.EUR,
    "gbp": _UREG.GBP, "cny": _UREG.CNY, "krw": _UREG.KRW,
    "inr": _UREG.INR, "aud": _UREG.AUD, "cad": _UREG.CAD, "chf": _UREG.CHF,
    # Power & Energy
    "w": _UREG.watt, "kw": _UREG.kilowatt, "mw": _UREG.megawatt,
    "gw": _UREG.gigawatt, "tw": _UREG.terawatt,
    # Data Storage
    "b_byte": _UREG.byte, "kb": _UREG.kilobyte, "mb": _UREG.megabyte,
    "gb": _UREG.gigabyte, "tb": _UREG.terabyte, "pb": _UREG.petabyte,
    # Length & Semiconductor Nodes
    "m": _UREG.meter, "km": _UREG.kilometer, "mm": _UREG.millimeter,
    "um": _UREG.micrometer, "nm": _UREG.nanometer,
    # Frequency
    "hz": _UREG.hertz, "khz": _UREG.kilohertz, "mhz": _UREG.megahertz, "ghz": _UREG.gigahertz,
    # Mass
    "g": _UREG.gram, "mg": _UREG.milligram, "ug": _UREG.microgram,
    "kg": _UREG.kilogram, "t": _UREG.metric_ton,
    # Time
    "s": _UREG.second, "ms": _UREG.millisecond, "us": _UREG.microsecond, "ns": _UREG.nanosecond,
    "min": _UREG.minute, "hr": _UREG.hour, "day": _UREG.day, "yr": _UREG.year,
    # Energy / Food
    "kcal": _UREG.kilocalorie, "cal": _UREG.calorie,
}

MULTIPLIERS_JP: Dict[str, float] = {
    "千": 1e3,
    "万": 1e4,
    "億": 1e8,
    "兆": 1e12,
}

MULTIPLIERS_EN: Dict[str, float] = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}

MULTIPLIERS_SI: Dict[str, float] = {
    "gw": 1e9, "mw": 1e6, "kw": 1e3,
    "tb": 1e12, "gb": 1e9, "mb": 1e6,
    "ghz": 1e9, "mhz": 1e6, "khz": 1e3,
    "km": 1e3, "mm": 1e-3, "um": 1e-6, "nm": 1e-9,
    "kg": 1e3, "mg": 1e-3, "ug": 1e-6,
    "ms": 1e-3, "us": 1e-6, "ns": 1e-9,
}

_SAFE_MATH_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_safe_math_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        nid = node.id.lower()
        if nid in _PINT_ENV:
            return _PINT_ENV[nid]
        raise ValueError(f"Unknown unit in formula: {node.id}")
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_MATH_OPS:
        return _SAFE_MATH_OPS[type(node.op)](_eval_safe_math_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_MATH_OPS:
        left = _eval_safe_math_node(node.left)
        right = _eval_safe_math_node(node.right)
        return _SAFE_MATH_OPS[type(node.op)](left, right)
    raise ValueError("Unsupported AST node in derivation formula")


def _sanitize_formula(expr: str) -> str:
    """Normalize formula string, replacing scales and unit surfaces with valid AST tokens."""
    cleaned = unicodedata.normalize("NFKC", expr).lower().strip()

    # Scale words (e.g. 83B, 20.1兆, 50 million)
    for u, mult in (
        ("兆", 1e12), ("trillion", 1e12), ("tn", 1e12),
        ("億", 1e8), ("万", 1e4),
        ("billion", 1e9), ("bn", 1e9), ("b", 1e9),
        ("million", 1e6), ("mn", 1e6), ("m", 1e6),
        ("thousand", 1e3), ("k", 1e3),
    ):
        patt = rf"(\d+(?:\.\d+)?)\s*{u}\b" if u.isascii() else rf"(\d+(?:\.\d+)?)\s*{u}"
        cleaned = re.sub(patt, rf"(\1 * {mult:e})", cleaned)

    # Compound currency exchange rates (e.g. 157.47 JPY/USD or 円/ドル)
    for r_pat, r_unit in (
        (r"(?:円/ドル|jpy/usd)", "(jpy / usd)"),
        (r"(?:ドル/円|usd/jpy)", "(usd / jpy)"),
        (r"(?:ユーロ/ドル|eur/usd)", "(eur / usd)"),
        (r"(?:ドル/ユーロ|usd/eur)", "(usd / eur)"),
    ):
        cleaned = re.sub(rf"(\d+(?:\.\d+)?|\([^)]+\))\s*{r_pat}", rf"( * {r_unit})", cleaned)
        cleaned = re.sub(rf"{r_pat}", r_unit, cleaned)

    # Physical & scientific units
    for pat, unit in (
        (r"(?:ドル|\busd\b)", "usd"), (r"(?:円|\bjpy\b)", "jpy"),
        (r"(?:ユーロ|\beur\b)", "eur"), (r"(?:ポンド|\bgbp\b)", "gbp"),
        (r"(?:元|\bcny\b)", "cny"), (r"(?:ウォン|\bkrw\b)", "krw"),
        (r"(?:ルピー|\binr\b)", "inr"),
        (r"(?:gw|ギガワット)\b", "gw"), (r"(?:mw|メガワット)\b", "mw"),
        (r"(?:kw|キロワット)\b", "kw"), (r"(?:w|ワット)\b", "w"),
        (r"(?:tb|テラバイト)\b", "tb"), (r"(?:gb|ギガバイト)\b", "gb"),
        (r"(?:mb|メガバイト)\b", "mb"), (r"(?:kb|キロバイト)\b", "kb"),
        (r"(?:nm|ナノメートル)\b", "nm"), (r"(?:um|マイクロメートル)\b", "um"),
        (r"(?:mm|ミリメートル)\b", "mm"), (r"(?:km|キロメートル)\b", "km"),
        (r"(?:ghz|ギガヘルツ)\b", "ghz"), (r"(?:mhz|メガヘルツ)\b", "mhz"),
        (r"(?:khz|キロヘルツ)\b", "khz"), (r"(?:hz|ヘルツ)\b", "hz"),
        (r"(?:mg|ミリグラム)\b", "mg"), (r"(?:kg|キログラム)\b", "kg"),
        (r"(?:kcal|キロカロリー)\b", "kcal"),
    ):
        cleaned = re.sub(rf"(\d+(?:\.\d+)?|\([^)]+\))\s*{pat}", rf"(\1 * {unit})", cleaned)

    # Prefix currency symbols: $100, ¥1000, €50, £20
    for sym, unit in (
        (r"[\$]", "usd"), (r"[¥￥]", "jpy"), (r"[€]", "eur"), (r"[£]", "gbp")
    ):
        cleaned = re.sub(rf"{sym}\s*(\d+(?:\.\d+)?|\([^)]+\))", rf"(\1 * {unit})", cleaned)

    cleaned = cleaned.replace("%", "").replace(",", "").strip()
    return cleaned


def eval_safe_quantity(expr: str) -> Any:
    """Safely parse and evaluate dimensional arithmetic returning Pint Quantity or float."""
    if not expr or not expr.strip():
        return None
    cleaned = _sanitize_formula(expr)
    try:
        tree = ast.parse(cleaned, mode="eval")
        return _eval_safe_math_node(tree.body)
    except Exception:
        return None


def eval_safe_arithmetic(expr: str) -> float | None:
    """Safely parse and evaluate dimensional arithmetic returning magnitude float."""
    val = eval_safe_quantity(expr)
    if val is None:
        return None
    try:
        return float(getattr(val, "magnitude", val))
    except Exception:
        return None


def extract_token_magnitudes(text: str, table_scale: float = 1.0) -> Dict[str, List[float]]:
    """Map raw numeric string tokens to their scaled values based on following unit or fractions."""
    norm = unicodedata.normalize("NFKC", text).lower()
    norm = re.sub(r"(\d{4}-\d{2}-\d{2}),", r"\1 ", norm)
    norm = re.sub(r"(?<=\d),(?=\d)", "", norm)
    token_mags: Dict[str, List[float]] = {}

    # Japanese scale multipliers
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*([千万億兆])", norm):
        val_str = m.group(1)
        scale = MULTIPLIERS_JP[m.group(2)]
        token_mags.setdefault(val_str, []).append(float(val_str) * scale)

    # English scale multipliers
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(k|thousand|mn?|million|bn?|billion|tn?|trillion)\b", norm):
        val_str = m.group(1)
        scale = MULTIPLIERS_EN[m.group(2)]
        token_mags.setdefault(val_str, []).append(float(val_str) * scale)

    # Scientific and physical units (capture both raw magnitude and SI-scaled magnitude)
    for m in re.finditer(
        r"(\d+(?:\.\d+)?)\s*(gw|mw|kw|w|tb|gb|mb|kb|ghz|mhz|khz|hz|km|mm|um|nm|kg|mg|ug|kcal|fps)(?![a-zA-Z0-9_])",
        norm,
    ):
        val_str = m.group(1)
        u_str = m.group(2)
        raw_val = float(val_str)
        token_mags.setdefault(val_str, []).append(raw_val)
        if u_str in MULTIPLIERS_SI:
            token_mags.setdefault(val_str, []).append(raw_val * MULTIPLIERS_SI[u_str])

    # Fractions (e.g. 3分の1)
    for m in re.finditer(r"(\d+)\s*分の\s*(\d+)", norm):
        denom, numer = float(m.group(1)), float(m.group(2))
        if denom > 0:
            token_mags.setdefault(f"{int(denom)}分の{int(numer)}", []).append(numer / denom)

    # Half phrases
    if "半額" in norm or "半分" in norm:
        token_mags.setdefault("半額", []).append(0.5)
        token_mags.setdefault("半分", []).append(0.5)

    # Percentages (capture both surface percentage value and ratio fraction)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*[%％]", norm):
        val_f = float(m.group(1))
        token_mags.setdefault(m.group(1), []).extend([val_f, val_f / 100.0])

    # Explicit currency values (e.g. $30, 30ドル, 4700円)
    for m in re.finditer(r"(?:[\$¥€£]\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:ドル|円|ユーロ|ポンド|usd|jpy|eur|gbp))", norm):
        tok = m.group(1) or m.group(2)
        token_mags.setdefault(tok, []).append(float(tok))

    # Standard counts and quantities
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:人|名|社|台|件|回|点|個|本|shares?|users?|people|jobs?)", norm):
        token_mags.setdefault(m.group(1), []).append(float(m.group(1)))

    # Scoped table scale (e.g. in millions)
    effective_scale = 1e6 if ("in millions" in norm or "(in millions)" in norm) else table_scale
    if effective_scale > 1.0:
        for m in re.finditer(r"\b(\d{4,6}(?:\.\d+)?)\b", norm):
            val_str = m.group(1)
            # Skip calendar years 1900-2099 unless in parentheses
            if len(val_str) == 4 and val_str.isdigit() and 1900 <= int(val_str) <= 2099:
                if not re.search(rf"\(\s*{val_str}\s*\)", norm):
                    continue
            token_mags.setdefault(val_str, []).append(float(val_str) * effective_scale)

    return token_mags


def extract_scaled_magnitudes(text: str, table_scale: float = 1.0) -> List[float]:
    """Extract canonical numerical magnitudes."""
    tm = extract_token_magnitudes(text, table_scale=table_scale)
    return [mag for mags in tm.values() for mag in mags]


# Regex detecting salient, domain-checkable assertions:
# - scaled numbers (万/億/兆/k/m/b/t)
# - percentages (% / ％ / bps)
# - multipliers (倍 / x / 半額 / 半分)
# - physical / tech / scientific units (GW, TB, nm, GHz, kW, etc.)
_SALIENT_FIGURE_PATT = re.compile(
    r"(?:"
    r"(\d+(?:\.\d+)?)\s*[千万億兆](?:円|ドル)?|"
    r"(\d+(?:\.\d+)?)\s*(?:billion|million|trillion|thousand|[kmb]|gw|mw|kw|w|tb|gb|mb|kb|nm|um|mm|km|ghz|mhz|khz|mg|kg|kcal|fps)(?![a-zA-Z0-9_])|"
    r"(\d+(?:\.\d+)?)\s*[%％]|"
    r"(\d+(?:\.\d+)?)\s*(?:bps|basis\s+points?)\b|"
    r"(\d+(?:\.\d+)?)\s*(?:倍|x)\b|"
    r"[$¥€£]\s*(\d+(?:\.\d+)?)|"
    r"(\d+(?:\.\d+)?)\s*(?:ドル|円|ユーロ|ポンド)|"
    r"(\d+\s*分の\s*\d+)|"
    r"(半額|半分|倍増|半減)"
    r")",
    re.I,
)


def extract_salient_figures(text: str) -> List[Tuple[str, float, str]]:
    """Extract salient, verifiable figures with unit/kind from human-facing text.

    Returns tuples: (raw_token, canonical_numeric_value, kind_or_unit).
    Excludes layout dimensions (1920x1080), hex colors, cut indices, and calendar years.
    """
    if not text:
        return []
    norm = unicodedata.normalize("NFKC", text)
    # Strip hex colors
    norm = re.sub(r"#[0-9a-fA-F]{3,8}\b", "", norm)
    # Strip resolution patterns (e.g. 1920x1080, 1080x1920)
    norm = re.sub(r"\b\d{3,4}\s*[xX×]\s*\d{3,4}\b", "", norm)

    mags_map = extract_token_magnitudes(norm)
    salient: List[Tuple[str, float, str]] = []

    for m in _SALIENT_FIGURE_PATT.finditer(norm):
        raw_match = m.group(0).strip()
        matched_token = next((g for g in m.groups() if g is not None), raw_match)
        # Determine value
        val: Optional[float] = None
        if matched_token in mags_map and mags_map[matched_token]:
            val = mags_map[matched_token][0]
        else:
            try:
                num_part = re.search(r"\d+(?:\.\d+)?", matched_token)
                if num_part:
                    val = float(num_part.group(0))
            except Exception:
                pass
        if val is not None:
            salient.append((matched_token, val, raw_match))

    return salient
_UNIT_PATTERNS: List[Tuple[re.Pattern, Any]] = [
    # Currencies
    (re.compile(r"[\$]|(?:\b(?:usd|dollars?)\b|ドル)(?![a-zA-Z0-9_])", re.I), _UREG.USD),
    (re.compile(r"[¥￥]|(?:\b(?:jpy|yen)\b|円)(?![a-zA-Z0-9_])", re.I), _UREG.JPY),
    (re.compile(r"[€]|(?:\b(?:eur|euros?)\b|ユーロ)(?![a-zA-Z0-9_])", re.I), _UREG.EUR),
    (re.compile(r"[£]|(?:\b(?:gbp|pounds?)\b|ポンド)(?![a-zA-Z0-9_])", re.I), _UREG.GBP),
    (re.compile(r"(?:\b(?:cny|yuan|rmb)\b|元)(?![a-zA-Z0-9_])", re.I), _UREG.CNY),
    # Power
    (re.compile(r"(?:\b(?:gw|gigawatts?)\b|ギガワット)(?![a-zA-Z0-9_])", re.I), _UREG.gigawatt),
    (re.compile(r"(?:\b(?:mw|megawatts?)\b|メガワット)(?![a-zA-Z0-9_])", re.I), _UREG.megawatt),
    (re.compile(r"(?:\b(?:kw|kilowatts?)\b|キロワット)(?![a-zA-Z0-9_])", re.I), _UREG.kilowatt),
    (re.compile(r"(?:\b(?:w|watts?)\b|ワット)(?![a-zA-Z0-9_])", re.I), _UREG.watt),
    # Storage
    (re.compile(r"(?:\b(?:tb|terabytes?)\b|テラバイト)(?![a-zA-Z0-9_])", re.I), _UREG.terabyte),
    (re.compile(r"(?:\b(?:gb|gigabytes?)\b|ギガバイト)(?![a-zA-Z0-9_])", re.I), _UREG.gigabyte),
    (re.compile(r"(?:\b(?:mb|megabytes?)\b|メガバイト)(?![a-zA-Z0-9_])", re.I), _UREG.megabyte),
    (re.compile(r"(?:\b(?:kb|kilobytes?)\b|キロバイト)(?![a-zA-Z0-9_])", re.I), _UREG.kilobyte),
    # Length & Semiconductor Nodes
    (re.compile(r"(?:\b(?:nm|nanometers?)\b|ナノメートル)(?![a-zA-Z0-9_])", re.I), _UREG.nanometer),
    (re.compile(r"(?:\b(?:um|micrometers?)\b|マイクロメートル)(?![a-zA-Z0-9_])", re.I), _UREG.micrometer),
    (re.compile(r"(?:\b(?:mm|millimeters?)\b|ミリメートル)(?![a-zA-Z0-9_])", re.I), _UREG.millimeter),
    (re.compile(r"(?:\b(?:km|kilometers?)\b|キロメートル)(?![a-zA-Z0-9_])", re.I), _UREG.kilometer),
    # Frequency
    (re.compile(r"(?:\b(?:ghz|gigahertz)\b|ギガヘルツ)(?![a-zA-Z0-9_])", re.I), _UREG.gigahertz),
    (re.compile(r"(?:\b(?:mhz|megahertz)\b|メガヘルツ)(?![a-zA-Z0-9_])", re.I), _UREG.megahertz),
    (re.compile(r"(?:\b(?:khz|kilohertz)\b|キロヘルツ)(?![a-zA-Z0-9_])", re.I), _UREG.kilohertz),
    (re.compile(r"(?:\b(?:hz|hertz)\b|ヘルツ)(?![a-zA-Z0-9_])", re.I), _UREG.hertz),
    # Mass
    (re.compile(r"(?:\b(?:kg|kilograms?)\b|キログラム)(?![a-zA-Z0-9_])", re.I), _UREG.kilogram),
    (re.compile(r"(?:\b(?:mg|milligrams?)\b|ミリグラム)(?![a-zA-Z0-9_])", re.I), _UREG.milligram),
    (re.compile(r"(?:\b(?:ug|micrograms?)\b|マイクログラム)(?![a-zA-Z0-9_])", re.I), _UREG.microgram),
    # Nutrition
    (re.compile(r"(?:\b(?:kcal|kilocalories?)\b|キロカロリー)(?![a-zA-Z0-9_])", re.I), _UREG.kilocalorie),
]


def extract_dominant_unit(text: str) -> Optional[Any]:
    """Detect primary Pint unit or currency asserted in claim or reference text."""
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)
    for pat, unit in _UNIT_PATTERNS:
        if pat.search(norm):
            return unit
    return None


_JP_AFFIRMATIVE_IDIOMS = re.compile(
    r"(?:少なくない|悪くない|珍しくない|間違いない|違いない|せざるを得ない|ほかない|しかない|問題ない|疑いない)"
)
_EN_AFFIRMATIVE_IDIOMS = re.compile(
    r"\b(?:not\s+only|no\s+less\s+than|no\s+fewer\s+than|nothing\s+short\s+of)\b",
    re.I,
)

_JP_NEG_KEYWORDS = frozenset({
    "否定", "誤り", "デマ", "虚偽", "未確認", "不十分",
    "届かない", "満たない", "達しない", "失敗", "却下"
})

_EN_NEG_PATT = re.compile(
    r"\b(?:not|never|no|none|neither|without|failed|fails|denies|denied|untrue|false|myth)\b|\bn't\b",
    re.I,
)

_CLAUSE_SPLIT_PATT = re.compile(
    r"(?:[。！？!?;\n]+|(?<=[^\d]),|(?<=[^\d])、|(?:が|けど|けれど|ものの|しかし|ただし)[、\s]|,\s*(?:but|while|although)\s+)",
    re.I,
)


def extract_content_lemmas(text: str) -> List[str]:
    """Extract content lemmas (nouns, verbs, adjectives base forms) and alphanumeric tokens."""
    if not text:
        return []
    norm = unicodedata.normalize("NFKC", text)
    lemmas: List[str] = []

    if _MECAB_TAGGER is not None:
        try:
            node = _MECAB_TAGGER.parseToNode(norm)
            while node:
                surf = node.surface
                feat = node.feature.split(",")
                pos = feat[0]
                if pos in ("名詞", "動詞", "形容詞"):
                    subpos = feat[1] if len(feat) > 1 else ""
                    if subpos not in ("非自立", "代名詞", "数"):
                        base = feat[6] if len(feat) > 6 and feat[6] != "*" else surf
                        if len(base) >= 2 or (pos in ("動詞", "形容詞") and len(base) >= 1):
                            lemmas.append(base.lower())
                elif pos == "未知語" and len(surf) >= 2:
                    lemmas.append(surf.lower())
                node = node.next
        except Exception:
            pass

    latin_tokens = re.findall(r"[a-z0-9_]{3,}", norm.lower())
    num_tokens = re.findall(r"\d+(?:\.\d+)?", norm)

    if not lemmas:
        kanji = re.findall(r"[\u4e00-\u9fff]{2,}", norm)
        katakana = re.findall(r"[\u30a0-\u30ff]{2,}", norm)
        lemmas.extend(kanji + katakana)

    return list(dict.fromkeys(lemmas + latin_tokens + num_tokens))


def has_clause_negation(text: str, target_tokens: Sequence[str] = ()) -> bool:
    """Return True if clause(s) associated with target_tokens express grammatical negation."""
    if not text:
        return False
    clauses = [c.strip() for c in _CLAUSE_SPLIT_PATT.split(text) if c.strip()]
    if not clauses:
        clauses = [text.strip()]

    target_norm = [t.lower().strip() for t in target_tokens if t.strip()]

    relevant_clauses = []
    if target_norm:
        for cl in clauses:
            cl_lower = cl.lower()
            if any(t in cl_lower for t in target_norm):
                relevant_clauses.append(cl)
    if not relevant_clauses:
        relevant_clauses = clauses

    for cl in relevant_clauses:
        cleaned = _JP_AFFIRMATIVE_IDIOMS.sub("", cl)
        cleaned = _EN_AFFIRMATIVE_IDIOMS.sub("", cleaned)
        if _EN_NEG_PATT.search(cleaned):
            return True
        if any(kw in cleaned for kw in _JP_NEG_KEYWORDS):
            return True
        if _MECAB_TAGGER is not None:
            try:
                node = _MECAB_TAGGER.parseToNode(cleaned)
                while node:
                    feat = node.feature.split(",")
                    pos = feat[0]
                    base = feat[6] if len(feat) > 6 else ""
                    if pos == "助動詞" and base in ("ない", "ぬ", "ん"):
                        return True
                    if pos == "動詞" and base in ("ない",):
                        return True
                    node = node.next
            except Exception:
                pass
        else:
            if re.search(r"(?:ではない|じゃない|ではなく|ありません|なかった|未確認|[てからけせれて]ない|[かさたなまらわ]ない)", cleaned):
                return True
    return False
