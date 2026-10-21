"""Unit and Integration Tests for YouTube Thumbnail A/B Variant Engine (Milestone 1).

Covers:
- Pure domain models in veraxi_ymmp.ir:
  VariantMetrics, ThumbnailVariant, RotationEvent, WinnerDecision, ThumbnailExperiment (serialization)
- Protocol conformance in veraxi_ymmp.ports:
  VideoPublisher, VideoAnalyticsProvider
- Variant configuration and generation in veraxi_ymmp.thumbnail:
  validate_thumbnail_file_size, auto_extract_variant_configs, generate_thumbnail_variants
- Infrastructure adapter mock simulation in veraxi_ymmp.youtube_adapter:
  MockYouTubeAdapter thumbnail_history, set_simulated_metrics, fetch_variant_metrics
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
from veraxi_ymmp.thumbnail_ab import (
    ThumbnailABCoordinator,
    commit_winner,
    evaluate_performance,
    get_status,
    initialize_experiment,
    load_experiment,
    render_ab_report,
    rotate_thumbnail,
)
from veraxi_ymmp.youtube_adapter import (
    THUMBNAIL_MAX_SIZE_BYTES,
    MockYouTubeAdapter,
)


class TestDomainModelSerialization:
    """Test pure dataclass serialization (to_dict / from_dict) in veraxi_ymmp.ir."""

    def test_variant_metrics_roundtrip(self) -> None:
        metrics = VariantMetrics(
            variant_id="A",
            impressions=1200,
            views=144,
            ctr=0.12,
            average_view_percentage=68.5,
            average_view_duration_sec=135.0,
            retention_score=0.685,
            sample_start="2026-10-01",
            sample_end="2026-10-02",
            raw_metrics={"source": "simulated"},
        )
        d = metrics.to_dict()
        assert d["variant_id"] == "A"
        assert d["impressions"] == 1200
        assert d["views"] == 144
        assert d["ctr"] == 0.12
        assert d["average_view_percentage"] == 68.5
        assert d["sample_start"] == "2026-10-01"

        restored = VariantMetrics.from_dict(d)
        assert restored.variant_id == metrics.variant_id
        assert restored.impressions == metrics.impressions
        assert restored.views == metrics.views
        assert restored.ctr == metrics.ctr
        assert restored.average_view_percentage == metrics.average_view_percentage
        assert restored.retention_score == metrics.retention_score
        assert restored.sample_start == metrics.sample_start
        assert restored.raw_metrics == {"source": "simulated"}

    def test_thumbnail_variant_roundtrip(self, tmp_path: Path) -> None:
        thumb_path = tmp_path / "thumb_a.png"
        variant = ThumbnailVariant(
            variant_id="A",
            name="Variant A (Gold Hook)",
            thumbnail_path=thumb_path,
            config={"theme": "gold", "emotion": "surprised"},
            metrics=VariantMetrics(variant_id="A", impressions=500, views=60, ctr=0.12),
            is_active=True,
            rotation_count=2,
        )
        d = variant.to_dict()
        assert d["variant_id"] == "A"
        assert d["name"] == "Variant A (Gold Hook)"
        assert d["thumbnail_path"] == str(thumb_path)
        assert d["config"]["theme"] == "gold"
        assert d["metrics"]["impressions"] == 500
        assert d["is_active"] is True
        assert d["rotation_count"] == 2

        restored = ThumbnailVariant.from_dict(d)
        assert restored.variant_id == "A"
        assert restored.thumbnail_path == thumb_path
        assert restored.metrics.impressions == 500
        assert restored.is_active is True
        assert restored.rotation_count == 2

    def test_rotation_event_roundtrip(self) -> None:
        event = RotationEvent(
            timestamp="2026-10-20T12:00:00Z",
            video_id="mock_video_001",
            from_variant_id="A",
            to_variant_id="B",
            reason="scheduled_rotation",
        )
        d = event.to_dict()
        assert d["timestamp"] == "2026-10-20T12:00:00Z"
        assert d["from_variant_id"] == "A"
        assert d["to_variant_id"] == "B"
        assert d["reason"] == "scheduled_rotation"

        restored = RotationEvent.from_dict(d)
        assert restored.timestamp == event.timestamp
        assert restored.video_id == event.video_id
        assert restored.from_variant_id == event.from_variant_id
        assert restored.to_variant_id == event.to_variant_id
        assert restored.reason == event.reason

    def test_winner_decision_roundtrip(self) -> None:
        decision = WinnerDecision(
            winner_variant_id="B",
            winning_score=0.88,
            margin=0.15,
            is_significant=True,
            p_value=0.015,
            committed=True,
            committed_at="2026-10-22T10:00:00Z",
            rationale="Statistically significant CTR advantage (Z=2.43, p=0.015)",
        )
        d = decision.to_dict()
        assert d["winner_variant_id"] == "B"
        assert d["is_significant"] is True
        assert d["p_value"] == 0.015
        assert d["committed"] is True

        restored = WinnerDecision.from_dict(d)
        assert restored.winner_variant_id == "B"
        assert restored.winning_score == 0.88
        assert restored.margin == 0.15
        assert restored.is_significant is True
        assert restored.p_value == 0.015
        assert restored.committed is True
        assert restored.committed_at == "2026-10-22T10:00:00Z"

    def test_thumbnail_experiment_full_roundtrip(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        thumb_a = project_dir / "thumbnail_a.png"
        thumb_b = project_dir / "thumbnail_b.png"

        var_a = ThumbnailVariant(variant_id="A", name="Variant A", thumbnail_path=thumb_a, is_active=False)
        var_b = ThumbnailVariant(variant_id="B", name="Variant B", thumbnail_path=thumb_b, is_active=True)

        event = RotationEvent(
            timestamp="2026-10-20T00:00:00Z",
            video_id="v_100",
            from_variant_id="A",
            to_variant_id="B",
            reason="scheduled_rotation",
        )
        winner = WinnerDecision(
            winner_variant_id="B",
            winning_score=0.85,
            is_significant=True,
            committed=True,
        )

        experiment = ThumbnailExperiment(
            experiment_id="exp_001",
            video_id="v_100",
            project_dir=project_dir,
            status="CONCLUDED",
            active_variant_id="B",
            variants={"A": var_a, "B": var_b},
            rotation_history=[event],
            winner_decision=winner,
            min_impressions=600,
            min_observation_hours=48.0,
            created_at="2026-10-18T00:00:00Z",
            updated_at="2026-10-20T00:00:00Z",
        )

        d = experiment.to_dict()
        # Verify JSON serializability
        serialized_json = json.dumps(d)
        data_from_json = json.loads(serialized_json)

        restored = ThumbnailExperiment.from_dict(data_from_json)
        assert restored.experiment_id == "exp_001"
        assert restored.video_id == "v_100"
        assert restored.project_dir == project_dir
        assert restored.status == "CONCLUDED"
        assert restored.active_variant_id == "B"
        assert len(restored.variants) == 2
        assert restored.variants["A"].name == "Variant A"
        assert restored.variants["B"].is_active is True
        assert len(restored.rotation_history) == 1
        assert restored.rotation_history[0].to_variant_id == "B"
        assert restored.winner_decision is not None
        assert restored.winner_decision.winner_variant_id == "B"
        assert restored.min_impressions == 600
        assert restored.min_observation_hours == 48.0


class TestThumbnailVariantExtractionAndGeneration:
    """Test auto_extract_variant_configs, generate_thumbnail_variants, and size validation."""

    def test_validate_thumbnail_file_size_boundaries(self, tmp_path: Path) -> None:
        # Non-existent file
        non_existent = tmp_path / "does_not_exist.png"
        assert validate_thumbnail_file_size(non_existent) is False

        # Directory path
        assert validate_thumbnail_file_size(tmp_path) is False

        # 0 bytes file
        empty_file = tmp_path / "empty.png"
        empty_file.write_bytes(b"")
        assert validate_thumbnail_file_size(empty_file) is True

        # Exactly 2MB (2,097,152 bytes)
        exact_2mb = tmp_path / "exact_2mb.png"
        with open(exact_2mb, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES - 1)
            f.write(b"\0")
        assert exact_2mb.stat().st_size == THUMBNAIL_MAX_SIZE_BYTES
        assert validate_thumbnail_file_size(exact_2mb) is True

        # Exactly 2MB + 1 byte (2,097,153 bytes)
        over_2mb = tmp_path / "over_2mb.png"
        with open(over_2mb, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES)
            f.write(b"\0")
        assert over_2mb.stat().st_size == THUMBNAIL_MAX_SIZE_BYTES + 1
        assert validate_thumbnail_file_size(over_2mb) is False

    def test_auto_extract_variant_configs_default_contrast(self) -> None:
        base_cfg = ThumbnailConfig(
            title_line1="コストコ再販店",
            title_line2="ボロ儲けの真実！？",
            highlight_word="ボロ儲け",
            sub_hook="▶ なぜ会員証なしでも繁盛するのか？",
            badge="【徹底解説】",
            character="ずんだもん",
            emotion="surprised",
        )
        variants = auto_extract_variant_configs(base_cfg)
        assert "A" in variants
        assert "B" in variants

        # Variant A: Gold theme, surprised emotion, curiosity hook, open mouth
        cfg_a = variants["A"]
        assert cfg_a.theme == "gold"
        assert cfg_a.emotion == "surprised"
        assert cfg_a.mouth_open is True
        assert cfg_a.badge == "【徹底解説】"

        # Variant B: Red theme, angry emotion, urgency hook, closed mouth
        cfg_b = variants["B"]
        assert cfg_b.theme == "red"
        assert cfg_b.emotion == "angry"
        assert cfg_b.mouth_open is False
        assert cfg_b.badge == "【緊急警告】"
        assert cfg_b.title_line2 != ""

    def test_auto_extract_variant_configs_from_file_with_overrides(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "thumbnail_config.json"
        data = {
            "default": {
                "title_line1": "日本株",
                "title_line2": "大暴落！？",
                "highlight_word": "大暴落",
            },
            "variants": {
                "A": {"theme": "gold", "badge": "【独自分析】"},
                "B": {"theme": "red", "badge": "【超警告】", "emotion": "angry"},
            },
        }
        cfg_file.write_text(json.dumps(data), encoding="utf-8")

        configs = auto_extract_variant_configs(tmp_path)
        assert len(configs) == 2
        assert configs["A"].theme == "gold"
        assert configs["A"].badge == "【独自分析】"
        assert configs["B"].theme == "red"
        assert configs["B"].badge == "【超警告】"
        assert configs["B"].emotion == "angry"

    def test_generate_thumbnail_variants_renders_valid_images(self, tmp_path: Path) -> None:
        base_cfg = ThumbnailConfig(
            title_line1="株式投資",
            title_line2="超初心者向け入門",
            highlight_word="超初心者",
            sub_hook="▶ 失敗しないための完全ロードマップ",
            badge="【完全ガイド】",
            character="ずんだもん",
            emotion="surprised",
        )
        out_dir = tmp_path / "variants"
        results = generate_thumbnail_variants(base_cfg, out_dir)

        assert "A" in results
        assert "B" in results
        assert results["A"].exists()
        assert results["B"].exists()

        # Both files must strictly adhere to the <= 2MB size limit
        assert validate_thumbnail_file_size(results["A"]) is True
        assert validate_thumbnail_file_size(results["B"]) is True
        assert results["A"].stat().st_size <= THUMBNAIL_MAX_SIZE_BYTES
        assert results["B"].stat().st_size <= THUMBNAIL_MAX_SIZE_BYTES

        # Canonical thumbnail.png created from Variant A
        canonical = out_dir / "thumbnail.png"
        assert canonical.exists()
        assert canonical.stat().st_size == results["A"].stat().st_size


class TestMockYouTubeAdapterSimulation:
    """Test MockYouTubeAdapter thumbnail upload history tracking and metric simulation."""

    def test_protocol_conformance(self) -> None:
        adapter = MockYouTubeAdapter()
        assert isinstance(adapter, VideoPublisher)
        assert isinstance(adapter, VideoAnalyticsProvider)

    def test_upload_thumbnail_records_history(self, tmp_path: Path) -> None:
        adapter = MockYouTubeAdapter()
        assert adapter.thumbnail_history == []

        thumb_a = tmp_path / "thumb_a.png"
        thumb_a.write_bytes(b"dummy_a_bytes")
        thumb_b = tmp_path / "thumb_b.png"
        thumb_b.write_bytes(b"dummy_b_bytes")

        # First upload
        ok1 = adapter.upload_thumbnail(video_id="video_abc", thumbnail_path=thumb_a)
        assert ok1 is True
        assert len(adapter.thumbnail_history) == 1
        assert adapter.thumbnail_history[0]["video_id"] == "video_abc"
        assert adapter.thumbnail_history[0]["thumbnail_path"] == thumb_a
        assert isinstance(adapter.thumbnail_history[0]["timestamp"], float)
        assert adapter.uploaded_thumbnails["video_abc"] == thumb_a

        # Rotation upload
        ok2 = adapter.upload_thumbnail(video_id="video_abc", thumbnail_path=thumb_b)
        assert ok2 is True
        assert len(adapter.thumbnail_history) == 2
        assert adapter.thumbnail_history[1]["thumbnail_path"] == thumb_b
        assert adapter.uploaded_thumbnails["video_abc"] == thumb_b

    def test_upload_thumbnail_rejects_oversized_file(self, tmp_path: Path) -> None:
        adapter = MockYouTubeAdapter()
        over_2mb = tmp_path / "huge_thumb.png"
        with open(over_2mb, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES)
            f.write(b"\0")

        with pytest.raises(ValueError, match="exceeds YouTube 2MB limit"):
            adapter.upload_thumbnail("video_001", over_2mb)

    def test_simulated_variant_metrics(self) -> None:
        adapter = MockYouTubeAdapter()
        adapter.set_simulated_metrics(
            variant_id="A",
            impressions=2500,
            views=300,
            ctr=0.12,
            average_view_percentage=66.0,
        )
        adapter.set_simulated_metrics(
            variant_id="B",
            impressions=2500,
            views=450,
            ctr=0.18,
            average_view_percentage=71.5,
        )

        metrics_a = adapter.fetch_variant_metrics("A")
        assert metrics_a.variant_id == "A"
        assert metrics_a.impressions == 2500
        assert metrics_a.views == 300
        assert metrics_a.ctr == 0.12
        assert metrics_a.average_view_percentage == 66.0

        metrics_b = adapter.fetch_variant_metrics("B")
        assert metrics_b.variant_id == "B"
        assert metrics_b.impressions == 2500
        assert metrics_b.views == 450
        assert metrics_b.ctr == 0.18
        assert metrics_b.average_view_percentage == 71.5

        assert "fetch_variant_metrics:A" in adapter.call_log
        assert "fetch_variant_metrics:B" in adapter.call_log

    def test_default_variant_metrics(self) -> None:
        adapter = MockYouTubeAdapter()
        default_m = adapter.fetch_variant_metrics("arbitrary_video_id")
        assert default_m.variant_id == "arbitrary_video_id"
        assert default_m.impressions == 1000
        assert default_m.views == 120
        assert default_m.ctr == 0.12
        assert default_m.average_view_percentage == 65.0


class TestThumbnailABCoordinator:
    """Comprehensive unit and lifecycle tests for ThumbnailABCoordinator (Milestone 2)."""

    @pytest.fixture
    def dummy_variants(self, tmp_path: Path) -> list[ThumbnailVariant]:
        thumb_a = tmp_path / "thumb_a.png"
        thumb_b = tmp_path / "thumb_b.png"
        thumb_a.write_bytes(b"dummy_a")
        thumb_b.write_bytes(b"dummy_b")
        return [
            ThumbnailVariant(
                variant_id="A",
                name="Variant A (Gold Hook)",
                thumbnail_path=thumb_a,
                config={"theme": "gold", "badge": "【徹底解説】"},
            ),
            ThumbnailVariant(
                variant_id="B",
                name="Variant B (Red Urgency)",
                thumbnail_path=thumb_b,
                config={"theme": "red", "badge": "【緊急警告】"},
            ),
        ]

    def test_coordinator_initialization_and_default_activation(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        exp = initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_unit_01",
            variants=dummy_variants,
            publisher=adapter,
        )

        assert exp.video_id == "vid_unit_01"
        assert exp.status == "RUNNING"
        assert exp.active_variant_id == "A"
        assert exp.variants["A"].is_active is True
        assert exp.variants["B"].is_active is False
        assert len(exp.rotation_history) == 1
        assert exp.rotation_history[0].to_variant_id == "A"
        assert exp.rotation_history[0].reason == "initial_activation"

        # Check publisher recorded the initial upload
        assert len(adapter.thumbnail_history) == 1
        assert adapter.thumbnail_history[0]["video_id"] == "vid_unit_01"
        assert adapter.thumbnail_history[0]["thumbnail_path"] == dummy_variants[0].thumbnail_path

        # Check state file persisted
        state_file = tmp_path / "thumbnail_ab_experiment.json"
        assert state_file.exists()
        loaded = load_experiment(tmp_path)
        assert loaded.video_id == "vid_unit_01"
        assert loaded.active_variant_id == "A"

    def test_coordinator_explicit_and_round_robin_rotation(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_unit_02",
            variants=dummy_variants,
            publisher=adapter,
        )

        # Explicit rotation to B
        ev1 = rotate_thumbnail(
            project_dir=tmp_path,
            video_id="vid_unit_02",
            target_variant_id="B",
            publisher=adapter,
            reason="explicit_switch",
        )
        assert ev1.from_variant_id == "A"
        assert ev1.to_variant_id == "B"
        assert ev1.reason == "explicit_switch"

        st1 = get_status(tmp_path)
        assert st1.active_variant_id == "B"
        assert st1.variants["B"].is_active is True
        assert st1.variants["A"].is_active is False
        assert st1.variants["B"].rotation_count == 1

        # Round-robin rotation (should rotate back to A)
        ev2 = rotate_thumbnail(
            project_dir=tmp_path,
            video_id="vid_unit_02",
            target_variant_id=None,
            publisher=adapter,
            reason="scheduled_rotation",
        )
        assert ev2.from_variant_id == "B"
        assert ev2.to_variant_id == "A"

        st2 = get_status(tmp_path)
        assert st2.active_variant_id == "A"
        assert st2.variants["A"].is_active is True
        assert st2.variants["A"].rotation_count == 1
        assert len(st2.rotation_history) == 3  # initial + 2 rotations

        # Verify adapter logged all 3 uploads
        assert len(adapter.thumbnail_history) == 3

    def test_coordinator_rotation_guards(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_unit_guards",
            variants=dummy_variants,
            publisher=adapter,
        )

        # Rotating to non-existent variant raises KeyError
        with pytest.raises(KeyError, match="Target variant 'Z' does not exist"):
            rotate_thumbnail(
                project_dir=tmp_path,
                video_id="vid_unit_guards",
                target_variant_id="Z",
                publisher=adapter,
            )

        # Commit winner to transition to CONCLUDED
        commit_winner(
            project_dir=tmp_path,
            video_id="vid_unit_guards",
            winner_id="A",
            publisher=adapter,
        )

        # Rotating on CONCLUDED experiment raises RuntimeError
        with pytest.raises(RuntimeError, match="Cannot rotate thumbnail on a CONCLUDED experiment"):
            rotate_thumbnail(
                project_dir=tmp_path,
                video_id="vid_unit_guards",
                target_variant_id="B",
                publisher=adapter,
            )

    def test_coordinator_evaluation_statistically_significant(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_unit_eval_sig",
            variants=dummy_variants,
            publisher=adapter,
        )

        # Variant A: 2000 imp, 160 views (8% CTR)
        # Variant B: 2000 imp, 280 views (14% CTR)
        adapter.set_simulated_metrics("A", impressions=2000, views=160, ctr=0.08, average_view_percentage=65.0)
        adapter.set_simulated_metrics("B", impressions=2000, views=280, ctr=0.14, average_view_percentage=68.0)

        decision = evaluate_performance(
            project_dir=tmp_path,
            video_id="vid_unit_eval_sig",
            analytics_provider=adapter,
            confidence_level=0.95,
        )

        assert decision.is_significant is True
        assert decision.winner_variant_id == "B"
        assert decision.p_value is not None and decision.p_value < 0.05
        assert decision.winning_score == 0.14
        assert abs(decision.margin - 0.06) < 1e-4
        assert "Statistically significant" in decision.rationale

        st = get_status(tmp_path)
        assert st.winner_decision is not None
        assert st.winner_decision.winner_variant_id == "B"

    def test_coordinator_evaluation_inconclusive_sample_size(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_unit_eval_low",
            variants=dummy_variants,
            publisher=adapter,
        )

        # Only 40 impressions each (< 500 default min_impressions)
        adapter.set_simulated_metrics("A", impressions=40, views=4, ctr=0.10)
        adapter.set_simulated_metrics("B", impressions=40, views=6, ctr=0.15)

        decision = evaluate_performance(
            project_dir=tmp_path,
            video_id="vid_unit_eval_low",
            analytics_provider=adapter,
        )

        assert decision.is_significant is False
        assert decision.winner_variant_id is None
        assert "INCONCLUSIVE_INSUFFICIENT_DATA" in decision.rationale

    def test_coordinator_evaluation_retention_guardrail_penalty(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_unit_retention",
            variants=dummy_variants,
            publisher=adapter,
        )

        # Variant A: 2500 imp, 225 views (9% CTR, 74.0% retention)
        # Variant B: 2500 imp, 425 views (17% CTR, 24.0% retention -> clickbait drop)
        adapter.set_simulated_metrics("A", impressions=2500, views=225, ctr=0.09, average_view_percentage=74.0)
        adapter.set_simulated_metrics("B", impressions=2500, views=425, ctr=0.17, average_view_percentage=24.0)

        decision = evaluate_performance(
            project_dir=tmp_path,
            video_id="vid_unit_retention",
            analytics_provider=adapter,
        )

        # Clickbait B should be vetoed due to < 40% retention and > 15% drop
        assert decision.winner_variant_id != "B"
        assert decision.winner_variant_id == "A"
        assert "retention" in decision.rationale.lower()

    def test_coordinator_commit_winner_and_qa_reporting(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        cfg_file = tmp_path / "thumbnail_config.json"
        cfg_file.write_text(json.dumps({"theme": "gold", "title_line1": "Base"}), encoding="utf-8")

        initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_unit_commit",
            variants=dummy_variants,
            publisher=adapter,
        )

        adapter.set_simulated_metrics("A", impressions=1500, views=120, ctr=0.08)
        adapter.set_simulated_metrics("B", impressions=1500, views=210, ctr=0.14)
        evaluate_performance(tmp_path, "vid_unit_commit", analytics_provider=adapter)

        exp = commit_winner(
            project_dir=tmp_path,
            video_id="vid_unit_commit",
            winner_id="B",
            publisher=adapter,
        )

        assert exp.status == "CONCLUDED"
        assert exp.active_variant_id == "B"
        assert exp.winner_decision is not None
        assert exp.winner_decision.committed is True
        assert exp.winner_decision.committed_at is not None

        # Canonical thumbnail promoted
        canonical = tmp_path / "thumbnail.png"
        assert canonical.exists()
        assert canonical.read_bytes() == dummy_variants[1].thumbnail_path.read_bytes()

        # Config synced
        updated_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert updated_cfg.get("theme") == "red"

        # QA reports generated
        assert (tmp_path / "ab_test_report.md").exists()
        assert (tmp_path / "ab_test_report.json").exists()
        assert (tmp_path / "qa_reports" / "ab_test_report.md").exists()
        assert (tmp_path / "qa_reports" / "thumbnail_ab_winner_report.md").exists()
        assert (tmp_path / "qa_reports" / "thumbnail_ab_winner_report.json").exists()

    def test_coordinator_markdown_report_rendering(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_unit_report",
            variants=dummy_variants,
            publisher=adapter,
        )
        rotate_thumbnail(tmp_path, "vid_unit_report", target_variant_id="B", publisher=adapter)
        commit_winner(tmp_path, "vid_unit_report", winner_id="B", publisher=adapter)

        exp = get_status(tmp_path)
        md = render_ab_report(exp)

        assert "# YouTube Thumbnail A/B Test Audit Report" in md
        assert f"`{exp.experiment_id}`" in md
        assert "**Winner Variant**: **B**" in md
        assert "Variant Performance Table" in md
        assert "Rotation History Log" in md

    def test_coordinator_dual_invocation_class_and_instance(
        self, tmp_path: Path, dummy_variants: list[ThumbnailVariant]
    ) -> None:
        adapter = MockYouTubeAdapter()
        coord = ThumbnailABCoordinator(publisher=adapter)

        # Instance invocation
        exp1 = coord.initialize_experiment(
            project_dir=tmp_path,
            video_id="vid_dual_01",
            variants=dummy_variants,
        )
        assert exp1.video_id == "vid_dual_01"

        # Class invocation
        state = ThumbnailABCoordinator.get_status(tmp_path)
        assert state.video_id == "vid_dual_01"

        rot = ThumbnailABCoordinator.rotate_thumbnail(
            project_dir=tmp_path,
            video_id="vid_dual_01",
            target_variant_id="B",
            publisher=adapter,
        )
        assert rot.to_variant_id == "B"
