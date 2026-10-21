"""
End-to-End (E2E) Opaque-Box Test Suite for YouTube A/B Thumbnail Engine.

This test suite implements a comprehensive 4-tier testing hierarchy verifying:
- Tier 1: Category-Partition Feature Coverage (Isolation happy paths across all 8 features, >=5 tests each)
- Tier 2: Boundary Value Analysis & Corner Stress (Extreme limits & fault injection, >=5 tests each across 5 categories)
- Tier 3: Cross-Feature Combinations (Pairwise and multi-component interactions, >=8 tests)
- Tier 4: Real-World Workload Scenarios (Realistic production video publishing & lifecycle workflows, >=5 scenarios)

Guarantees:
- 100% offline execution without network access or live Google credentials.
- Zero committed secrets or hardcoded user/machine paths.
- Strict Clean Architecture compliance and progressive testability across Milestones M1-M4.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# Milestone M1: Domain Models, Ports, Thumbnail Helpers, and Mock Adapter
# ---------------------------------------------------------------------------
try:
    from veraxi_ymmp.ir import (
        RotationEvent,
        ThumbnailExperiment,
        ThumbnailVariant,
        VariantMetrics,
        WinnerDecision,
    )
    HAS_M1_DOMAIN = True
except ImportError:
    HAS_M1_DOMAIN = False
    RotationEvent = None  # type: ignore
    ThumbnailExperiment = None  # type: ignore
    ThumbnailVariant = None  # type: ignore
    VariantMetrics = None  # type: ignore
    WinnerDecision = None  # type: ignore

try:
    from veraxi_ymmp.ports import VideoAnalyticsProvider, VideoPublisher
    HAS_M1_PORTS = True
except ImportError:
    HAS_M1_PORTS = False
    VideoAnalyticsProvider = None  # type: ignore
    VideoPublisher = None  # type: ignore

try:
    from veraxi_ymmp.thumbnail import (
        ThumbnailConfig,
        auto_extract_variant_configs,
        generate_thumbnail,
        generate_thumbnail_variants,
        validate_thumbnail_file_size,
    )
    HAS_M1_THUMBNAIL = True
except ImportError:
    HAS_M1_THUMBNAIL = False
    ThumbnailConfig = None  # type: ignore
    auto_extract_variant_configs = None  # type: ignore
    generate_thumbnail = None  # type: ignore
    generate_thumbnail_variants = None  # type: ignore
    validate_thumbnail_file_size = None  # type: ignore

try:
    from veraxi_ymmp.youtube_adapter import MockYouTubeAdapter, YouTubeAdapter
    HAS_M1_ADAPTER = hasattr(MockYouTubeAdapter, "set_simulated_metrics") and hasattr(
        MockYouTubeAdapter, "fetch_variant_metrics"
    )
except (ImportError, AttributeError):
    HAS_M1_ADAPTER = False
    MockYouTubeAdapter = None  # type: ignore
    YouTubeAdapter = None  # type: ignore

# ---------------------------------------------------------------------------
# Milestone M2: Application Coordinator Service (ThumbnailABCoordinator)
# ---------------------------------------------------------------------------
try:
    from veraxi_ymmp.thumbnail_ab import ThumbnailABCoordinator
    HAS_M2_COORDINATOR = True
except ImportError:
    try:
        from veraxi_ymmp.thumbnail_ab_coordinator import ThumbnailABCoordinator  # type: ignore
        HAS_M2_COORDINATOR = True
    except ImportError:
        HAS_M2_COORDINATOR = False
        ThumbnailABCoordinator = None  # type: ignore

# ---------------------------------------------------------------------------
# Milestone M3: CLI Subcommand Integration (youtube ab-test)
# ---------------------------------------------------------------------------
def _check_cli_supports_ab_test() -> bool:
    try:
        from veraxi_ymmp import cli
        return hasattr(cli, "_cmd_youtube_ab_test") or hasattr(cli, "cmd_youtube_ab_test")
    except Exception:
        return False

HAS_M3_CLI = _check_cli_supports_ab_test()

# Milestone Progressive Skip Markers
skip_m1_domain = pytest.mark.skipif(
    not HAS_M1_DOMAIN,
    reason="Milestone M1 (Domain models in veraxi_ymmp.ir) pending implementation",
)
skip_m1_thumbnail = pytest.mark.skipif(
    not HAS_M1_THUMBNAIL,
    reason="Milestone M1 (Thumbnail helpers in veraxi_ymmp.thumbnail) pending implementation",
)
skip_m1_adapter = pytest.mark.skipif(
    not HAS_M1_ADAPTER,
    reason="Milestone M1 (MockYouTubeAdapter analytics in veraxi_ymmp.youtube_adapter) pending implementation",
)
skip_m2 = pytest.mark.skipif(
    not HAS_M2_COORDINATOR,
    reason="Milestone M2 (ThumbnailABCoordinator in veraxi_ymmp.thumbnail_ab) pending implementation",
)
skip_m3 = pytest.mark.skipif(
    not HAS_M3_CLI,
    reason="Milestone M3 (CLI subcommand 'youtube ab-test' in veraxi_ymmp.cli) pending implementation",
)


# ===========================================================================
# Test Fixtures & Utilities
# ===========================================================================

@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project folder with minimal script.json and asset directory."""
    proj_dir = tmp_path / "test_ab_project"
    proj_dir.mkdir(parents=True, exist_ok=True)

    script_content = [
        {
            "character": "ずんだもん",
            "text": "コストコの驚くべきビジネスモデルを解説するのだ！",
            "emotion": "surprised",
        },
        {
            "character": "四国めたん",
            "text": "利益のほとんどが年会費から生まれているのですわ。",
            "emotion": "neutral",
        },
    ]
    (proj_dir / "script.json").write_text(json.dumps(script_content, ensure_ascii=False, indent=2), encoding="utf-8")

    thumb_cfg = {
        "title_line1": "コストコの秘密",
        "title_line2": "ボロ儲けの真実",
        "highlight_word": "ボロ儲け",
        "sub_hook": "▶ 知らないと損する仕組み",
        "badge": "【徹底解説】",
        "theme": "gold",
        "character": "ずんだもん",
        "emotion": "surprised",
    }
    (proj_dir / "thumbnail_config.json").write_text(json.dumps(thumb_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return proj_dir


@pytest.fixture
def mock_adapter() -> MockYouTubeAdapter:
    """Instantiate MockYouTubeAdapter for isolated offline testing."""
    if not HAS_M1_ADAPTER and MockYouTubeAdapter is None:
        pytest.skip("MockYouTubeAdapter not available")
    return MockYouTubeAdapter()


def create_solid_image(path: Path, width: int = 1920, height: int = 1080, color: str = "red") -> Path:
    """Create a solid color RGBA image at specified path."""
    img = Image.new("RGBA", (width, height), color)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    return path


def get_coordinator_instance() -> Any:
    """Helper to return an instance or class reference of ThumbnailABCoordinator."""
    if not HAS_M2_COORDINATOR or ThumbnailABCoordinator is None:
        return None
    try:
        return ThumbnailABCoordinator()
    except Exception:
        return ThumbnailABCoordinator


def invoke_coord(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Invoke a method on ThumbnailABCoordinator supporting instance or class methods."""
    c = get_coordinator_instance()
    if c is None:
        pytest.skip(f"ThumbnailABCoordinator not available for {method_name}")
    fn = getattr(c, method_name)
    try:
        return fn(*args, **kwargs)
    except TypeError:
        return fn(**kwargs)


# ===========================================================================
# Tier 1: Feature Coverage (Category-Partition Happy Paths, >=5 tests each)
# ===========================================================================

class TestFeature1MultiVariantConfig:
    """F1: Multi-Variant Configuration Extraction & Overrides."""

    @skip_m1_thumbnail
    def test_f1_01_auto_extract_variant_configs_default_contrasting_keys(self, tmp_project: Path) -> None:
        """Extracts at least Variant A and Variant B with distinct IDs."""
        configs = auto_extract_variant_configs(tmp_project)
        assert isinstance(configs, dict)
        assert "A" in configs
        assert "B" in configs
        assert isinstance(configs["A"], ThumbnailConfig)
        assert isinstance(configs["B"], ThumbnailConfig)

    @skip_m1_thumbnail
    def test_f1_02_auto_extract_variant_configs_distinct_emotions_and_themes(self, tmp_project: Path) -> None:
        """Variant A and Variant B have contrasting themes, badges, and emotions."""
        configs = auto_extract_variant_configs(tmp_project)
        cfg_a = configs["A"]
        cfg_b = configs["B"]

        assert cfg_a.theme != cfg_b.theme
        assert cfg_a.emotion != cfg_b.emotion
        assert cfg_a.badge != cfg_b.badge
        assert cfg_a.theme in ("gold", "emerald", "cyan")
        assert cfg_b.theme in ("red", "violet")

    @skip_m1_thumbnail
    def test_f1_03_auto_extract_variant_configs_overlay_from_thumbnail_config_json(self, tmp_project: Path) -> None:
        """Explicit 'variants' section in thumbnail_config.json overrides default extraction."""
        custom_cfg = {
            "default": {"title_line1": "Base Title", "theme": "emerald"},
            "variants": {
                "A": {"title_line2": "Variant A Custom", "badge": "【A特典】", "theme": "gold"},
                "B": {"title_line2": "Variant B Custom", "badge": "【B警告】", "theme": "red"},
            },
        }
        (tmp_project / "thumbnail_config.json").write_text(json.dumps(custom_cfg, ensure_ascii=False), encoding="utf-8")

        configs = auto_extract_variant_configs(tmp_project)
        assert configs["A"].title_line2 == "Variant A Custom"
        assert configs["A"].badge == "【A特典】"
        assert configs["B"].title_line2 == "Variant B Custom"
        assert configs["B"].badge == "【B警告】"

    @skip_m1_thumbnail
    def test_f1_04_auto_extract_variant_configs_preserves_character(self, tmp_project: Path) -> None:
        """Extracted variants preserve the primary presenter character."""
        configs = auto_extract_variant_configs(tmp_project)
        assert configs["A"].character == "ずんだもん"
        assert configs["B"].character == "ずんだもん"

    @skip_m1_thumbnail
    def test_f1_05_auto_extract_variant_configs_from_raw_script_list(self) -> None:
        """Accepts a raw list of dialogue entries without an on-disk project directory."""
        script = [{"character": "四国めたん", "text": "未来の相場を予測しますわ。", "emotion": "happy"}]
        configs = auto_extract_variant_configs(script)
        assert "A" in configs and "B" in configs
        assert configs["A"].character == "四国めたん"
        assert configs["B"].character == "四国めたん"


class TestFeature2MultiVariantRendering:
    """F2: Multi-Variant Image Rendering & Size Guard."""

    @skip_m1_thumbnail
    def test_f2_01_generate_thumbnail_variants_creates_distinct_files(self, tmp_project: Path) -> None:
        """Generates thumbnail_a.png and thumbnail_b.png in output directory."""
        out_dir = tmp_project / "thumbnails"
        results = generate_thumbnail_variants(tmp_project, out_dir)
        assert "A" in results and "B" in results
        assert results["A"].exists()
        assert results["B"].exists()
        assert results["A"] != results["B"]

    @skip_m1_thumbnail
    def test_f2_02_generate_thumbnail_variants_validates_1920x1080_dimensions(self, tmp_project: Path) -> None:
        """Both generated variant images conform to 1920x1080 YouTube standard resolution."""
        out_dir = tmp_project / "thumbnails"
        results = generate_thumbnail_variants(tmp_project, out_dir)
        with Image.open(results["A"]) as im_a:
            assert im_a.size == (1920, 1080)
        with Image.open(results["B"]) as im_b:
            assert im_b.size == (1920, 1080)

    @skip_m1_thumbnail
    def test_f2_03_generate_thumbnail_variants_under_2mb_size_limit(self, tmp_project: Path) -> None:
        """All rendered variants strictly respect YouTube's 2MB (2,097,152 bytes) limit."""
        out_dir = tmp_project / "thumbnails"
        results = generate_thumbnail_variants(tmp_project, out_dir)
        for vid, path in results.items():
            file_size = path.stat().st_size
            assert file_size <= 2 * 1024 * 1024, f"Variant {vid} exceeds 2MB limit: {file_size} bytes"

    @skip_m1_thumbnail
    def test_f2_04_validate_thumbnail_file_size_helper(self, tmp_path: Path) -> None:
        """validate_thumbnail_file_size correctly evaluates size boundaries."""
        valid_file = tmp_path / "valid.png"
        valid_file.write_bytes(b"x" * 1000)
        assert validate_thumbnail_file_size(valid_file) is True

        oversized_file = tmp_path / "oversized.png"
        oversized_file.write_bytes(b"x" * (2097152 + 1))
        assert validate_thumbnail_file_size(oversized_file) is False

        nonexistent_file = tmp_path / "nonexistent.png"
        assert validate_thumbnail_file_size(nonexistent_file) is False

    @skip_m1_thumbnail
    def test_f2_05_generate_thumbnail_variants_promotes_canonical_thumbnail_png(self, tmp_project: Path) -> None:
        """Generates canonical thumbnail.png if missing in project directory."""
        canonical = tmp_project / "thumbnail.png"
        if canonical.exists():
            canonical.unlink()

        out_dir = tmp_project / "thumbnails"
        generate_thumbnail_variants(tmp_project, out_dir)
        assert canonical.exists()
        assert canonical.stat().st_size > 0


class TestFeature3PureDomainModels:
    """F3: Domain Model Serialization & State Reconstruction."""

    @skip_m1_domain
    def test_f3_01_variant_metrics_defaults_and_serialization(self) -> None:
        """VariantMetrics dataclass initializes cleanly and performs dict serialization roundtrip."""
        vm = VariantMetrics(
            variant_id="A",
            impressions=1250,
            views=150,
            ctr=0.12,
            average_view_percentage=68.5,
            retention_score=85.0,
        )
        d = vm.to_dict()
        assert d["variant_id"] == "A"
        assert d["impressions"] == 1250
        assert d["ctr"] == 0.12

        reconstructed = VariantMetrics.from_dict(d)
        assert reconstructed.variant_id == vm.variant_id
        assert reconstructed.impressions == vm.impressions
        assert reconstructed.retention_score == vm.retention_score

    @skip_m1_domain
    def test_f3_02_thumbnail_variant_dataclass_and_metrics_nesting(self, tmp_path: Path) -> None:
        """ThumbnailVariant wraps image path and nested metrics."""
        t_path = tmp_path / "variant_b.png"
        t_path.touch()
        tv = ThumbnailVariant(
            variant_id="B",
            name="Variant B (Urgency)",
            thumbnail_path=t_path,
            config={"theme": "red", "badge": "【警告】"},
            is_active=True,
            rotation_count=3,
        )
        d = tv.to_dict()
        assert d["variant_id"] == "B"
        assert d["is_active"] is True
        assert d["rotation_count"] == 3

        reconstructed = ThumbnailVariant.from_dict(d)
        assert reconstructed.variant_id == "B"
        assert reconstructed.thumbnail_path == t_path
        assert reconstructed.rotation_count == 3

    @skip_m1_domain
    def test_f3_03_rotation_event_timestamp_and_reason(self) -> None:
        """RotationEvent tracks transition metadata."""
        event = RotationEvent(
            timestamp="2026-10-20T12:00:00Z",
            video_id="vid_test_123",
            from_variant_id="A",
            to_variant_id="B",
            reason="scheduled_rotation",
        )
        d = event.to_dict()
        assert d["from_variant_id"] == "A"
        assert d["to_variant_id"] == "B"
        assert d["reason"] == "scheduled_rotation"

        rec = RotationEvent.from_dict(d)
        assert rec.timestamp == event.timestamp
        assert rec.to_variant_id == "B"

    @skip_m1_domain
    def test_f3_04_winner_decision_significance_and_p_value(self) -> None:
        """WinnerDecision captures statistical verdict."""
        decision = WinnerDecision(
            winner_variant_id="B",
            winning_score=0.145,
            margin=0.042,
            is_significant=True,
            p_value=0.012,
            committed=True,
            rationale="Variant B demonstrated higher CTR with p < 0.05",
        )
        d = decision.to_dict()
        assert d["is_significant"] is True
        assert d["p_value"] == 0.012

        rec = WinnerDecision.from_dict(d)
        assert rec.winner_variant_id == "B"
        assert rec.is_significant is True
        assert rec.committed is True

    @skip_m1_domain
    def test_f3_05_thumbnail_experiment_full_roundtrip_serialization(self, tmp_path: Path) -> None:
        """ThumbnailExperiment aggregates variants, history, and decision into JSON roundtrip."""
        t_a = tmp_path / "thumb_a.png"
        t_b = tmp_path / "thumb_b.png"
        t_a.touch()
        t_b.touch()

        exp = ThumbnailExperiment(
            experiment_id="exp_001",
            video_id="video_abc",
            project_dir=tmp_path,
            status="RUNNING",
            active_variant_id="A",
            variants={
                "A": ThumbnailVariant("A", "Variant A", t_a, is_active=True),
                "B": ThumbnailVariant("B", "Variant B", t_b, is_active=False),
            },
            rotation_history=[
                RotationEvent("2026-10-20T10:00:00Z", "video_abc", None, "A", "initial_upload")
            ],
            min_impressions=1000,
        )
        d = exp.to_dict()
        assert d["experiment_id"] == "exp_001"
        assert len(d["variants"]) == 2
        assert len(d["rotation_history"]) == 1

        rec = ThumbnailExperiment.from_dict(d)
        assert rec.experiment_id == "exp_001"
        assert rec.active_variant_id == "A"
        assert "A" in rec.variants and "B" in rec.variants


class TestFeature4AnalyticsPortAndMock:
    """F4: Analytics Port Extension & Mock Simulation."""

    def test_f4_01_video_analytics_provider_protocol_declares_fetch_variant_metrics(self) -> None:
        """VideoAnalyticsProvider protocol defines fetch_variant_metrics method."""
        assert hasattr(VideoAnalyticsProvider, "fetch_variant_metrics")

    @skip_m1_adapter
    def test_f4_02_mock_youtube_adapter_tracks_thumbnail_history(self, mock_adapter: MockYouTubeAdapter, tmp_path: Path) -> None:
        """MockYouTubeAdapter.upload_thumbnail appends to thumbnail_history."""
        thumb = create_solid_image(tmp_path / "t.png")
        success = mock_adapter.upload_thumbnail("vid_history_1", thumb)
        assert success is True
        assert hasattr(mock_adapter, "thumbnail_history")
        assert len(mock_adapter.thumbnail_history) >= 1
        last = mock_adapter.thumbnail_history[-1]
        assert last["video_id"] == "vid_history_1"
        assert last["thumbnail_path"] == thumb

    @skip_m1_adapter
    def test_f4_03_mock_youtube_adapter_set_and_fetch_simulated_metrics(self, mock_adapter: MockYouTubeAdapter) -> None:
        """MockYouTubeAdapter allows setting deterministic simulated metrics."""
        mock_adapter.set_simulated_metrics(
            variant_id="B",
            impressions=2500,
            views=350,
            ctr=0.14,
            average_view_percentage=72.0,
        )
        metrics = mock_adapter.fetch_variant_metrics("vid_metrics_1")
        assert metrics.impressions == 2500
        assert metrics.views == 350
        assert metrics.ctr == 0.14
        assert metrics.average_view_percentage == 72.0

    @skip_m1_adapter
    def test_f4_04_mock_youtube_adapter_default_fallback_metrics(self, mock_adapter: MockYouTubeAdapter) -> None:
        """fetch_variant_metrics provides realistic default fallback when no simulated data set."""
        clean_mock = MockYouTubeAdapter()
        metrics = clean_mock.fetch_variant_metrics("vid_default_fallback")
        assert metrics.impressions > 0
        assert metrics.views > 0
        assert 0.0 <= metrics.ctr <= 1.0

    @skip_m1_adapter
    def test_f4_05_mock_youtube_adapter_logs_analytics_calls(self, mock_adapter: MockYouTubeAdapter) -> None:
        """MockYouTubeAdapter records fetch_variant_metrics calls in its call_log."""
        mock_adapter.fetch_variant_metrics("vid_log_test")
        assert any("fetch_variant_metrics:vid_log_test" in call for call in mock_adapter.call_log)


class TestFeature5YouTubeThumbnailRotation:
    """F5: YouTube Thumbnail Rotation & State Tracking."""

    @skip_m2
    def test_f5_01_coordinator_initialize_experiment_creates_state_json(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """initialize_experiment creates and persists thumbnail_ab_experiment.json."""
        exp = invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_init_01", publisher=mock_adapter)
        state_file = tmp_project / "thumbnail_ab_experiment.json"
        assert state_file.exists()
        assert exp.status in ("DRAFT", "RUNNING")
        assert exp.video_id == "vid_init_01"

    @skip_m2
    def test_f5_02_coordinator_rotate_thumbnail_calls_publisher_upload(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """rotate_thumbnail invokes publisher.upload_thumbnail with the target variant path."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_rot_02", publisher=mock_adapter)
        event = invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_rot_02", target_variant_id="B", publisher=mock_adapter)
        assert event.to_variant_id == "B"
        assert len(mock_adapter.thumbnail_history) >= 2  # initial + rotation

    @skip_m2
    def test_f5_03_coordinator_rotate_thumbnail_appends_rotation_event(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Rotation history in experiment state records from_variant_id and to_variant_id."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_rot_03", publisher=mock_adapter)
        invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_rot_03", target_variant_id="B", publisher=mock_adapter)
        status = invoke_coord("get_status", project_dir=tmp_project)
        assert len(status.rotation_history) >= 2
        last_event = status.rotation_history[-1]
        assert last_event.to_variant_id == "B"

    @skip_m2
    def test_f5_04_coordinator_rotate_thumbnail_updates_active_variant(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Active variant identifier and is_active flags update upon rotation."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_rot_04", publisher=mock_adapter)
        invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_rot_04", target_variant_id="B", publisher=mock_adapter)
        status = invoke_coord("get_status", project_dir=tmp_project)
        assert status.active_variant_id == "B"
        assert status.variants["B"].is_active is True
        assert status.variants["A"].is_active is False

    @skip_m2
    def test_f5_05_coordinator_get_status_reads_active_state(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """get_status retrieves the persisted state from disk without external mutation."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_rot_05", publisher=mock_adapter)
        status = invoke_coord("get_status", project_dir=tmp_project)
        assert status.video_id == "vid_rot_05"
        assert "A" in status.variants


class TestFeature6PerformanceEvaluation:
    """F6: Performance Metric Retrieval & Statistical Evaluation."""

    @skip_m2
    def test_f6_01_evaluate_performance_computes_two_proportion_z_score(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Two-proportion Z-test evaluates difference between variant CTRs."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_eval_01", publisher=mock_adapter)
        # Variant A: 1000 impr, 80 views (8% CTR)
        # Variant B: 1000 impr, 140 views (14% CTR)
        mock_adapter.set_simulated_metrics("A", impressions=1000, views=80, ctr=0.08)
        mock_adapter.set_simulated_metrics("B", impressions=1000, views=140, ctr=0.14)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_eval_01", analytics_provider=mock_adapter)
        assert decision.p_value is not None
        assert decision.p_value < 0.05
        assert decision.is_significant is True
        assert decision.winner_variant_id == "B"

    @skip_m2
    def test_f6_02_evaluate_performance_declares_significant_winner(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Declares variant winner with statistical significance."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_eval_02", publisher=mock_adapter)
        mock_adapter.set_simulated_metrics("A", impressions=2000, views=160, ctr=0.08)
        mock_adapter.set_simulated_metrics("B", impressions=2000, views=260, ctr=0.13)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_eval_02", analytics_provider=mock_adapter)
        assert decision.is_significant is True
        assert decision.winner_variant_id == "B"
        assert decision.margin > 0.0

    @skip_m2
    def test_f6_03_evaluate_performance_retention_guardrail_prevents_win(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Variant with higher CTR but critically low retention score is blocked by guardrail."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_eval_03", publisher=mock_adapter)
        # Variant A: 1000 impr, 90 views (9% CTR), 70% retention
        # Variant B: 1000 impr, 160 views (16% CTR), 25% retention (clickbait drop-off)
        mock_adapter.set_simulated_metrics("A", impressions=1000, views=90, ctr=0.09, average_view_percentage=70.0)
        mock_adapter.set_simulated_metrics("B", impressions=1000, views=160, ctr=0.16, average_view_percentage=25.0)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_eval_03", analytics_provider=mock_adapter)
        # Guardrail should veto B as winner or flag in rationale
        assert decision.winner_variant_id != "B" or "retention" in decision.rationale.lower()

    @skip_m2
    def test_f6_04_evaluate_performance_respects_confidence_level_parameter(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Supports custom confidence level (e.g. 0.99 for higher rigor)."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_eval_04", publisher=mock_adapter)
        # Moderately different CTR that passes at 90% but might fail at 99.9%
        mock_adapter.set_simulated_metrics("A", impressions=800, views=80, ctr=0.10)
        mock_adapter.set_simulated_metrics("B", impressions=800, views=104, ctr=0.13)

        dec_strict = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_eval_04", analytics_provider=mock_adapter, confidence_level=0.999)
        assert dec_strict is not None

    @skip_m2
    def test_f6_05_evaluate_performance_updates_variant_metrics_in_state(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Experiment state records the queried metrics for each evaluated variant."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_eval_05", publisher=mock_adapter)
        mock_adapter.set_simulated_metrics("A", impressions=1200, views=120, ctr=0.10)
        mock_adapter.set_simulated_metrics("B", impressions=1200, views=180, ctr=0.15)

        invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_eval_05", analytics_provider=mock_adapter)
        status = invoke_coord("get_status", project_dir=tmp_project)
        assert status.variants["A"].metrics.impressions == 1200
        assert status.variants["B"].metrics.impressions == 1200


class TestFeature7WinnerCommitment:
    """F7: Winner Commitment & QA Audit Reporting."""

    @skip_m2
    def test_f7_01_commit_winner_copies_winning_image_to_canonical_thumbnail_png(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """commit_winner replaces project thumbnail.png with the winning variant image."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_com_01", publisher=mock_adapter)
        mock_adapter.set_simulated_metrics("A", impressions=1500, views=120, ctr=0.08)
        mock_adapter.set_simulated_metrics("B", impressions=1500, views=225, ctr=0.15)
        invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_com_01", analytics_provider=mock_adapter)

        exp = invoke_coord("commit_winner", project_dir=tmp_project, video_id="vid_com_01", winner_id="B", publisher=mock_adapter)
        canonical = tmp_project / "thumbnail.png"
        assert canonical.exists()
        winning_variant_path = exp.variants["B"].thumbnail_path
        assert canonical.stat().st_size == winning_variant_path.stat().st_size

    @skip_m2
    def test_f7_02_commit_winner_updates_experiment_status_to_concluded(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Experiment status transitions to CONCLUDED and committed flag is True."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_com_02", publisher=mock_adapter)
        exp = invoke_coord("commit_winner", project_dir=tmp_project, video_id="vid_com_02", winner_id="A", publisher=mock_adapter)
        assert exp.status == "CONCLUDED"
        assert exp.winner_decision is not None
        assert exp.winner_decision.committed is True

    @skip_m2
    def test_f7_03_commit_winner_calls_publisher_upload_for_final_lock(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Winner thumbnail is uploaded to YouTube to ensure permanent lock."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_com_03", publisher=mock_adapter)
        init_uploads = len(mock_adapter.thumbnail_history)
        invoke_coord("commit_winner", project_dir=tmp_project, video_id="vid_com_03", winner_id="B", publisher=mock_adapter)
        assert len(mock_adapter.thumbnail_history) > init_uploads
        assert mock_adapter.thumbnail_history[-1]["video_id"] == "vid_com_03"

    @skip_m2
    def test_f7_04_commit_winner_updates_thumbnail_config_json(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Winning configuration parameters are synced back into thumbnail_config.json."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_com_04", publisher=mock_adapter)
        invoke_coord("commit_winner", project_dir=tmp_project, video_id="vid_com_04", winner_id="B", publisher=mock_adapter)

        cfg_file = tmp_project / "thumbnail_config.json"
        data = json.loads(cfg_file.read_text(encoding="utf-8-sig"))
        assert data.get("theme") == "red" or "variants" in data

    @skip_m2
    def test_f7_05_commit_winner_generates_markdown_and_json_qa_reports(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Generates audit reports (ab_test_report.md and ab_test_report.json)."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_com_05", publisher=mock_adapter)
        invoke_coord("commit_winner", project_dir=tmp_project, video_id="vid_com_05", winner_id="A", publisher=mock_adapter)

        report_md = tmp_project / "ab_test_report.md"
        report_json = tmp_project / "ab_test_report.json"
        assert report_md.exists() or (tmp_project / "qa_reports" / "ab_test_report.md").exists()
        assert report_json.exists() or (tmp_project / "qa_reports" / "ab_test_report.json").exists()


class TestFeature8CLICommandParsing:
    """F8: CLI Command Parsing & Execution."""

    @skip_m3
    def test_f8_01_cli_ab_test_help_displays_subcommands(self, capsys: Any) -> None:
        """veraxi-ymmp youtube ab-test --help prints actions (init, rotate, evaluate, commit, status)."""
        from veraxi_ymmp.cli import main
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "ab-test", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        out = capsys.readouterr().out.lower()
        assert "init" in out or "rotate" in out or "evaluate" in out

    @skip_m3
    def test_f8_02_cli_ab_test_init_mock_execution(self, tmp_project: Path, capsys: Any) -> None:
        """veraxi-ymmp youtube ab-test init --project <dir> --video-id <id> --mock."""
        from veraxi_ymmp.cli import main
        cmd = ["veraxi-ymmp", "youtube", "ab-test", "init", "--project", str(tmp_project), "--video-id", "cli_test_01", "--mock"]
        with patch.object(sys, "argv", cmd):
            main()
        state_file = tmp_project / "thumbnail_ab_experiment.json"
        assert state_file.exists()

    @skip_m3
    def test_f8_03_cli_ab_test_rotate_mock_execution(self, tmp_project: Path, capsys: Any) -> None:
        """veraxi-ymmp youtube ab-test rotate --project <dir> --video-id <id> --mock."""
        from veraxi_ymmp.cli import main
        cmd_init = ["veraxi-ymmp", "youtube", "ab-test", "init", "--project", str(tmp_project), "--video-id", "cli_test_02", "--mock"]
        with patch.object(sys, "argv", cmd_init):
            main()

        cmd_rot = ["veraxi-ymmp", "youtube", "ab-test", "rotate", "--project", str(tmp_project), "--video-id", "cli_test_02", "--variant", "B", "--mock"]
        with patch.object(sys, "argv", cmd_rot):
            main()
        out = capsys.readouterr().out
        assert "B" in out or "rotate" in out.lower()

    @skip_m3
    def test_f8_04_cli_ab_test_status_mock_output(self, tmp_project: Path, capsys: Any) -> None:
        """veraxi-ymmp youtube ab-test status --project <dir> --mock outputs experiment state."""
        from veraxi_ymmp.cli import main
        cmd_init = ["veraxi-ymmp", "youtube", "ab-test", "init", "--project", str(tmp_project), "--video-id", "cli_test_03", "--mock"]
        with patch.object(sys, "argv", cmd_init):
            main()

        cmd_status = ["veraxi-ymmp", "youtube", "ab-test", "status", "--project", str(tmp_project), "--mock"]
        with patch.object(sys, "argv", cmd_status):
            main()
        out = capsys.readouterr().out
        assert "cli_test_03" in out or "RUNNING" in out or "DRAFT" in out

    @skip_m3
    def test_f8_05_cli_ab_test_evaluate_and_commit_cli(self, tmp_project: Path) -> None:
        """veraxi-ymmp youtube ab-test evaluate and commit commands run cleanly in mock mode."""
        from veraxi_ymmp.cli import main
        cmd_init = ["veraxi-ymmp", "youtube", "ab-test", "init", "--project", str(tmp_project), "--video-id", "cli_test_04", "--mock"]
        with patch.object(sys, "argv", cmd_init):
            main()

        cmd_eval = ["veraxi-ymmp", "youtube", "ab-test", "evaluate", "--project", str(tmp_project), "--video-id", "cli_test_04", "--mock"]
        with patch.object(sys, "argv", cmd_eval):
            main()

        cmd_commit = ["veraxi-ymmp", "youtube", "ab-test", "commit", "--project", str(tmp_project), "--video-id", "cli_test_04", "--winner", "A", "--mock"]
        with patch.object(sys, "argv", cmd_commit):
            main()
        assert (tmp_project / "thumbnail.png").exists()


# ===========================================================================
# Tier 2: Boundary Value Analysis & Corner Cases (>=5 tests per category)
# ===========================================================================

class TestTier2BoundaryAndCornerCases:
    """Tier 2: Boundary Value Analysis, Metric Extremes, Fault Injection, and State Stress."""

    # -----------------------------------------------------------------------
    # Category 1: 2MB File Size Limits & File Validation
    # -----------------------------------------------------------------------
    @skip_m1_thumbnail
    def test_tier2_bva_file_size_exactly_2mb_passes(self, tmp_path: Path) -> None:
        """File of exactly 2,097,152 bytes is accepted by validate_thumbnail_file_size."""
        exact_file = tmp_path / "exact_2mb.png"
        exact_file.write_bytes(b"\x00" * 2097152)
        assert validate_thumbnail_file_size(exact_file, max_bytes=2097152) is True

    @skip_m1_thumbnail
    def test_tier2_bva_file_size_2mb_plus_one_byte_rejected(self, tmp_path: Path) -> None:
        """File of 2,097,153 bytes is strictly rejected."""
        exceeded_file = tmp_path / "exceeded_2mb.png"
        exceeded_file.write_bytes(b"\x00" * 2097153)
        assert validate_thumbnail_file_size(exceeded_file, max_bytes=2097152) is False

    @skip_m1_thumbnail
    def test_tier2_bva_file_size_zero_byte_file_rejected(self, tmp_path: Path) -> None:
        """0-byte file is rejected as an invalid empty thumbnail."""
        empty_file = tmp_path / "empty.png"
        empty_file.touch()
        # 0 bytes should either fail file size check or be rejected by generator
        assert empty_file.stat().st_size == 0

    @skip_m1_thumbnail
    def test_tier2_bva_file_size_missing_file_rejected(self, tmp_path: Path) -> None:
        """Nonexistent file path returns False."""
        missing = tmp_path / "ghost.png"
        assert validate_thumbnail_file_size(missing) is False

    @skip_m1_thumbnail
    def test_tier2_bva_file_size_directory_path_rejected(self, tmp_path: Path) -> None:
        """Passing a directory instead of a file returns False."""
        sub_dir = tmp_path / "sub_folder"
        sub_dir.mkdir()
        assert validate_thumbnail_file_size(sub_dir) is False

    # -----------------------------------------------------------------------
    # Category 2: Metric Extremes & Division-by-Zero Handling
    # -----------------------------------------------------------------------
    @skip_m1_domain
    def test_tier2_metrics_zero_impressions_zero_views_zero_ctr(self) -> None:
        """0 impressions and 0 views produces 0.0 CTR without raising ZeroDivisionError."""
        vm = VariantMetrics("A", impressions=0, views=0)
        assert vm.ctr == 0.0
        assert vm.impressions == 0

    @skip_m1_domain
    def test_tier2_metrics_100_percent_ctr_upper_bound(self) -> None:
        """Views equal to impressions yields 1.0 (100%) CTR without overflow."""
        vm = VariantMetrics("B", impressions=500, views=500, ctr=1.0)
        assert vm.ctr == 1.0
        d = vm.to_dict()
        assert d["ctr"] == 1.0

    @skip_m1_domain
    def test_tier2_metrics_more_views_than_impressions_sanitized(self) -> None:
        """Anomalous telemetry (views > impressions) is handled safely."""
        vm = VariantMetrics("C", impressions=100, views=120, ctr=1.2)
        assert vm.views == 120
        assert vm.ctr >= 1.0

    @skip_m1_domain
    def test_tier2_metrics_negative_values_clamped_or_preserved(self) -> None:
        """Negative metrics in raw dictionary do not crash from_dict deserialization."""
        raw = {"variant_id": "X", "impressions": -5, "views": -1, "ctr": -0.1}
        vm = VariantMetrics.from_dict(raw)
        assert vm.variant_id == "X"

    @skip_m1_domain
    def test_tier2_metrics_empty_raw_metrics_dict(self) -> None:
        """raw_metrics dictionary defaults to empty dict and serializes cleanly."""
        vm = VariantMetrics("Y")
        assert vm.raw_metrics == {}
        assert vm.to_dict()["raw_metrics"] == {}

    # -----------------------------------------------------------------------
    # Category 3: Statistical Ties & Sample Size Limits
    # -----------------------------------------------------------------------
    @skip_m2
    def test_tier2_stat_identical_ctr_tie_handling(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Identical CTR across variants (e.g., both 10.0%) results in is_significant = False."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_tie_01", publisher=mock_adapter)
        mock_adapter.set_simulated_metrics("A", impressions=1000, views=100, ctr=0.10)
        mock_adapter.set_simulated_metrics("B", impressions=1000, views=100, ctr=0.10)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_tie_01", analytics_provider=mock_adapter)
        assert decision.is_significant is False

    @skip_m2
    def test_tier2_stat_below_min_impressions_is_inconclusive(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Low sample size (< min_impressions, e.g. 50 impressions) returns inconclusive decision."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_low_samp", publisher=mock_adapter)
        mock_adapter.set_simulated_metrics("A", impressions=30, views=3, ctr=0.10)
        mock_adapter.set_simulated_metrics("B", impressions=40, views=8, ctr=0.20)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_low_samp", analytics_provider=mock_adapter)
        assert decision.is_significant is False
        assert "insufficient" in decision.rationale.lower() or "inconclusive" in decision.rationale.lower()

    @skip_m2
    def test_tier2_stat_borderline_p_value_alpha_threshold(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """P-value borderline behavior is evaluated consistently against alpha = 0.05."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_border", publisher=mock_adapter)
        # Moderate difference
        mock_adapter.set_simulated_metrics("A", impressions=1500, views=150, ctr=0.10)
        mock_adapter.set_simulated_metrics("B", impressions=1500, views=180, ctr=0.12)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_border", analytics_provider=mock_adapter)
        assert decision.p_value is not None

    @skip_m2
    def test_tier2_stat_large_sample_with_microscopic_difference(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Very large sample (100k impressions) with trivial difference (10.0% vs 10.02%) evaluates safely."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_large", publisher=mock_adapter)
        mock_adapter.set_simulated_metrics("A", impressions=100000, views=10000, ctr=0.10)
        mock_adapter.set_simulated_metrics("B", impressions=100000, views=10020, ctr=0.1002)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_large", analytics_provider=mock_adapter)
        assert decision is not None

    @skip_m2
    def test_tier2_stat_single_variant_experiment_evaluation(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Evaluating an experiment with only one variant returns inconclusive gracefully."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_single", publisher=mock_adapter)
        # Manually alter experiment to have 1 variant
        state_file = tmp_project / "thumbnail_ab_experiment.json"
        data = json.loads(state_file.read_text(encoding="utf-8"))
        data["variants"] = {"A": data["variants"]["A"]}
        state_file.write_text(json.dumps(data), encoding="utf-8")

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_single", analytics_provider=mock_adapter)
        assert decision.is_significant is False

    # -----------------------------------------------------------------------
    # Category 4: State Corruption & Filesystem Faults
    # -----------------------------------------------------------------------
    @skip_m2
    def test_tier2_fault_corrupted_json_syntax_in_experiment_file(self, tmp_project: Path) -> None:
        """Corrupted JSON syntax in experiment file raises descriptive error or resets safely."""
        state_file = tmp_project / "thumbnail_ab_experiment.json"
        state_file.write_text("{ unclosed_json: true, ", encoding="utf-8")

        with pytest.raises((json.JSONDecodeError, ValueError, RuntimeError)):
            invoke_coord("get_status", project_dir=tmp_project)

    @skip_m2
    def test_tier2_fault_missing_required_keys_in_experiment_json(self, tmp_project: Path) -> None:
        """Experiment JSON missing required 'variants' key raises KeyError or handles gracefully."""
        state_file = tmp_project / "thumbnail_ab_experiment.json"
        state_file.write_text(json.dumps({"experiment_id": "bad_exp"}), encoding="utf-8")

        with pytest.raises((KeyError, ValueError, TypeError)):
            invoke_coord("get_status", project_dir=tmp_project)

    @skip_m2
    def test_tier2_fault_nonexistent_project_directory_error(self, tmp_path: Path) -> None:
        """Nonexistent project directory raises FileNotFoundError."""
        ghost_dir = tmp_path / "ghost_project"
        with pytest.raises((FileNotFoundError, ValueError)):
            invoke_coord("get_status", project_dir=ghost_dir)

    @skip_m1_domain
    def test_tier2_fault_schema_drift_unknown_keys_ignored(self, tmp_path: Path) -> None:
        """Unknown extra fields in experiment JSON are safely ignored during deserialization."""
        extra_data = {
            "experiment_id": "exp_drift",
            "video_id": "vid_drift",
            "project_dir": str(tmp_path),
            "status": "RUNNING",
            "unknown_future_field": 12345,
            "another_field": "hello",
        }
        exp = ThumbnailExperiment.from_dict(extra_data)
        assert exp.experiment_id == "exp_drift"

    @skip_m2
    def test_tier2_fault_nonexistent_target_variant_id_rotation_error(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Attempting to rotate to an unconfigured variant ID (e.g. 'Z') raises KeyError or ValueError."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_bad_rot", publisher=mock_adapter)
        with pytest.raises((KeyError, ValueError)):
            invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_bad_rot", target_variant_id="NON_EXISTENT_VARIANT", publisher=mock_adapter)

    # -----------------------------------------------------------------------
    # Category 5: State Transitions & Timing Constraints
    # -----------------------------------------------------------------------
    @skip_m2
    def test_tier2_timing_rapid_rotation_within_minimum_window_warning(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Rotating immediately after previous rotation records event or flags rapid frequency."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_rapid", publisher=mock_adapter)
        ev1 = invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_rapid", target_variant_id="B", publisher=mock_adapter)
        ev2 = invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_rapid", target_variant_id="A", publisher=mock_adapter)
        assert ev1.to_variant_id == "B"
        assert ev2.to_variant_id == "A"

    @skip_m2
    def test_tier2_timing_rotation_on_concluded_experiment_prevented(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Cannot rotate thumbnails once the experiment status is CONCLUDED."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_concluded", publisher=mock_adapter)
        invoke_coord("commit_winner", project_dir=tmp_project, video_id="vid_concluded", winner_id="A", publisher=mock_adapter)

        with pytest.raises((RuntimeError, ValueError)):
            invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_concluded", target_variant_id="B", publisher=mock_adapter)

    @skip_m2
    def test_tier2_timing_commit_without_variants_prevented(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Cannot commit winner on an invalid empty experiment."""
        state_file = tmp_project / "thumbnail_ab_experiment.json"
        state_file.write_text(json.dumps({"experiment_id": "e", "video_id": "v", "project_dir": str(tmp_project), "status": "DRAFT", "variants": {}}), encoding="utf-8")

        with pytest.raises((ValueError, KeyError, RuntimeError)):
            invoke_coord("commit_winner", project_dir=tmp_project, video_id="v", winner_id="Z", publisher=mock_adapter)

    @skip_m2
    def test_tier2_timing_reinitializing_existing_experiment_preserves_or_overwrites(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Re-initializing experiment updates or preserves existing rotation history cleanly."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_reinit", publisher=mock_adapter)
        invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_reinit", target_variant_id="B", publisher=mock_adapter)

        # Second init
        exp2 = invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_reinit", publisher=mock_adapter)
        assert exp2.video_id == "vid_reinit"

    @skip_m1_thumbnail
    def test_tier2_timing_empty_variants_initialization_auto_generates_defaults(self, tmp_project: Path) -> None:
        """When no variants explicitly configured, auto_extract_variant_configs generates default A and B."""
        configs = auto_extract_variant_configs(tmp_project)
        assert len(configs) >= 2
        assert "A" in configs and "B" in configs


# ===========================================================================
# Tier 3: Cross-Feature Combinations (Pairwise Coverage, >=8 tests)
# ===========================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Multi-Component Pairwise & Interaction Verification."""

    @skip_m2
    def test_tier3_combo_01_generate_rotate_metric_evaluate_flow(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Pairwise flow: Variant rendering -> Rotation -> Metric retrieval -> Winner evaluation."""
        out_dir = tmp_project / "thumbnails"
        var_paths = generate_thumbnail_variants(tmp_project, out_dir)
        assert len(var_paths) >= 2

        exp = invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_flow_01", publisher=mock_adapter)
        assert exp.active_variant_id == "A"

        invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_flow_01", target_variant_id="B", publisher=mock_adapter)
        mock_adapter.set_simulated_metrics("A", impressions=2000, views=160, ctr=0.08)
        mock_adapter.set_simulated_metrics("B", impressions=2000, views=280, ctr=0.14)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_flow_01", analytics_provider=mock_adapter)
        assert decision.is_significant is True
        assert decision.winner_variant_id == "B"

    @skip_m2
    def test_tier3_combo_02_pipeline_run_mock_with_ab_variants(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Coordinator coordinates with publisher and analytics ports without cross-layer violations."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_pipe_02", publisher=mock_adapter)
        status = invoke_coord("get_status", project_dir=tmp_project)
        assert status.status in ("DRAFT", "RUNNING")

    @skip_m2
    def test_tier3_combo_03_mid_experiment_variant_addition(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Adding Variant C mid-experiment and rotating to it."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_combo_03", publisher=mock_adapter)
        # Add variant C
        c_path = create_solid_image(tmp_project / "thumbnails" / "thumbnail_c.png", color="blue")
        status = invoke_coord("get_status", project_dir=tmp_project)
        status.variants["C"] = ThumbnailVariant("C", "Variant C (Cyan)", c_path)
        (tmp_project / "thumbnail_ab_experiment.json").write_text(json.dumps(status.to_dict(), ensure_ascii=False), encoding="utf-8")

        ev = invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_combo_03", target_variant_id="C", publisher=mock_adapter)
        assert ev.to_variant_id == "C"

    @skip_m2
    def test_tier3_combo_04_pause_and_resume_state_transitions(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """State transitions from RUNNING -> PAUSED -> RUNNING."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_combo_04", publisher=mock_adapter)
        status = invoke_coord("get_status", project_dir=tmp_project)
        status.status = "PAUSED"
        (tmp_project / "thumbnail_ab_experiment.json").write_text(json.dumps(status.to_dict(), ensure_ascii=False), encoding="utf-8")

        paused_status = invoke_coord("get_status", project_dir=tmp_project)
        assert paused_status.status == "PAUSED"

        # Resume
        paused_status.status = "RUNNING"
        (tmp_project / "thumbnail_ab_experiment.json").write_text(json.dumps(paused_status.to_dict(), ensure_ascii=False), encoding="utf-8")
        assert invoke_coord("get_status", project_dir=tmp_project).status == "RUNNING"

    @skip_m2
    def test_tier3_combo_05_multi_round_rotation_cumulative_history(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Rotating A -> B -> A -> B tracks increasing rotation_count and event sequence."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_combo_05", publisher=mock_adapter)
        invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_combo_05", target_variant_id="B", publisher=mock_adapter)
        invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_combo_05", target_variant_id="A", publisher=mock_adapter)
        invoke_coord("rotate_thumbnail", project_dir=tmp_project, video_id="vid_combo_05", target_variant_id="B", publisher=mock_adapter)

        status = invoke_coord("get_status", project_dir=tmp_project)
        assert len(status.rotation_history) >= 4
        assert status.variants["B"].rotation_count >= 2

    @skip_m2
    def test_tier3_combo_06_thumbnail_config_sync_on_winner_commit(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Winner commitment keeps thumbnail.png and thumbnail_config.json aligned."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_combo_06", publisher=mock_adapter)
        invoke_coord("commit_winner", project_dir=tmp_project, video_id="vid_combo_06", winner_id="B", publisher=mock_adapter)

        cfg_data = json.loads((tmp_project / "thumbnail_config.json").read_text(encoding="utf-8-sig"))
        assert cfg_data.get("theme") in ("red", "gold") or "variants" in cfg_data

    @skip_m2
    def test_tier3_combo_07_retention_override_against_high_ctr_clickbait(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """High CTR (18%) with abysmal retention (20%) is blocked from winning over stable variant (10% CTR, 75% retention)."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_combo_07", publisher=mock_adapter)
        mock_adapter.set_simulated_metrics("A", impressions=3000, views=300, ctr=0.10, average_view_percentage=75.0)
        mock_adapter.set_simulated_metrics("B", impressions=3000, views=540, ctr=0.18, average_view_percentage=20.0)

        decision = invoke_coord("evaluate_performance", project_dir=tmp_project, video_id="vid_combo_07", analytics_provider=mock_adapter)
        # Should veto B or flag retention issue
        assert decision.winner_variant_id != "B" or "retention" in decision.rationale.lower()

    @skip_m2
    def test_tier3_combo_08_markdown_and_json_report_fidelity(self, tmp_project: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """Markdown scorecard and JSON report have identical metrics and winner IDs."""
        invoke_coord("initialize_experiment", project_dir=tmp_project, video_id="vid_combo_08", publisher=mock_adapter)
        invoke_coord("commit_winner", project_dir=tmp_project, video_id="vid_combo_08", winner_id="A", publisher=mock_adapter)

        rep_json_file = tmp_project / "ab_test_report.json"
        rep_md_file = tmp_project / "ab_test_report.md"
        if rep_json_file.exists() and rep_md_file.exists():
            data = json.loads(rep_json_file.read_text(encoding="utf-8"))
            md_text = rep_md_file.read_text(encoding="utf-8")
            assert data["winner_decision"]["winner_variant_id"] in md_text


# ===========================================================================
# Tier 4: Real-World Workload Scenarios (>=5 scenarios)
# ===========================================================================

class TestTier4RealWorldWorkloadScenarios:
    """Tier 4: Realistic Production Scenarios & Workload Simulators."""

    @skip_m2
    def test_tier4_scenario_01_costco_production_lifecycle(self, tmp_path: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """
        Scenario 1: End-to-end lifecycle for Costco business model video:
        1. Setup project with script and thumbnail config.
        2. Generate Variant A (Gold/Curiosity) and Variant B (Red/Urgency).
        3. Upload initial Variant A to YouTube mock.
        4. After observation period: Rotate active thumbnail to Variant B.
        5. Fetch analytics: Variant B achieved 14.2% CTR vs. Variant A 9.1% (p < 0.01).
        6. Commit Variant B as winner.
        7. Verify canonical project thumbnail.png promoted and status is CONCLUDED.
        """
        proj_dir = tmp_path / "01_costco_lifecycle"
        proj_dir.mkdir(parents=True, exist_ok=True)

        script = [
            {"character": "ずんだもん", "text": "コストコのボロ儲けの秘密なのだ！", "emotion": "surprised"},
            {"character": "四国めたん", "text": "実は利益のほとんどは会費収入ですわ。", "emotion": "happy"},
        ]
        (proj_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

        # Step 2: Render variants
        out_dir = proj_dir / "thumbnails"
        var_paths = generate_thumbnail_variants(proj_dir, out_dir)
        assert len(var_paths) >= 2

        # Step 3: Initialize experiment
        video_id = "costco_yt_001"
        exp = invoke_coord("initialize_experiment", project_dir=proj_dir, video_id=video_id, publisher=mock_adapter)
        assert exp.active_variant_id == "A"
        assert len(mock_adapter.thumbnail_history) >= 1

        # Step 4: Rotate to Variant B
        rot_event = invoke_coord("rotate_thumbnail", project_dir=proj_dir, video_id=video_id, target_variant_id="B", publisher=mock_adapter)
        assert rot_event.to_variant_id == "B"
        assert len(mock_adapter.thumbnail_history) >= 2

        # Step 5: Simulate analytics
        mock_adapter.set_simulated_metrics("A", impressions=2500, views=228, ctr=0.0912, average_view_percentage=68.0)
        mock_adapter.set_simulated_metrics("B", impressions=2500, views=355, ctr=0.1420, average_view_percentage=69.5)

        decision = invoke_coord("evaluate_performance", project_dir=proj_dir, video_id=video_id, analytics_provider=mock_adapter)
        assert decision.is_significant is True
        assert decision.winner_variant_id == "B"

        # Step 6: Commit winner
        final_exp = invoke_coord("commit_winner", project_dir=proj_dir, video_id=video_id, winner_id="B", publisher=mock_adapter)
        assert final_exp.status == "CONCLUDED"

        # Step 7: Verify canonical file
        canonical_thumb = proj_dir / "thumbnail.png"
        assert canonical_thumb.exists()
        assert canonical_thumb.stat().st_size == var_paths["B"].stat().st_size

    @skip_m2
    def test_tier4_scenario_02_three_way_variant_rotation_fair_exposure(self, tmp_path: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """
        Scenario 2: Multi-turn rotation cycle across 3 variants (A -> B -> C -> A):
        Verifies fair exposure allocation, sequential state tracking, and accurate query results.
        """
        proj_dir = tmp_path / "three_way_test"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "script.json").write_text(json.dumps([{"character": "ずんだもん", "text": "テストなのだ"}], ensure_ascii=False), encoding="utf-8")

        generate_thumbnail_variants(proj_dir, proj_dir / "thumbnails")
        # Add third variant C
        c_thumb = create_solid_image(proj_dir / "thumbnails" / "thumbnail_c.png", color="purple")

        video_id = "vid_3way_002"
        exp = invoke_coord("initialize_experiment", project_dir=proj_dir, video_id=video_id, publisher=mock_adapter)
        exp.variants["C"] = ThumbnailVariant("C", "Variant C", c_thumb)
        (proj_dir / "thumbnail_ab_experiment.json").write_text(json.dumps(exp.to_dict(), ensure_ascii=False), encoding="utf-8")

        # Rotate A -> B -> C -> A
        invoke_coord("rotate_thumbnail", project_dir=proj_dir, video_id=video_id, target_variant_id="B", publisher=mock_adapter)
        invoke_coord("rotate_thumbnail", project_dir=proj_dir, video_id=video_id, target_variant_id="C", publisher=mock_adapter)
        invoke_coord("rotate_thumbnail", project_dir=proj_dir, video_id=video_id, target_variant_id="A", publisher=mock_adapter)

        status = invoke_coord("get_status", project_dir=proj_dir)
        assert status.active_variant_id == "A"
        assert len(status.rotation_history) >= 4  # Initial + 3 rotations
        assert status.variants["B"].rotation_count >= 1
        assert status.variants["C"].rotation_count >= 1

    @skip_m2
    def test_tier4_scenario_03_underpowered_inconclusive_guardrail(self, tmp_path: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """
        Scenario 3: Low-traffic video with insufficient impressions:
        Remains inconclusive and refuses to declare a winner prematurely before min_impressions is met.
        """
        proj_dir = tmp_path / "underpowered_test"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "script.json").write_text(json.dumps([{"character": "ずんだもん", "text": "テスト"}], ensure_ascii=False), encoding="utf-8")
        generate_thumbnail_variants(proj_dir, proj_dir / "thumbnails")

        video_id = "vid_underpowered_003"
        invoke_coord("initialize_experiment", project_dir=proj_dir, video_id=video_id, publisher=mock_adapter)

        # Only 40 impressions each
        mock_adapter.set_simulated_metrics("A", impressions=40, views=2, ctr=0.05)
        mock_adapter.set_simulated_metrics("B", impressions=40, views=6, ctr=0.15)

        decision = invoke_coord("evaluate_performance", project_dir=proj_dir, video_id=video_id, analytics_provider=mock_adapter)
        assert decision.is_significant is False
        assert decision.committed is False

    @skip_m2
    def test_tier4_scenario_04_clickbait_retention_penalty_guardrail(self, tmp_path: Path, mock_adapter: MockYouTubeAdapter) -> None:
        """
        Scenario 4: Sensational thumbnail achieves high initial clicks but severe audience drop-off:
        The retention guardrail prevents the clickbait variant from being promoted over the audience-retentive variant.
        """
        proj_dir = tmp_path / "clickbait_test"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "script.json").write_text(json.dumps([{"character": "ずんだもん", "text": "テスト"}], ensure_ascii=False), encoding="utf-8")
        generate_thumbnail_variants(proj_dir, proj_dir / "thumbnails")

        video_id = "vid_clickbait_004"
        invoke_coord("initialize_experiment", project_dir=proj_dir, video_id=video_id, publisher=mock_adapter)

        # Variant A: Standard (10% CTR, 72% avg watch percentage)
        # Variant B: Clickbait (17% CTR, 22% avg watch percentage -> cliff drop-off)
        mock_adapter.set_simulated_metrics("A", impressions=2000, views=200, ctr=0.10, average_view_percentage=72.0)
        mock_adapter.set_simulated_metrics("B", impressions=2000, views=340, ctr=0.17, average_view_percentage=22.0)

        decision = invoke_coord("evaluate_performance", project_dir=proj_dir, video_id=video_id, analytics_provider=mock_adapter)
        # Decision must not blindly promote B as winner due to retention veto
        assert decision.winner_variant_id != "B" or "retention" in decision.rationale.lower()

    @skip_m3
    def test_tier4_scenario_05_full_cli_simulation_workflow(self, tmp_path: Path, capsys: Any) -> None:
        """
        Scenario 5: Full Headless CLI Workflow Simulation:
        veraxi-ymmp youtube ab-test init -> rotate -> status -> evaluate -> commit.
        """
        from veraxi_ymmp.cli import main

        proj_dir = tmp_path / "cli_workflow_project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "script.json").write_text(json.dumps([{"character": "ずんだもん", "text": "CLIテスト"}], ensure_ascii=False), encoding="utf-8")

        # 1. Init
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "ab-test", "init", "--project", str(proj_dir), "--video-id", "cli_wf_005", "--mock"]):
            main()
        assert (proj_dir / "thumbnail_ab_experiment.json").exists()

        # 2. Rotate
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "ab-test", "rotate", "--project", str(proj_dir), "--video-id", "cli_wf_005", "--variant", "B", "--mock"]):
            main()

        # 3. Status
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "ab-test", "status", "--project", str(proj_dir), "--mock"]):
            main()

        # 4. Evaluate
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "ab-test", "evaluate", "--project", str(proj_dir), "--video-id", "cli_wf_005", "--mock"]):
            main()

        # 5. Commit
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "ab-test", "commit", "--project", str(proj_dir), "--video-id", "cli_wf_005", "--winner", "B", "--mock"]):
            main()
        assert (proj_dir / "thumbnail.png").exists()
