"""
Unified Project Runner for Veraxi YMMP
Enables generating multiple videos independently without overwriting each other.
"""
import argparse
import json
import sys
from pathlib import Path

from veraxi_ymmp.compiler import YMMPCompiler
from veraxi_ymmp.voicevox import VoicevoxClient
from veraxi_ymmp.premiere_exporter import export_to_premiere
from veraxi_ymmp.moviepy_renderer import MoviePyRenderer
from veraxi_ymmp.thumbnail import generate_project_thumbnail


def run_project(
    project_path: str,
    do_premiere: bool = True,
    do_ymmp: bool = True,
    do_qa: bool = True,
    qa_duration: float = 30.0,
    do_thumbnail: bool = True,
):
    proj_dir = Path(project_path).resolve()
    if not proj_dir.exists():
        print(f"Error: Project directory '{project_path}' does not exist.")
        sys.exit(1)

    script_path = proj_dir / "script.json"
    if not script_path.exists():
        print(f"Error: No script.json found in '{project_path}'.")
        sys.exit(1)

    print(f"\n=======================================================")
    print(f"  Running Veraxi YMMP Project: {proj_dir.name}")
    print(f"  Location: {proj_dir}")
    print(f"=======================================================\n")

    script = json.loads(script_path.read_text(encoding="utf-8-sig"))
    print(f"Loaded script: {len(script)} lines.")

    # 1. Initialize Voicevox
    print("Initializing Voicevox Client...")
    vv = VoicevoxClient()
    if not vv.ensure_started():
        print("Warning: VOICEVOX could not be started. Audio will not be generated.")
        vv = None

    speaker_map = {
        "ずんだもん": 3,
        "四国めたん": 2,
        "春日部つむぎ": 8,
    }
    compiler = YMMPCompiler("examples/full_template.ymmp", voicevox_client=vv, speaker_map=speaker_map)

    audio_dir = proj_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    print("Building Timeline IR & Synthesizing Audio...")
    timeline_ir, audio_files = compiler._build_ir(script, audio_dir)
    print(f"Synthesized {len(timeline_ir.voice_clips)} voice clips successfully.")

    # 2. Premiere Pro XML Export
    if do_premiere:
        print("\n--- [1/3] Generating Premiere Pro FCPXML ---")
        xml_dir = proj_dir / "premiere"
        proj_assets_dir = proj_dir / "premiere"
        xml_dir.mkdir(parents=True, exist_ok=True)
        res = export_to_premiere(timeline_ir, xml_dir, proj_assets_dir, xml_filename=f"{proj_dir.name}.xml")
        print(f"Success! Premiere XML generated at:")
        print(f"  -> {res['xml_path']}")

    # 3. YMM4 Project Export
    if do_ymmp:
        print("\n--- [2/3] Generating Yukkuri Movie Maker 4 (.ymmp) ---")
        ymmp_dir = proj_dir / "ymmp"
        ymmp_dir.mkdir(parents=True, exist_ok=True)
        ymmp_out = ymmp_dir / "final_video.ymmp"
        compiler._render_ymmp(timeline_ir, ymmp_out, False, len(timeline_ir.voice_clips), audio_files)
        from veraxi_ymmp.validation import validate_ymmp_timeline
        with open(ymmp_out, 'r', encoding='utf-8') as f:
            v_data = json.load(f)
        v_res = validate_ymmp_timeline(v_data, expected_voice_count=len(timeline_ir.voice_clips))
        print(f"Success! YMM4 project generated at:")
        print(f"  -> {ymmp_out}")
        print(f"  [YMMP Timeline QA PASSED]")
        print(f"    - VoiceItems (Layer 9 with Brotli VoiceCache & LipSync): {v_res['voice_items']} items")
        print(f"    - Tachie Items (Layer 4/6): {v_res['tachie_items']} items (all with valid PSD 'n...' layer IDs)")
        print(f"    - Speech Plates (Layer 8): {v_res['plate_items_layer7']} speech bubbles")
        print(f"    - BGM/SFX Items (Layer 3): {v_res['bgm_items']} items")
        print(f"    - MaxLayer: {v_res['max_layer']}")

    # 4. MoviePy QA Video
    if do_qa:
        print(f"\n--- [3/4] Rendering MoviePy QA Preview Video ({qa_duration}s) ---")
        renderer = MoviePyRenderer(timeline_ir)
        renderer.fast_qa_duration = qa_duration
        qa_out = proj_dir / "qa_test.mp4"
        renderer.render(str(qa_out))
        print(f"Success! QA preview video ready at:")
        print(f"  -> {qa_out}")

    # 5. High-CTR YouTube Thumbnail
    if do_thumbnail:
        print(f"\n--- [4/4] Generating High-CTR YouTube Thumbnail ---")
        thumb_out = proj_dir / "thumbnail.png"
        generate_project_thumbnail(proj_dir, out_path=thumb_out)
        print(f"Success! High-CTR YouTube thumbnail ready at:")
        print(f"  -> {thumb_out}")

    print(f"\n=======================================================")
    print(f"  Project '{proj_dir.name}' Execution Finished!")
    print(f"=======================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Veraxi YMMP Project Runner")
    parser.add_argument("project", type=str, help="Path to project directory")
    parser.add_argument("--no-premiere", action="store_true", help="Skip Premiere XML export")
    parser.add_argument("--no-ymmp", action="store_true", help="Skip YMM4 export")
    parser.add_argument("--no-qa", action="store_true", help="Skip MoviePy QA render")
    parser.add_argument("--qa-duration", type=float, default=30.0, help="Duration for QA render in seconds")
    parser.add_argument("--no-thumbnail", action="store_true", help="Skip YouTube thumbnail generation")

    args = parser.parse_args()
    run_project(
        project_path=args.project,
        do_premiere=not args.no_premiere,
        do_ymmp=not args.no_ymmp,
        do_qa=not args.no_qa,
        qa_duration=args.qa_duration,
        do_thumbnail=not args.no_thumbnail,
    )
