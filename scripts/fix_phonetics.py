# -*- coding: utf-8 -*-
"""
Fast, zero-AI phonetic fix and YMMP rebuild utility.

Usage examples:
  # 1. Rebuild YMMP & audio for any lines affected by phonetics_dict.json or inline {漢字|よみ}:
  python scripts/fix_phonetics.py projects/07_ai_capex_market_rotation_2026

  # 2. Add a phonetic rule to phonetics_dict.json and immediately rebuild affected audio + YMMP (<2s):
  python scripts/fix_phonetics.py projects/07_ai_capex_market_rotation_2026 --add "行ってください=おこなってください" --add "買った分=買ったぶん"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from veraxi_ymmp.phonetics import DEFAULT_PHONETICS_DICT_PATH, normalize_tts_text
from veraxi_ymmp.pipeline import ProjectPipeline
from veraxi_ymmp.voicevox import VoicevoxClient


def update_phonetics_dict(dict_path: Path, additions: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    if dict_path.exists():
        data = json.loads(dict_path.read_text(encoding="utf-8-sig"))
    for item in additions:
        if "=" not in item:
            raise ValueError(f"Invalid --add format '{item}'. Expected '漢字=よみ'.")
        surface, reading = item.split("=", 1)
        data[surface.strip()] = reading.strip()
    dict_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Systematically fix TTS phonetics and rebuild YMM4/Premiere timelines in seconds."
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to the project directory (e.g. projects/07_ai_capex_market_rotation_2026)",
    )
    parser.add_argument(
        "--add",
        action="append",
        default=[],
        help="Add a 'surface=reading' mapping to phonetics_dict.json before rebuilding.",
    )
    parser.add_argument(
        "--project-dict",
        action="store_true",
        help="Write --add entries to <project_dir>/phonetics_dict.json instead of global veraxi_ymmp/phonetics_dict.json.",
    )
    parser.add_argument(
        "--voicevox-url",
        default="http://127.0.0.1:50021",
        help="VOICEVOX Engine URL (default: http://127.0.0.1:50021)",
    )
    args = parser.parse_args()

    proj_dir = args.project_dir.resolve()
    if not proj_dir.exists():
        print(f"Error: Project directory not found: {proj_dir}", file=sys.stderr)
        sys.exit(1)

    if args.add:
        target_dict = (proj_dir / "phonetics_dict.json") if args.project_dict else DEFAULT_PHONETICS_DICT_PATH
        updated = update_phonetics_dict(target_dict, args.add)
        print(f"Updated {target_dict} ({len(updated)} total rules).")

    # Preview which script lines have phonetic transformations applied
    script_path = proj_dir / "script.json"
    if script_path.exists():
        entries = json.loads(script_path.read_text(encoding="utf-8-sig"))
        transformed_count = 0
        for idx, entry in enumerate(entries):
            if "text" not in entry:
                continue
            raw = entry["text"]
            tts = normalize_tts_text(raw, project_dir=proj_dir)
            if tts != raw:
                transformed_count += 1
                print(f"  [Line {idx:03d}] Subtitle: {raw}")
                print(f"             TTS Read: {tts}")
        print(f"Phonetic normalization active on {transformed_count} script lines.")

    pipeline = ProjectPipeline(
        template_path="examples/full_template.ymmp",
        voicevox_client=VoicevoxClient(args.voicevox_url),
        use_tts=True,
    )
    result = pipeline.run(
        proj_dir,
        do_premiere=True,
        do_ymmp=True,
        do_qa=False,
        do_thumbnail=False,
    )
    if not result.success:
        print(f"Errors: {result.errors}", file=sys.stderr)
        sys.exit(1)

    print(f"Rebuilt YMMP: {result.ymmp_path}")
    print(f"Rebuilt XML:  {result.premiere_xml}")


if __name__ == "__main__":
    main()
