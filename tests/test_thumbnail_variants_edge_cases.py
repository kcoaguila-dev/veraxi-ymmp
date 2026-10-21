"""Adversarial and Empirical Stress-Test Suite for Milestone 1.

Written by challenger_m1_1 to empirically challenge and stress-test:
1. Domain model serialization edge cases (corrupted, missing, extra fields, extreme values).
2. Boundary conditions for validate_thumbnail_file_size (0 bytes, 2MB-1, 2MB, 2MB+1).
3. Variant configuration extraction under missing, corrupted, or overridden configurations.
4. MockYouTubeAdapter rapid rotations, interleaved multi-video rotations, and fault injection.
5. Clean Architecture and Protocol conformance.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from veraxi_ymmp.ir import (
    RotationEvent,
    ThumbnailExperiment,
    ThumbnailVariant,
    VariantMetrics,
    WinnerDecision,
)
from veraxi_ymmp.ports import (
    VideoAnalyticsProvider,
    VideoPublisher,
)
from veraxi_ymmp.thumbnail import (
    ThumbnailConfig,
    auto_extract_variant_configs,
    generate_thumbnail_variants,
    validate_thumbnail_file_size,
)
from veraxi_ymmp.youtube_adapter import (
    THUMBNAIL_MAX_SIZE_BYTES,
    MockYouTubeAdapter,
)


class TestDomainSerializationAdversarial:
    """Stress-test domain model serialization with corrupted, missing, extra, and extreme data."""

    def test_variant_metrics_empty_dict(self) -> None:
        """from_dict with empty dict should use safe defaults."""
        m = VariantMetrics.from_dict({})
        assert m.variant_id == ""
        assert m.impressions == 0
        assert m.views == 0
        assert m.ctr == 0.0
        assert m.average_view_percentage == 0.0
        assert m.average_view_duration_sec == 0.0
        assert m.retention_score == 0.0
        assert m.sample_start is None
        assert m.sample_end is None
        assert m.raw_metrics == {}

    def test_variant_metrics_extra_unknown_fields(self) -> None:
        """Forward compatibility: extra unexpected keys should be cleanly ignored."""
        data = {
            "variant_id": "test_var",
            "impressions": 100,
            "views": 25,
            "unknown_extra_1": "payload",
            "unexpected_nested": {"a": 1, "b": 2},
            "__future_feature_score": 99.9,
        }
        m = VariantMetrics.from_dict(data)
        assert m.variant_id == "test_var"
        assert m.impressions == 100
        assert m.views == 25
        assert not hasattr(m, "unknown_extra_1")

    def test_variant_metrics_numeric_string_coercion(self) -> None:
        """String-encoded numbers should be coerced to int/float."""
        data = {
            "variant_id": "A",
            "impressions": "5000",
            "views": "750",
            "ctr": "0.15",
            "average_view_percentage": "62.5",
            "average_view_duration_sec": "110.0",
            "retention_score": "0.625",
        }
        m = VariantMetrics.from_dict(data)
        assert m.impressions == 5000
        assert isinstance(m.impressions, int)
        assert m.views == 750
        assert isinstance(m.views, int)
        assert m.ctr == 0.15
        assert isinstance(m.ctr, float)

    def test_variant_metrics_extreme_values(self) -> None:
        """Support massive scale counters and negative or fractional metrics."""
        m = VariantMetrics(
            variant_id="extreme",
            impressions=10**12,  # 1 trillion impressions
            views=10**11,        # 100 billion views
            ctr=0.10,
            average_view_percentage=150.0,  # Rewatched video
            average_view_duration_sec=7200.0,
            retention_score=1.5,
        )
        d = m.to_dict()
        assert d["impressions"] == 10**12
        restored = VariantMetrics.from_dict(d)
        assert restored.impressions == 10**12
        assert restored.average_view_percentage == 150.0

    def test_thumbnail_variant_missing_required_path_raises_key_error(self) -> None:
        """ThumbnailVariant.from_dict requires 'thumbnail_path'."""
        data = {"variant_id": "A", "name": "Variant A"}
        with pytest.raises(KeyError, match="thumbnail_path"):
            ThumbnailVariant.from_dict(data)

    def test_thumbnail_variant_fallback_when_metrics_is_none_or_missing(self, tmp_path: Path) -> None:
        """When metrics is omitted or None in dict, a default VariantMetrics should be initialized."""
        data_missing = {
            "variant_id": "B",
            "name": "Variant B",
            "thumbnail_path": str(tmp_path / "b.png"),
        }
        v1 = ThumbnailVariant.from_dict(data_missing)
        assert v1.metrics.variant_id == "B"
        assert v1.metrics.impressions == 0

        data_none = {
            "variant_id": "C",
            "name": "Variant C",
            "thumbnail_path": str(tmp_path / "c.png"),
            "metrics": None,
        }
        v2 = ThumbnailVariant.from_dict(data_none)
        assert v2.metrics.variant_id == "C"

    def test_winner_decision_none_p_value_and_null_winner(self) -> None:
        """WinnerDecision should gracefully handle inconclusive tests with None winner and p_value."""
        data = {
            "winner_variant_id": None,
            "winning_score": 0.0,
            "margin": 0.0,
            "is_significant": False,
            "p_value": None,
            "committed": False,
            "committed_at": None,
            "rationale": "Sample size insufficient",
        }
        wd = WinnerDecision.from_dict(data)
        assert wd.winner_variant_id is None
        assert wd.p_value is None
        assert wd.is_significant is False
        assert wd.rationale == "Sample size insufficient"

        d = wd.to_dict()
        assert d["winner_variant_id"] is None
        assert d["p_value"] is None

    def test_thumbnail_experiment_nested_corrupted_fields(self, tmp_path: Path) -> None:
        """ThumbnailExperiment requires project_dir; missing project_dir raises KeyError."""
        data = {
            "experiment_id": "exp_fail",
            "video_id": "vid_fail",
        }
        with pytest.raises(KeyError, match="project_dir"):
            ThumbnailExperiment.from_dict(data)

    def test_thumbnail_experiment_full_nested_lifecycle(self, tmp_path: Path) -> None:
        """Ensure complex experiments with multiple variants and rotation events roundtrip cleanly."""
        proj = tmp_path / "complex_project"
        proj.mkdir()
        thumb_a = proj / "thumb_a.png"
        thumb_b = proj / "thumb_b.png"
        thumb_c = proj / "thumb_c.png"

        exp = ThumbnailExperiment(
            experiment_id="exp_999",
            video_id="video_multi_999",
            project_dir=proj,
            status="RUNNING",
            active_variant_id="B",
            variants={
                "A": ThumbnailVariant(variant_id="A", name="Var A", thumbnail_path=thumb_a, rotation_count=3),
                "B": ThumbnailVariant(variant_id="B", name="Var B", thumbnail_path=thumb_b, is_active=True, rotation_count=4),
                "C": ThumbnailVariant(variant_id="C", name="Var C", thumbnail_path=thumb_c, rotation_count=2),
            },
            rotation_history=[
                RotationEvent("2026-10-20T00:00:00Z", "video_multi_999", None, "A", "init"),
                RotationEvent("2026-10-20T06:00:00Z", "video_multi_999", "A", "B", "rotate_1"),
                RotationEvent("2026-10-20T12:00:00Z", "video_multi_999", "B", "C", "rotate_2"),
                RotationEvent("2026-10-20T18:00:00Z", "video_multi_999", "C", "B", "rotate_3"),
            ],
            winner_decision=None,
            min_impressions=1000,
            min_observation_hours=72.0,
        )

        serialized = json.dumps(exp.to_dict())
        restored = ThumbnailExperiment.from_dict(json.loads(serialized))

        assert restored.experiment_id == "exp_999"
        assert restored.project_dir == proj
        assert len(restored.variants) == 3
        assert restored.variants["B"].is_active is True
        assert len(restored.rotation_history) == 4
        assert restored.rotation_history[-1].to_variant_id == "B"
        assert restored.winner_decision is None


class TestThumbnailFileSizeBoundaries:
    """Rigorous boundary testing for validate_thumbnail_file_size."""

    def test_exact_byte_boundaries(self, tmp_path: Path) -> None:
        """Test [0, 1, 2MB-1, 2MB, 2MB+1] exact file byte counts."""
        # 0 bytes
        f_0 = tmp_path / "f_0.png"
        f_0.write_bytes(b"")
        assert validate_thumbnail_file_size(f_0) is True

        # 1 byte
        f_1 = tmp_path / "f_1.png"
        f_1.write_bytes(b"x")
        assert validate_thumbnail_file_size(f_1) is True

        # 2MB - 1 byte (2,097,151)
        f_under = tmp_path / "f_under.png"
        with open(f_under, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES - 2)
            f.write(b"\0")
        assert f_under.stat().st_size == THUMBNAIL_MAX_SIZE_BYTES - 1
        assert validate_thumbnail_file_size(f_under) is True

        # Exactly 2MB (2,097,152)
        f_exact = tmp_path / "f_exact.png"
        with open(f_exact, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES - 1)
            f.write(b"\0")
        assert f_exact.stat().st_size == THUMBNAIL_MAX_SIZE_BYTES
        assert validate_thumbnail_file_size(f_exact) is True

        # 2MB + 1 byte (2,097,153)
        f_over = tmp_path / "f_over.png"
        with open(f_over, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES)
            f.write(b"\0")
        assert f_over.stat().st_size == THUMBNAIL_MAX_SIZE_BYTES + 1
        assert validate_thumbnail_file_size(f_over) is False

    def test_custom_max_bytes_parameter(self, tmp_path: Path) -> None:
        """validate_thumbnail_file_size respects custom max_bytes thresholds."""
        f = tmp_path / "test_custom.dat"
        f.write_bytes(b"1234567890")  # 10 bytes

        assert validate_thumbnail_file_size(f, max_bytes=10) is True
        assert validate_thumbnail_file_size(f, max_bytes=9) is False
        assert validate_thumbnail_file_size(f, max_bytes=100) is True

    def test_str_and_path_inputs(self, tmp_path: Path) -> None:
        """Accepts both string and Path instances."""
        f = tmp_path / "test_path.png"
        f.write_bytes(b"hello")

        assert validate_thumbnail_file_size(str(f)) is True
        assert validate_thumbnail_file_size(f) is True

    def test_invalid_path_types_and_missing_files(self, tmp_path: Path) -> None:
        """Returns False for non-existent files or directories."""
        assert validate_thumbnail_file_size(tmp_path / "non_existent.png") is False
        assert validate_thumbnail_file_size(tmp_path) is False


class TestAutoExtractVariantConfigsAdversarial:
    """Stress-test auto_extract_variant_configs and generate_thumbnail_variants."""

    def test_missing_script_and_config_uses_graceful_defaults(self, tmp_path: Path) -> None:
        """Completely empty directory without script.json or thumbnail_config.json derives contrasting A and B."""
        empty_dir = tmp_path / "empty_proj"
        empty_dir.mkdir()

        configs = auto_extract_variant_configs(empty_dir)
        assert "A" in configs
        assert "B" in configs
        assert configs["A"].theme == "gold"
        assert configs["A"].emotion == "surprised"
        assert configs["A"].mouth_open is True

        assert configs["B"].theme == "red"
        assert configs["B"].emotion == "angry"
        assert configs["B"].mouth_open is False
        assert configs["B"].badge == "【緊急警告】"

    def test_corrupted_config_json_falls_back_gracefully(self, tmp_path: Path) -> None:
        """Broken JSON syntax in thumbnail_config.json should not raise, but log warning and fallback."""
        proj = tmp_path / "corrupted_json_proj"
        proj.mkdir()
        cfg_file = proj / "thumbnail_config.json"
        cfg_file.write_text("{ this is NOT valid json ...", encoding="utf-8")

        configs = auto_extract_variant_configs(proj)
        assert "A" in configs
        assert "B" in configs
        assert configs["A"].theme == "gold"
        assert configs["B"].theme == "red"

    def test_multi_variant_config_file_with_three_variants(self, tmp_path: Path) -> None:
        """Explicit variants dictionary with 3 variants (A, B, C) extracts all three correctly."""
        proj = tmp_path / "three_variants_proj"
        proj.mkdir()
        cfg_file = proj / "thumbnail_config.json"
        data = {
            "default": {
                "title_line1": "暗号資産",
                "title_line2": "今すぐ売れ！？",
                "highlight_word": "今すぐ売れ",
                "character": "ずんだもん",
            },
            "variants": {
                "A": {"theme": "gold", "badge": "【市場分析】", "emotion": "surprised"},
                "B": {"theme": "red", "badge": "【暴落警告】", "emotion": "angry"},
                "C": {"theme": "purple", "badge": "【裏情報】", "emotion": "happy"},
            },
        }
        cfg_file.write_text(json.dumps(data), encoding="utf-8")

        configs = auto_extract_variant_configs(proj)
        assert len(configs) == 3
        assert set(configs.keys()) == {"A", "B", "C"}
        assert configs["A"].theme == "gold"
        assert configs["B"].theme == "red"
        assert configs["C"].theme == "purple"
        assert configs["C"].badge == "【裏情報】"

    def test_generate_thumbnail_variants_with_custom_overrides(self, tmp_path: Path) -> None:
        """generate_thumbnail_variants applies variant_overrides and injects new variants."""
        base_cfg = ThumbnailConfig(
            title_line1="AI副業",
            title_line2="月10万円稼ぐ方法",
            highlight_word="月10万円",
            sub_hook="▶ 初心者でも即日スタート！",
            badge="【完全ガイド】",
            character="ずんだもん",
            emotion="surprised",
        )
        out_dir = tmp_path / "rendered_variants"
        overrides = {
            "A": {"badge": "【特別版A】"},
            "C": {"theme": "cyber", "badge": "【特別版C】", "emotion": "happy"},
        }
        results = generate_thumbnail_variants(base_cfg, out_dir, variant_overrides=overrides)

        assert "A" in results
        assert "B" in results
        assert "C" in results
        for vid, path in results.items():
            assert path.exists()
            assert validate_thumbnail_file_size(path) is True
            assert path.stat().st_size <= THUMBNAIL_MAX_SIZE_BYTES

        # Canonical thumbnail.png copied from Variant A
        canonical = out_dir / "thumbnail.png"
        assert canonical.exists()
        assert canonical.stat().st_size == results["A"].stat().st_size


class TestMockYouTubeAdapterAdversarial:
    """Stress-test MockYouTubeAdapter under high load, concurrency, and error conditions."""

    def test_rapid_consecutive_rotations(self, tmp_path: Path) -> None:
        """100 rapid consecutive rotations across 3 variants maintain monotonic history."""
        adapter = MockYouTubeAdapter()
        video_id = "v_stress_100"

        thumb_a = tmp_path / "thumb_a.png"
        thumb_a.write_bytes(b"A" * 1024)
        thumb_b = tmp_path / "thumb_b.png"
        thumb_b.write_bytes(b"B" * 2048)
        thumb_c = tmp_path / "thumb_c.png"
        thumb_c.write_bytes(b"C" * 4096)

        thumbs = [thumb_a, thumb_b, thumb_c]

        for i in range(100):
            target_thumb = thumbs[i % 3]
            success = adapter.upload_thumbnail(video_id=video_id, thumbnail_path=target_thumb)
            assert success is True

        assert len(adapter.thumbnail_history) == 100
        assert adapter.uploaded_thumbnails[video_id] == thumbs[99 % 3]

        # Verify timestamps are monotonically non-decreasing
        timestamps = [entry["timestamp"] for entry in adapter.thumbnail_history]
        for t1, t2 in zip(timestamps[:-1], timestamps[1:]):
            assert t2 >= t1

    def test_interleaved_multi_video_rotations(self, tmp_path: Path) -> None:
        """Rotating thumbnails on multiple distinct videos preserves video-specific state."""
        adapter = MockYouTubeAdapter()

        t_v1_a = tmp_path / "v1_a.png"
        t_v1_a.write_bytes(b"v1a")
        t_v1_b = tmp_path / "v1_b.png"
        t_v1_b.write_bytes(b"v1b")

        t_v2_a = tmp_path / "v2_a.png"
        t_v2_a.write_bytes(b"v2a")
        t_v2_b = tmp_path / "v2_b.png"
        t_v2_b.write_bytes(b"v2b")

        # Interleaved sequence
        adapter.upload_thumbnail("video_1", t_v1_a)
        adapter.upload_thumbnail("video_2", t_v2_a)
        adapter.upload_thumbnail("video_1", t_v1_b)
        adapter.upload_thumbnail("video_2", t_v2_b)

        assert len(adapter.thumbnail_history) == 4
        assert adapter.uploaded_thumbnails["video_1"] == t_v1_b
        assert adapter.uploaded_thumbnails["video_2"] == t_v2_b

    def test_upload_thumbnail_fault_atomicity(self, tmp_path: Path) -> None:
        """Failed thumbnail uploads (missing file or oversized) do NOT pollute history or state."""
        adapter = MockYouTubeAdapter()
        video_id = "v_atomic"

        good_thumb = tmp_path / "good.png"
        good_thumb.write_bytes(b"good_data")
        adapter.upload_thumbnail(video_id, good_thumb)
        assert len(adapter.thumbnail_history) == 1
        assert adapter.uploaded_thumbnails[video_id] == good_thumb

        # Missing file attempt
        missing_thumb = tmp_path / "non_existent.png"
        with pytest.raises(FileNotFoundError):
            adapter.upload_thumbnail(video_id, missing_thumb)

        assert len(adapter.thumbnail_history) == 1
        assert adapter.uploaded_thumbnails[video_id] == good_thumb

        # Oversized file attempt (> 2MB)
        huge_thumb = tmp_path / "huge.png"
        with open(huge_thumb, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES)
            f.write(b"\0")

        with pytest.raises(ValueError, match="exceeds YouTube 2MB limit"):
            adapter.upload_thumbnail(video_id, huge_thumb)

        assert len(adapter.thumbnail_history) == 1
        assert adapter.uploaded_thumbnails[video_id] == good_thumb

    def test_simulated_metrics_isolation_and_retrieval(self) -> None:
        """Simulated metrics for distinct variants remain fully isolated."""
        adapter = MockYouTubeAdapter()
        adapter.set_simulated_metrics("var_1", impressions=10000, views=1500, ctr=0.15)
        adapter.set_simulated_metrics("var_2", impressions=12000, views=2400, ctr=0.20)

        m1 = adapter.fetch_variant_metrics("var_1")
        m2 = adapter.fetch_variant_metrics("var_2")

        assert m1.impressions == 10000
        assert m1.views == 1500
        assert m1.ctr == 0.15

        assert m2.impressions == 12000
        assert m2.views == 2400
        assert m2.ctr == 0.20

    def test_protocol_conformance_adversarial(self) -> None:
        """Verify strict protocol conformance against VideoPublisher and VideoAnalyticsProvider."""
        adapter = MockYouTubeAdapter()
        assert isinstance(adapter, VideoPublisher)
        assert isinstance(adapter, VideoAnalyticsProvider)

        # Ensure methods defined on VideoAnalyticsProvider are present and callable
        assert hasattr(adapter, "fetch_retention_curve")
        assert callable(adapter.fetch_retention_curve)
        assert hasattr(adapter, "fetch_variant_metrics")
        assert callable(adapter.fetch_variant_metrics)

        # Ensure methods defined on VideoPublisher are present and callable
        assert hasattr(adapter, "upload_video")
        assert callable(adapter.upload_video)
        assert hasattr(adapter, "upload_thumbnail")
        assert callable(adapter.upload_thumbnail)
        assert hasattr(adapter, "upload_caption")
        assert callable(adapter.upload_caption)
