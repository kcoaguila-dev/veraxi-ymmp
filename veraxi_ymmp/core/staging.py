"""
veraxi-ymmp Staging and Presentation Engine.

Handles virtual camera framing, inter-cut acoustic tempo sculpting,
and procedural sound design cues.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from veraxi_ymmp.core.ir import CameraShotIR, DynamicAudioClip


def calculate_cut_padding(
    entry: Dict[str, Any],
    prev_entry: Optional[Dict[str, Any]],
    base_padding: float,
    punchline_pause: float,
) -> float:
    """
    Calculates acoustic padding between dialogue cuts.
    Replaces static dead air with high-retention zero-gap clamping:
    - Micro-reaction cuts (<= 12 chars): 0.0s for immediate snappy interruption
    - Comedic drops: 0.25s dead silence when Metan delivers a cold roast followed by Zundamon
    - Rapid ping-pong: clamped to base_padding (~0.05s)
    """
    text = str(entry.get("text", ""))
    cleaned_len = len(text.strip("「」 \n\t"))
    if cleaned_len <= 12:
        return 0.0

    if prev_entry:
        prev_char = str(prev_entry.get("character", ""))
        prev_emo = str(prev_entry.get("emotion", ""))
        prev_txt = str(prev_entry.get("text", ""))
        cur_char = str(entry.get("character", ""))
        is_metan_roast = ("めたん" in prev_char or "metan" in prev_char.lower()) and (
            prev_emo in ("smug", "angry")
            or any(k in prev_txt for k in ("おめでたい", "養分", "カモ", "能天気", "甘い", "底値"))
        )
        is_zunda_reactor = "ずんだ" in cur_char or "zunda" in cur_char.lower()
        if is_metan_roast and is_zunda_reactor:
            return punchline_pause

    return base_padding


def resolve_camera_shot(
    entry: Dict[str, Any],
    cut_idx: int,
    start_frame: int,
    length: int,
    has_slide: bool,
) -> CameraShotIR:
    """
    Resolves virtual camera framing, zoom, and punch-in angles for each cut.
    Enforces the 3-second optical reset invariant without static visual stagnation.
    """
    char = str(entry.get("character", ""))
    emo = str(entry.get("emotion", "normal"))
    text = str(entry.get("text", ""))

    # 1. Slide presentation focus: when a diagram/slide is active, ensure slide is in frame
    if has_slide:
        return CameraShotIR(
            start_frame=start_frame,
            length=length,
            shot_type="slide_focus",
            zoom=1.04,
            pan_x=0.0,
            pan_y=0.0,
            shake_frames=0,
        )

    # 2. Opening hook window (Cuts 0-1): Anchor onto speaker
    if cut_idx <= 1:
        is_right = "ずんだ" in char or "zunda" in char.lower() or "つむぎ" in char
        pan_x = 180.0 if is_right else -180.0
        return CameraShotIR(
            start_frame=start_frame,
            length=length,
            shot_type="focus_speaker",
            zoom=1.12,
            pan_x=pan_x,
            pan_y=0.0,
            shake_frames=0,
        )

    # 3. Shock/Panic micro-reaction (Zundamon panic or explosive punctuation)
    is_shock = emo in ("surprised", "scared", "crying") or any(
        k in text for k in ("！？", "!?", "嘘", "助けて", "破産", "カモ", "あり得", "正気")
    )
    if is_shock and ("ずんだ" in char or "zunda" in char.lower()):
        return CameraShotIR(
            start_frame=start_frame,
            length=length,
            shot_type="punch_in_reactor",
            zoom=1.35,
            pan_x=280.0,
            pan_y=30.0,
            shake_frames=3,
        )

    # 4. Cynical/Sadistic Roast (Metan smug/mockery)
    is_roast = emo in ("smug", "angry") or any(
        k in text for k in ("おめでたい", "養分", "能天気", "甘い", "愚か")
    )
    if is_roast and ("めたん" in char or "metan" in char.lower()):
        return CameraShotIR(
            start_frame=start_frame,
            length=length,
            shot_type="focus_left",
            zoom=1.22,
            pan_x=-220.0,
            pan_y=20.0,
            shake_frames=0,
        )

    # 5. Default wide shot
    return CameraShotIR(
        start_frame=start_frame,
        length=length,
        shot_type="wide",
        zoom=1.0,
        pan_x=0.0,
        pan_y=0.0,
        shake_frames=0,
    )


def detect_sfx_for_cut(
    entry: Dict[str, Any],
    camera_shot: CameraShotIR,
    sfx_suite: Dict[str, Path],
    current_frame: int,
    fps: int,
) -> List[DynamicAudioClip]:
    """
    Detects and constructs tactile sound design clips for a dialogue cut.
    """
    clips: List[DynamicAudioClip] = []
    text = str(entry.get("text", ""))

    if camera_shot.shot_type == "punch_in_reactor" and "snap" in sfx_suite:
        clips.append(
            DynamicAudioClip(
                audio_path=sfx_suite["snap"],
                start_frame=current_frame,
                length=max(1, int(0.04 * fps)),
                volume=0.20,
            )
        )

    is_alarm_metric = any(
        k in text for k in ("損失", "暴落", "危機", "爆弾", "critical", "赤字", "粉飾", "全滅")
    )
    if is_alarm_metric and "impact" in sfx_suite:
        clips.append(
            DynamicAudioClip(
                audio_path=sfx_suite["impact"],
                start_frame=current_frame,
                length=max(1, int(0.38 * fps)),
                volume=0.35,
            )
        )

    return clips


def detect_slide_sfx(
    sfx_suite: Dict[str, Path],
    current_frame: int,
    fps: int,
) -> Optional[DynamicAudioClip]:
    """
    Constructs a whoosh transition audio clip when a slide/B-roll image appears.
    """
    if "whoosh" in sfx_suite:
        return DynamicAudioClip(
            audio_path=sfx_suite["whoosh"],
            start_frame=current_frame,
            length=max(1, int(0.28 * fps)),
            volume=0.22,
        )
    return None
