"""Phase 4: DynamicVideoClip IR, ingest-clips, renderer/exporter support."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import veraxi_ymmp.app.clip_ingest as ci
from veraxi_ymmp.app.compiler import YMMPCompiler
from veraxi_ymmp.core.ir import DynamicVideoClip, TimelineIR, VoiceClip
from veraxi_ymmp.core.script import validate_director_script, validate_production_script

FIXTURES = Path(__file__).parent / "fixtures"
ffmpeg_required = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)


def _entry(**overrides):
    entry = {
        "character": "zundamon",
        "text": "テスト",
        "emotion": "happy",
        "motion": "none",
        "bgm": None,
        "sfx": None,
        "image": None,
    }
    entry.update(overrides)
    return entry


def test_dynamic_video_clip_dict_round_trip():
    clip = DynamicVideoClip(
        start_frame=90, length=180, video_path=Path("clips/intro.mp4"),
        clip_id="intro", in_point=1.5, out_point=7.5, muted=False,
    )
    data = clip.to_dict()
    assert data["type"] == "DynamicVideoClip"
    restored = DynamicVideoClip.from_dict(data)
    assert restored == clip
    assert restored.source_span == 6.0


def test_script_validators_accept_and_check_clip_id():
    validated = validate_director_script([_entry(clip_id="intro-clip")])
    assert validated[0]["clip_id"] == "intro-clip"
    # Absent clip_id stays absent (no new key on ordinary entries)
    assert "clip_id" not in validate_director_script([_entry()])[0]
    with pytest.raises(ValueError, match="clip_id"):
        validate_director_script([_entry(clip_id=42)])
    with pytest.raises(ValueError, match="clip_id"):
        validate_director_script([_entry(clip_id="  ")])
    prod = validate_production_script([_entry(clip_id="intro-clip")])
    assert prod[0]["clip_id"] == "intro-clip"


def test_place_video_clip_longer_and_shorter_than_cut():
    entry = {"id": "long", "path": "/x/long.mp4", "duration_sec": 10.0}
    placed = ci.place_video_clip(entry, start_frame=30, cut_frames=90, fps=30)
    assert placed.length == 90  # capped at the cut; source span not exhausted
    assert placed.out_point == 10.0

    short = {"id": "short", "path": "/x/short.mp4", "duration_sec": 2.0}
    placed_short = ci.place_video_clip(short, start_frame=0, cut_frames=90, fps=30)
    assert placed_short.length == 60  # whole clip, shorter than the cut


def _make_source_clip(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=duration=1:size=320x240:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", str(path)],
        check=True, capture_output=True,
    )


@ffmpeg_required
def test_ingest_clips_normalizes_and_hashes(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _make_source_clip(inbox / "My Intro.mp4")
    manifest = ci.ingest_clips(inbox, fps=30)

    assert manifest["rejected"] == []
    assert len(manifest["clips"]) == 1
    clip = manifest["clips"][0]
    assert clip["id"] == "my-intro"
    normalized = tmp_path / "clips" / "my-intro.mp4"
    assert normalized.exists()
    assert clip["sha256"] == hashlib.sha256(normalized.read_bytes()).hexdigest()
    assert clip["source_sha256"] == hashlib.sha256(
        (inbox / "My Intro.mp4").read_bytes()
    ).hexdigest()
    probe = ci.probe_video(normalized)
    assert probe is not None
    assert (probe["width"], probe["height"]) == (1920, 1080)
    assert probe["fps"] == pytest.approx(30.0, abs=1.0)
    assert probe["has_audio"] is True
    assert (tmp_path / "clips" / "manifest.json").exists()


@ffmpeg_required
def test_ingest_clips_rejects_corrupt_files(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "broken.mp4").write_bytes(b"this is not a video file")
    _make_source_clip(inbox / "good.mp4")
    manifest = ci.ingest_clips(inbox, fps=30)
    assert [c["id"] for c in manifest["clips"]] == ["good"]
    assert [r["source"] for r in manifest["rejected"]] == ["broken.mp4"]

    with pytest.raises(SystemExit) as excinfo:
        ci.cmd_ingest_clips([str(inbox)])
    assert excinfo.value.code == 1


def _project_with_manifest(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "audio").mkdir(parents=True)
    clips_dir = proj / "clips"
    clips_dir.mkdir()
    manifest = {
        "version": 1,
        "profile": {"width": 1920, "height": 1080, "fps": 60},
        "clips": [{
            "id": "intro-clip", "source": "intro.mp4", "file": "intro-clip.mp4",
            "duration_sec": 10.0, "width": 1920, "height": 1080, "fps": 60,
            "has_audio": True, "muted": True,
        }],
        "rejected": [],
    }
    (clips_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return proj


def test_build_ir_places_clip_referenced_by_script(tmp_path):
    proj = _project_with_manifest(tmp_path)
    script = json.loads((FIXTURES / "sample_script.json").read_text(encoding="utf-8"))
    script[1]["clip_id"] = "intro-clip"
    compiler = YMMPCompiler(str(FIXTURES / "sample_template.ymmp"))
    ir, _audio = compiler.build_ir(script, proj / "audio")

    assert len(ir.dynamic_video_clips) == 1
    placed = ir.dynamic_video_clips[0]
    cut = ir.voice_clips[1]
    assert placed.start_frame == cut.start_frame
    # 10s clip is longer than the cut: placed length is capped at the cut.
    assert placed.length == cut.length
    assert placed.clip_id == "intro-clip"
    assert placed.video_path.name == "intro-clip.mp4"


def test_build_ir_unknown_clip_id_warns_not_crashes(tmp_path):
    proj = _project_with_manifest(tmp_path)
    script = json.loads((FIXTURES / "sample_script.json").read_text(encoding="utf-8"))
    script[0]["clip_id"] = "no-such-clip"
    compiler = YMMPCompiler(str(FIXTURES / "sample_template.ymmp"))
    ir, _audio = compiler.build_ir(script, proj / "audio")
    assert ir.dynamic_video_clips == []
    assert any("no-such-clip" in w for w in compiler.warnings)


def test_ymmp_compile_emits_video_item(tmp_path):
    proj = _project_with_manifest(tmp_path)
    script = json.loads((FIXTURES / "sample_script.json").read_text(encoding="utf-8"))
    script[1]["clip_id"] = "intro-clip"
    compiler = YMMPCompiler(str(FIXTURES / "sample_template.ymmp"))
    out = proj / "out.ymmp"
    compiler.compile(script, out, audio_dir=proj / "audio")

    data = json.loads(out.read_text(encoding="utf-8"))
    items = data["Timeline"]["Items"]
    video_items = [i for i in items if "VideoItem" in i.get("$type", "")]
    assert len(video_items) == 1
    assert video_items[0]["FilePath"].endswith("intro-clip.mp4")
    assert video_items[0]["Layer"] == 2
    assert video_items[0]["Length"] > 0


def test_premiere_export_places_video_clip_with_in_point(tmp_path):
    from veraxi_ymmp.exporters.premiere_exporter import PremiereExporter

    clip_file = tmp_path / "intro-clip.mp4"
    clip_file.write_bytes(b"\x00" * 64)
    ir = TimelineIR(
        fps=60,
        total_frames=600,
        dynamic_video_clips=[
            DynamicVideoClip(
                start_frame=120, length=180, video_path=clip_file,
                clip_id="intro-clip", in_point=1.5, out_point=4.5,
            )
        ],
    )
    exporter = PremiereExporter(ir)
    result = exporter.export_xmeml_without_bubbles(tmp_path / "xml", tmp_path)
    content = result.read_text(encoding="utf-8")
    assert "intro-clip.mp4" in content
    assert "<in>90</in>" in content  # 1.5s at 60fps
    assert "<out>270</out>" in content


@ffmpeg_required
def test_moviepy_renderer_composes_video_clip(tmp_path):
    from veraxi_ymmp.exporters.moviepy_renderer import MoviePyRenderer

    src = tmp_path / "clip.mp4"
    _make_source_clip(src)
    ir = TimelineIR(fps=30, total_frames=30)
    ir.voice_clips = [
        VoiceClip(
            start_frame=0, length=30, character="Zundamon", text="Hello",
            emotion="neutral", motion="none", audio_path=None, hatsuon="hello",
            subtitle_position="bottom", subtitle_style="normal",
        )
    ]
    ir.dynamic_video_clips = [
        DynamicVideoClip(
            start_frame=0, length=30, video_path=src, clip_id="clip",
            in_point=0.0, out_point=1.0,
        )
    ]
    out_path = tmp_path / "qa_test.mp4"
    renderer = MoviePyRenderer(timeline_ir=ir)
    result = renderer.export(
        ir, out_path,
        options={"preset": "ultrafast", "crf": 28, "normalize_loudness": False},
    )
    assert out_path.exists() and out_path.stat().st_size > 0
    assert result.metadata["duration"] == 1.0


@ffmpeg_required
def test_ingest_clips_rejected_file_does_not_consume_an_id(tmp_path):
    # Regression (WP8 refactor): id assignment moved ahead of the
    # probe, so an unreadable file sharing a stem consumed the base
    # id and the surviving clip became "clip-2". Scripts reference
    # these ids, so probe failures must not take a numbering slot:
    # clip.mov sorts before clip.mp4 and is rejected; the good file
    # keeps the id "clip" it had before the refactor.
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "clip.mov").write_bytes(b"not a video")
    _make_source_clip(inbox / "clip.mp4")
    result = ci.ingest_clips(inbox)
    assert [c["id"] for c in result["clips"]] == ["clip"]
    assert [r["source"] for r in result["rejected"]] == ["clip.mov"]
