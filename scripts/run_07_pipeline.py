# -*- coding: utf-8 -*-
"""Execute full project pipeline for 07_ai_capex_market_rotation_2026."""
import sys
from pathlib import Path
from veraxi_ymmp.pipeline import ProjectPipeline
from veraxi_ymmp.voicevox import VoicevoxClient

def main():
    proj_dir = Path("projects/07_ai_capex_market_rotation_2026")
    print(f"Starting pipeline for {proj_dir}...")
    pipeline = ProjectPipeline(
        template_path="examples/full_template.ymmp",
        voicevox_client=VoicevoxClient("http://127.0.0.1:50021"),
        use_tts=True,
        fast_qa_duration=30.0
    )
    result = pipeline.run(
        proj_dir,
        do_premiere=True,
        do_ymmp=True,
        do_qa=True,
        do_thumbnail=True
    )
    print("Pipeline finished.")
    print("Success:", result.success)
    print("Errors:", result.errors)
    print("Audio files count:", len(result.audio_files))
    print("YMMP:", result.ymmp_path)
    print("Premiere XML:", result.premiere_xml)
    print("QA video:", result.qa_video_path)
    print("Thumbnail:", result.thumbnail_path)
    if not result.success:
        sys.exit(1)

if __name__ == "__main__":
    main()
