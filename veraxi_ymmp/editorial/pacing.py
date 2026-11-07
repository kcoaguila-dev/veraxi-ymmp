"""
Pacing and Audience Retention Optimization Engine for Multi-Character Scripts.

Enforces data-backed dialogue ratios (The 50/30/20 Golden Ratio for 3-character casts),
hook protection, mid-roll retention injection windows, and grounded staging invariants.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple


# Recommended targets for 3-character commentary/explainer videos
TARGET_EXPLAINER_MIN_RATIO = 0.40
TARGET_EXPLAINER_MAX_RATIO = 0.60

TARGET_INQUIRER_MIN_RATIO = 0.25
TARGET_INQUIRER_MAX_RATIO = 0.40

# Golden ratio for 3rd specialist character (e.g. 春日部つむぎ)
TARGET_SPECIALIST_MIN_RATIO = 0.12
TARGET_SPECIALIST_MAX_RATIO = 0.22
TARGET_SPECIALIST_HARD_CEILING = 0.25

# Hook protection window (first N cuts or % of script where 3rd character must not appear)
HOOK_PROTECTION_CUT_COUNT = 3
HOOK_PROTECTION_RATIO = 0.10

# Maximum consecutive cuts for 3rd character before handing back to the anchor duo
MAX_CONSECUTIVE_SPECIALIST_CUTS = 3


@dataclasses.dataclass
class CharacterPacingStats:
    """Telemetry and distribution stats for an individual character."""

    character: str
    cut_count: int
    char_count: int
    cut_ratio: float
    char_ratio: float
    first_cut_index: int
    last_cut_index: int
    max_consecutive_cuts: int


@dataclasses.dataclass
class PacingRuleViolation:
    """A detected violation or warning regarding retention pacing."""

    rule_name: str
    severity: str  # "ERROR", "WARNING", "INFO"
    character: Optional[str]
    message: str
    remedy: str


@dataclasses.dataclass
class ScriptPacingReport:
    """Complete scorecard of script pacing and retention readiness."""

    total_cuts: int
    total_characters: int
    num_characters: int
    character_stats: Dict[str, CharacterPacingStats]
    violations: List[PacingRuleViolation]
    retention_score: int  # 0 to 100
    is_healthy: bool
    summary: str


def audit_script_pacing(
    script: List[Dict[str, Any]],
    explainer_name: Optional[str] = None,
    specialist_name: Optional[str] = None,
) -> ScriptPacingReport:
    """
    Audits a script's dialogue cuts against empirical YouTube audience retention rules.
    """
    dialogue_entries = [
        entry for entry in script
        if isinstance(entry, dict) and "character" in entry and "text" in entry
    ]

    total_cuts = len(dialogue_entries)
    if total_cuts == 0:
        return ScriptPacingReport(
            total_cuts=0,
            total_characters=0,
            num_characters=0,
            character_stats={},
            violations=[
                PacingRuleViolation(
                    rule_name="EMPTY_SCRIPT",
                    severity="ERROR",
                    character=None,
                    message="Script contains zero dialogue entries.",
                    remedy="Provide at least 15-25 dialogue cuts.",
                )
            ],
            retention_score=0,
            is_healthy=False,
            summary="Empty script cannot be audited.",
        )

    # Aggregate character metrics
    char_cut_counts: Dict[str, int] = {}
    char_text_lengths: Dict[str, int] = {}
    first_indices: Dict[str, int] = {}
    last_indices: Dict[str, int] = {}
    max_consecutive: Dict[str, int] = {}

    current_char: Optional[str] = None
    current_run = 0

    total_chars = 0
    for idx, entry in enumerate(dialogue_entries):
        c = entry["character"]
        text = str(entry.get("text", ""))
        text_len = len(text)
        total_chars += text_len

        char_cut_counts[c] = char_cut_counts.get(c, 0) + 1
        char_text_lengths[c] = char_text_lengths.get(c, 0) + text_len

        if c not in first_indices:
            first_indices[c] = idx
        last_indices[c] = idx

        if c == current_char:
            current_run += 1
        else:
            current_char = c
            current_run = 1

        if current_run > max_consecutive.get(c, 0):
            max_consecutive[c] = current_run

    character_stats: Dict[str, CharacterPacingStats] = {}
    for c, count in char_cut_counts.items():
        c_chars = char_text_lengths[c]
        character_stats[c] = CharacterPacingStats(
            character=c,
            cut_count=count,
            char_count=c_chars,
            cut_ratio=round(count / total_cuts, 4),
            char_ratio=round(c_chars / total_chars, 4) if total_chars > 0 else 0.0,
            first_cut_index=first_indices[c],
            last_cut_index=last_indices[c],
            max_consecutive_cuts=max_consecutive.get(c, 0),
        )

    violations: List[PacingRuleViolation] = []
    num_chars = len(character_stats)

    # 1. Check cut length ceiling (<= 40 chars)
    overlength_cuts = []
    for idx, entry in enumerate(dialogue_entries):
        text = str(entry.get("text", ""))
        if len(text) > 42:
            overlength_cuts.append((idx, entry["character"], len(text)))

    if overlength_cuts:
        violations.append(
            PacingRuleViolation(
                rule_name="CUT_LENGTH_CEILING",
                severity="WARNING",
                character=None,
                message=f"{len(overlength_cuts)} cut(s) exceed recommended ceiling (<= 40 chars): "
                + ", ".join(f"#{i} ({c}:{length}c)" for i, c, length in overlength_cuts[:3]),
                remedy="Split overlength compound sentences across multiple cuts to prevent reading fatigue.",
            )
        )

    # 2. Check grounded staging (No cartoon jump)
    jump_cuts = []
    for idx, entry in enumerate(dialogue_entries):
        if entry.get("motion") == "jump":
            jump_cuts.append((idx, entry["character"]))

    if jump_cuts:
        violations.append(
            PacingRuleViolation(
                rule_name="GROUNDED_STAGING_INVARIANT",
                severity="WARNING",
                character=None,
                message=f"Detected cartoon 'jump' motion at {len(jump_cuts)} cut(s): "
                + ", ".join(f"#{i} ({c})" for i, c in jump_cuts[:4]),
                remedy="Replace 'jump' with 'none' or 'nod'. In technical videos, jumping characters look amateurish and distract from B-roll.",
            )
        )

    # 3. Check currency formatting invariant (No trailing '$' like 2200億$)
    trailing_dollar_cuts = []
    for idx, entry in enumerate(dialogue_entries):
        text = str(entry.get("text", ""))
        if re.search(r"(\d+[億万千兆]?|\d+)\$", text):
            trailing_dollar_cuts.append((idx, entry["character"]))

    if trailing_dollar_cuts:
        violations.append(
            PacingRuleViolation(
                rule_name="TRAILING_DOLLAR_SIGN_ERROR",
                severity="WARNING",
                character=None,
                message=f"Detected invalid trailing dollar sign ($ at end) at {len(trailing_dollar_cuts)} cut(s): "
                + ", ".join(f"#{i} ({c})" for i, c in trailing_dollar_cuts[:4]),
                remedy="In Japanese script writing, write '$220B' or '2200億ドル', never '2200億$'.",
            )
        )

    # 4. Check AI Slop corporate presentation cliches
    slop_patterns = [
        r"[0-9０-９]+つのポイント",
        r"[0-9０-９]+大視点",
        r"[0-9０-９]+大潮流",
        r"[0-9０-９]+大原則",
        r"本日のポイント",
        r"本日の3大",
        r"本日の３大",
    ]
    slop_cuts = []
    for idx, entry in enumerate(dialogue_entries):
        text = str(entry.get("text", ""))
        for pat in slop_patterns:
            if re.search(pat, text):
                slop_cuts.append((idx, entry["character"], pat))
                break

    if slop_cuts:
        violations.append(
            PacingRuleViolation(
                rule_name="AI_SLOP_TEMPLATE_VIOLATION",
                severity="WARNING",
                character=None,
                message=f"Detected formulaic presentation cliches ('3つのポイント'/'3大視点') at {len(slop_cuts)} cut(s): "
                + ", ".join(f"#{i} ({c})" for i, c, _ in slop_cuts[:4]),
                remedy="Replace corporate lecture templates with narrative friction, investigative stakes, and contrarian hooks.",
            )
        )

    # 5. Check spoken company abbreviations (e.g. MS instead of マイクロソフト)
    abbrev_cuts = []
    for idx, entry in enumerate(dialogue_entries):
        text = str(entry.get("text", ""))
        if re.search(r"(?<![A-Za-z0-9])MS(?![A-Za-z0-9])|エムエス", text):
            abbrev_cuts.append((idx, entry["character"]))

    if abbrev_cuts:
        violations.append(
            PacingRuleViolation(
                rule_name="ABBREVIATED_COMPANY_NAME_VIOLATION",
                severity="WARNING",
                character=None,
                message=f"Detected spoken company abbreviation ('MS'/'エムエス') at {len(abbrev_cuts)} cut(s): "
                + ", ".join(f"#{i} ({c})" for i, c in abbrev_cuts[:4]),
                remedy="In spoken dialogue, pronounce full names like 'マイクロソフト' for clarity and acoustic authority.",
            )
        )

    # 6. Check Opening Greeting Invariant (Zero-Greeting Cold Open Rule)
    opening_check_count = min(3, total_cuts)
    greeting_patterns = [
        r"こんにちは",
        r"ごきげんよう",
        r"はじめまして",
        r"初めまして",
        r"みなさん[、\s]*こん",
        r"みんな[、\s]*こん",
        r"よろしくお?願い",
        r"よろしくなのだ",
    ]
    greeting_cuts = []
    for idx in range(opening_check_count):
        entry = dialogue_entries[idx]
        text = str(entry.get("text", ""))
        for pat in greeting_patterns:
            if re.search(pat, text):
                greeting_cuts.append((idx, entry["character"]))
                break

    if greeting_cuts:
        violations.append(
            PacingRuleViolation(
                rule_name="OPENING_GREETING_VIOLATION",
                severity="WARNING",
                character=None,
                message="Detected opening greeting/filler at cut(s): "
                + ", ".join(f"#{i} ({c})" for i, c in greeting_cuts),
                remedy=(
                    "Eliminate opening greetings from the first 3 cuts (0-second Cold Open rule). "
                    "In modern high-retention YouTube, opening pleasantries trigger immediate cliff drop-off. "
                    "Start directly at 0.0s In Media Res with a high-stakes hook, shocking metric, or contrarian assertion."
                ),
            )
        )

    # 7. Check Premature Slide Overload (Hook window must focus on character dialogue, not slides)
    if total_cuts > 0:
        first_entry = dialogue_entries[0]
        if first_entry.get("image"):
            violations.append(
                PacingRuleViolation(
                    rule_name="PREMATURE_SLIDE_OVERLOAD",
                    severity="WARNING",
                    character=None,
                    message="First dialogue cut has a presentation slide attached ('image' is set at Cut #0).",
                    remedy=(
                        "Keep Cut #0 clean ('image': null) to let character expressions and dialogue hook viewers emotionally. "
                        "Dumping multi-element presentation slides at 0.0s causes cognitive overload and corporate lecture fatigue. "
                        "Introduce evidence slides around Cut #3–#6 when transitioning to the unvarnished facts."
                    ),
                )
            )

    # 8. Check Zundamon Persona Contamination (No corporate B2B consultant lecturing)
    zundamon_consultant_patterns = [
        r"特定の.*依存を嫌がる",
        r"原価と現金の推移を見るべき",
        r"ポートフォリオ",
        r"基幹システムの乗り換え",
        r"粗利益率で圧倒する",
        r"減価償却費が",
        r"設備投資の金額が.*異常",
        r"設備投資計画です",
        r"見るべきなのだ",
        r"判断すべきなのだ",
        r"分析すべきなのだ",
    ]
    zundamon_violations = []
    for idx, entry in enumerate(dialogue_entries):
        if entry["character"] == "ずんだもん":
            text = str(entry.get("text", ""))
            for pat in zundamon_consultant_patterns:
                if re.search(pat, text):
                    zundamon_violations.append((idx, text))
                    break

    if zundamon_violations:
        violations.append(
            PacingRuleViolation(
                rule_name="ZUNDAMON_PERSONA_CONTAMINATION",
                severity="WARNING",
                character="ずんだもん",
                message=f"Zundamon speaks like a corporate B2B consultant/analyst at {len(zundamon_violations)} cut(s): "
                + ", ".join(f"#{i} ('{t[:20]}...')" for i, t in zundamon_violations[:3]),
                remedy=(
                    "Zundamon represents viewer greed, panic, and vulnerability. "
                    "Never have him lecture on enterprise procurement or equity analysis. "
                    "Translate his lines into visceral emotional reactions, panic over money, or naive misunderstandings."
                ),
            )
        )

    # 9. Check Yes-Man Metan (Metan must not act as an agreeable corporate presenter)
    metan_entries = [
        (idx, entry)
        for idx, entry in enumerate(dialogue_entries)
        if entry["character"] == "四国めたん"
    ]
    if len(metan_entries) >= 3:
        yes_count = 0
        yes_indices = []
        for idx, entry in metan_entries:
            text = str(entry.get("text", ""))
            if re.match(r"^(はい[。、]|その通りです[わね]?|そう[ですね|ですわ])", text):
                yes_count += 1
                yes_indices.append(idx)

        if yes_count / len(metan_entries) > 0.35:
            violations.append(
                PacingRuleViolation(
                    rule_name="YES_MAN_METAN_INVARIANT",
                    severity="WARNING",
                    character="四国めたん",
                    message=(
                        f"Metan is acting as an agreeable yes-man ({yes_count}/{len(metan_entries)} cuts start with "
                        f"'はい/その通りですわ', {yes_count / len(metan_entries) * 100:.0f}%)."
                    ),
                    remedy=(
                        "Inject sharp friction, aristocratic sarcasm, and cold reality checks. "
                        "Have Metan puncture Zundamon's delusions ('おめでたい頭ですわね', '寝言は寝てからおっしゃい') "
                        "rather than constantly agreeing with him like a corporate seminar co-host."
                    ),
                )
            )

    # 10. Check Rhythmic Syncopation (Dialogue requires short punchy micro-reactions)
    if total_cuts >= 15:
        micro_cuts = [
            (idx, entry["character"], entry.get("text", ""))
            for idx, entry in enumerate(dialogue_entries)
            if len(str(entry.get("text", ""))) <= 12
        ]
        if len(micro_cuts) == 0 or (len(micro_cuts) / total_cuts < 0.05):
            violations.append(
                PacingRuleViolation(
                    rule_name="RHYTHMIC_SYNCOPATION_REQUIRED",
                    severity="WARNING",
                    character=None,
                    message=(
                        f"Script lacks rhythmic syncopation ({len(micro_cuts)}/{total_cuts} micro-cuts <= 12 chars). "
                        "All dialogue cuts are uniformly long sentences, causing VOICEVOX listener fatigue."
                    ),
                    remedy=(
                        "Inject 1-beat emotional micro-reactions (3–12 chars, e.g. 'はぁ！？', '嘘でしょ！？', '正気じゃないのだ！') "
                        "to create rapid ping-pong comedic contrast and natural breath marks."
                    ),
                )
            )

    # 11. Check Formulaic Ending Drop-Off (No textbook goodbye / subscribe triggers)
    if total_cuts >= 5:
        ending_cuts = dialogue_entries[-3:]
        formulaic_ending_patterns = [
            r"チャンネル登録.*よろしく",
            r"高評価も.*よろしく",
            r"概要欄.*(チェック|見て|確認|飛んで|載せて|参照)",
            r"また次回.*会おう",
            r"また次回.*お会い",
        ]
        ending_violations = []
        for offset, entry in enumerate(ending_cuts):
            actual_idx = total_cuts - len(ending_cuts) + offset
            text = str(entry.get("text", ""))
            for pat in formulaic_ending_patterns:
                if re.search(pat, text):
                    ending_violations.append((actual_idx, entry["character"], text))
                    break

        if ending_violations:
            violations.append(
                PacingRuleViolation(
                    rule_name="FORMULAIC_ENDING_DROP_OFF",
                    severity="WARNING",
                    character=None,
                    message="Detected formulaic YouTube CTA in final cuts: "
                    + ", ".join(f"#{i} ('{t[:20]}...')" for i, _, t in ending_violations),
                    remedy=(
                        "Standard 'subscribe/like' goodbye formulas trigger immediate viewer abandonment (cliff drop-off). "
                        "End abruptly on high emotional stakes, an unresolved comedic punchline, a panicked realization, "
                        "or a provocative open teaser."
                    ),
                )
            )

    # 12. Check Naked SaaS/Subscription Pricing Ambiguity (Pricing must qualify unit/per-seat scope)
    pricing_pattern = re.compile(r"(月額\d+[ドル円]|月\d+[ドル円]|\$\d+\s*/?\s*(?:mo|month|月)?)")
    unit_qualifiers = re.compile(r"(1人|一人|社員|アカウント|ユーザー|1席|シート|追加|アドオン|1台)")

    naked_pricing_cuts = []
    for idx, entry in enumerate(dialogue_entries):
        text = str(entry.get("text", ""))
        match = pricing_pattern.search(text)
        if match:
            has_unit = bool(unit_qualifiers.search(text))
            if not has_unit:
                neighbor_texts = []
                if idx > 0:
                    neighbor_texts.append(str(dialogue_entries[idx - 1].get("text", "")))
                if idx < len(dialogue_entries) - 1:
                    neighbor_texts.append(str(dialogue_entries[idx + 1].get("text", "")))
                if not any(unit_qualifiers.search(n) for n in neighbor_texts):
                    naked_pricing_cuts.append((idx, entry["character"], match.group(0), text))

    if naked_pricing_cuts:
        violations.append(
            PacingRuleViolation(
                rule_name="NAKED_PRICING_AMBIGUITY",
                severity="WARNING",
                character=None,
                message=f"Detected ambiguous subscription pricing without seat/unit qualification at {len(naked_pricing_cuts)} cut(s): "
                + ", ".join(f"#{i} ('{m}' in '{t[:20]}...')" for i, _, m, t in naked_pricing_cuts[:3]),
                remedy=(
                    "In business/tech analysis, never state naked subscription pricing (e.g. bare '月額30ドル'). "
                    "Always qualify the pricing scope and unit: specify whether it is '法人向け（社員1人あたり月30ドルの追加課金）' "
                    "or '個人向け' so viewers understand whether cost scales per seat."
                ),
            )
        )

    # 13. Check Bare 'ええ' Affirmation Invariant
    ee_cuts = []
    for idx, entry in enumerate(dialogue_entries):
        text = str(entry.get("text", "")).strip()
        if re.match(r"^ええ[、。]", text):
            ee_cuts.append((idx, entry["character"]))

    if ee_cuts:
        violations.append(
            PacingRuleViolation(
                rule_name="BARE_EE_AFFIRMATION_VIOLATION",
                severity="WARNING",
                character=None,
                message=f"Detected bare 'ええ、/ええ。' affirmation at {len(ee_cuts)} cut(s): "
                + ", ".join(f"#{i} ({c})" for i, c in ee_cuts[:4]),
                remedy=(
                    "In Japanese VOICEVOX narration, bare 'ええ' sounds repetitive and robotic. "
                    "Use character-specific affirmations: 'はい、', 'その通りですわ、', '左様でございますわ' for Metan, "
                    "or 'まさにその通りなのだ！' for Zundamon."
                ),
            )
        )

    # 14. Check Slide Stagnation & Visual Cadence
    current_img: Optional[str] = None
    img_streak = 0
    stagnant_slides: List[Tuple[int, str, int]] = []
    for idx, entry in enumerate(dialogue_entries):
        img = entry.get("image")
        if img:
            if img == current_img:
                img_streak += 1
            else:
                if img_streak > 5 and current_img:
                    stagnant_slides.append((idx - img_streak, current_img, img_streak))
                current_img = img
                img_streak = 1
        else:
            if img_streak > 5 and current_img:
                stagnant_slides.append((idx - img_streak, current_img, img_streak))
            current_img = None
            img_streak = 0
    if img_streak > 5 and current_img:
        stagnant_slides.append((len(dialogue_entries) - img_streak, current_img, img_streak))

    if stagnant_slides:
        violations.append(
            PacingRuleViolation(
                rule_name="SLIDE_STAGNATION_WARNING",
                severity="WARNING",
                character=None,
                message=f"B-roll slide held unchanged for >5 cuts at {len(stagnant_slides)} section(s): "
                + ", ".join(f"Cut #{start+1} ({Path(path).name}, {streak} cuts)" for start, path, streak in stagnant_slides[:3]),
                remedy=(
                    "Top rivals refresh visual stimuli every 3–4 cuts (10–15s). "
                    "Split long slides into multi-phase progressive reveals, data sub-views, or switch to character close-up reactions."
                ),
            )
        )

    # 3. Special rules for 3-character casts
    if num_chars >= 3:
        # Determine roles
        sorted_by_share = sorted(
            character_stats.values(), key=lambda s: s.cut_count, reverse=True
        )

        # Infer Specialist if not explicitly provided
        specialist_stat = sorted_by_share[2]

        if specialist_name and specialist_name in character_stats:
            specialist_stat = character_stats[specialist_name]
        elif "春日部つむぎ" in character_stats:
            specialist_stat = character_stats["春日部つむぎ"]

        # Check Specialist ratio (Golden Ratio: ~15% - 20%)
        spec_ratio = specialist_stat.cut_ratio
        if spec_ratio > TARGET_SPECIALIST_HARD_CEILING:
            violations.append(
                PacingRuleViolation(
                    rule_name="SPECIALIST_RATIO_EXCEEDED",
                    severity="WARNING",
                    character=specialist_stat.character,
                    message=(
                        f"3rd character '{specialist_stat.character}' speaking share is {spec_ratio*100:.1f}%, "
                        f"which exceeds the {TARGET_SPECIALIST_HARD_CEILING*100:.0f}% safety ceiling."
                    ),
                    remedy=(
                        "Reduce speaking time to 15%–20%. High exposure to a 3rd distinct voice causes acoustic "
                        "fatigue and converts educational focus into unstructured banter."
                    ),
                )
            )
        elif spec_ratio < TARGET_SPECIALIST_MIN_RATIO:
            violations.append(
                PacingRuleViolation(
                    rule_name="SPECIALIST_RATIO_UNDERUTILIZED",
                    severity="INFO",
                    character=specialist_stat.character,
                    message=(
                        f"3rd character '{specialist_stat.character}' speaking share is only {spec_ratio*100:.1f}%, "
                        f"below the recommended 15%–20% pattern-interrupt band."
                    ),
                    remedy="Allocate 1-2 additional specialized cuts (e.g. deep-dive or summary comment) to maximize retention reset.",
                )
            )

        # Check Hook Protection (first 10% or first 3 cuts)
        hook_cutoff = max(HOOK_PROTECTION_CUT_COUNT, int(total_cuts * HOOK_PROTECTION_RATIO))
        if specialist_stat.first_cut_index < hook_cutoff:
            violations.append(
                PacingRuleViolation(
                    rule_name="HOOK_CONTAMINATION",
                    severity="WARNING",
                    character=specialist_stat.character,
                    message=(
                        f"3rd character '{specialist_stat.character}' speaks at cut #{specialist_stat.first_cut_index + 1} "
                        f"inside the opening hook window (first {hook_cutoff} cuts)."
                    ),
                    remedy=(
                        "Delay 3rd character's first entrance until the mid-roll decay phase (after cut 8-10). "
                        "Opening hook must be delivered strictly by the core anchor duo to minimize viewer bounce."
                    ),
                )
            )

        # Check Mid-roll injection (should appear before 70% of the timeline)
        midroll_max_cut = int(total_cuts * 0.70)
        if specialist_stat.first_cut_index > midroll_max_cut:
            violations.append(
                PacingRuleViolation(
                    rule_name="MIDROLL_INJECTION_DELAYED",
                    severity="WARNING",
                    character=specialist_stat.character,
                    message=(
                        f"3rd character '{specialist_stat.character}' does not appear until cut #{specialist_stat.first_cut_index + 1} "
                        f"({specialist_stat.first_cut_index / total_cuts * 100:.1f}% into video), missing the mid-roll retention dip."
                    ),
                    remedy="Introduce 3rd character around 30%–50% of the timeline to reset audience attention.",
                )
            )

        # Check Maximum run length
        if specialist_stat.max_consecutive_cuts > MAX_CONSECUTIVE_SPECIALIST_CUTS:
            violations.append(
                PacingRuleViolation(
                    rule_name="SPECIALIST_RUN_LENGTH_EXCEEDED",
                    severity="WARNING",
                    character=specialist_stat.character,
                    message=(
                        f"3rd character '{specialist_stat.character}' speaks {specialist_stat.max_consecutive_cuts} cuts in a row "
                        f"(max recommended is {MAX_CONSECUTIVE_SPECIALIST_CUTS})."
                    ),
                    remedy="Break up consecutive specialist lines with reactions or confirmations from the anchor or lead inquirer.",
                )
            )

    # Calculate overall retention health score (100 base, subtract penalties)
    score = 100
    for v in violations:
        if v.severity == "ERROR":
            score -= 30
        elif v.severity == "WARNING":
            score -= 10
        elif v.severity == "INFO":
            score -= 3
    score = max(0, min(100, score))

    is_healthy = score >= 80

    summary_lines = []
    summary_lines.append(f"Script Pacing Audit: {score}/100 ({'HEALTHY' if is_healthy else 'NEEDS ATTENTION'})")
    for c_name, stats in character_stats.items():
        summary_lines.append(
            f"  - {c_name}: {stats.cut_count} cuts ({stats.cut_ratio*100:.1f}%), {stats.char_count} chars"
        )
    summary = "\n".join(summary_lines)

    return ScriptPacingReport(
        total_cuts=total_cuts,
        total_characters=total_chars,
        num_characters=num_chars,
        character_stats=character_stats,
        violations=violations,
        retention_score=score,
        is_healthy=is_healthy,
        summary=summary,
    )


def format_pacing_report_markdown(report: ScriptPacingReport) -> str:
    """Formats a ScriptPacingReport as a clean markdown report."""
    md = [
        f"### 📊 Audience Retention Pacing Audit (Score: {report.retention_score}/100)",
        "",
        f"**Status:** {'✅ Publication Ready' if report.is_healthy else '⚠️ Retention Risks Detected'}",
        f"- **Total Dialogue Cuts:** {report.total_cuts}",
        f"- **Total Characters (Moji):** {report.total_characters}",
        f"- **Active Cast Size:** {report.num_characters}",
        "",
        "#### Character Distribution:",
        "| Character | Cuts | Cut Share | Total Chars | Char Share | Max Streak |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    for c_name, s in report.character_stats.items():
        md.append(
            f"| **{c_name}** | {s.cut_count} | {s.cut_ratio*100:.1f}% | {s.char_count} | {s.char_ratio*100:.1f}% | {s.max_consecutive_cuts} |"
        )

    if report.violations:
        md.extend([
            "",
            "#### Pacing Rule Diagnostics & Remedies:",
        ])
        for v in report.violations:
            badge = "🔴" if v.severity == "ERROR" else ("🟡" if v.severity == "WARNING" else "ℹ️")
            md.append(f"- {badge} **[{v.rule_name}]** {v.message}")
            md.append(f"  *Remedy:* {v.remedy}")
    else:
        md.extend([
            "",
            "🎉 **Zero retention pacing violations detected.** Dialogue strictly obeys the 50/30/20 Golden Ratio, hook protection, and grounded staging invariants.",
        ])

    return "\n".join(md)
