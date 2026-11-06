import pytest
from pathlib import Path
from veraxi_ymmp.moviepy_renderer import MoviePyRenderer
from veraxi_ymmp.ir import TimelineIR, VoiceClip

def test_headless_renderer(tmp_path: Path) -> None:
    """Test headless rendering natively from MoviePyRenderer without requiring YMM4/Premiere."""
    # Create minimal TimelineIR
    ir = TimelineIR(
        fps=60,
        total_frames=180,  # 3 seconds at 60fps
    )
    # Give some items so they can render
    ir.voice_clips = [
        VoiceClip(
            start_frame=0,
            length=60,
            character="Zundamon",
            text="Hello",
            emotion="neutral",
            motion="none",
            audio_path=None,
            hatsuon="hello",
            subtitle_position="bottom",
            subtitle_style="normal"
        )
    ]

    out_path = tmp_path / "final_video.mp4"

    renderer = MoviePyRenderer(
        timeline_ir=ir
    )

    result = renderer.export(ir, out_path, options={"preset": "ultrafast", "crf": 23, "normalize_loudness": False})

    # Assert
    assert out_path.exists(), "Output video file was not generated"
    assert out_path.stat().st_size > 0, "Output video is empty"
    assert result.target_format == "mp4"
    assert result.output_path == out_path

    # Check duration metadata
    assert result.metadata["duration"] == 3.0

if __name__ == "__main__":
    pytest.main(["-v", __file__])
