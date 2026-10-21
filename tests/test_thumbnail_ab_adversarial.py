"""Empirical Adversarial Stress Suite for Milestone 2: ThumbnailABCoordinator.

Author: challenger_m2_1 (Empirical Challenger)
Focus:
1. Statistical edge cases & extreme sample sizes (0 to 10,000,000 impressions, identical CTRs, division by zero)
2. Confidence level thresholds and Z-test significance mathematical accuracy
3. Retention guardrail stress testing (sub-40% veto, >15% drop veto, exact boundary conditions)
4. State lifecycle & invalid transitions (concluded experiment lock, non-existent variant ID, round-robin cycles)
5. Atomicity, persistence resilience, corrupted state handling, Unicode/Emoji preservation
6. Comprehensive QA audit report outputs and canonical asset promotion
7. Dual invocation parity (class-level vs instance-level ThumbnailABCoordinator)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from veraxi_ymmp.ir import (
    ThumbnailVariant,
    VariantMetrics,
)
from veraxi_ymmp.thumbnail_ab import (
    ThumbnailABCoordinator,
    commit_winner,
    evaluate_performance,
    get_status,
    initialize_experiment,
    load_experiment,
    rotate_thumbnail,
    save_experiment,
)
from veraxi_ymmp.youtube_adapter import MockYouTubeAdapter


def _create_mock_png(path: Path, content: bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy") -> Path:
    """Create a minimal mock thumbnail image file for fast unit tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _create_standard_variants(
    proj_dir: Path,
    variants_spec: List[tuple[str, int, int, float, float]],
) -> List[ThumbnailVariant]:
    """Helper to quickly build ThumbnailVariants: (variant_id, imp, views, avg_ret, score)."""
    variants = []
    for vid, imp, views, ret, score in variants_spec:
        thumb_path = proj_dir / "thumbnails" / f"thumb_{vid.lower()}.png"
        _create_mock_png(thumb_path, f"data_for_{vid}".encode("utf-8"))
        ctr = views / imp if imp > 0 else 0.0
        v = ThumbnailVariant(
            variant_id=vid,
            name=f"Variant {vid}",
            thumbnail_path=thumb_path,
            config={"theme": "gold", "badge": f"Badge_{vid}"},
            metrics=VariantMetrics(
                variant_id=vid,
                impressions=imp,
                views=views,
                ctr=ctr,
                average_view_percentage=ret,
                average_view_duration_sec=ret * 1.5,
                retention_score=score,
            ),
            is_active=False,
            rotation_count=0,
        )
        variants.append(v)
    return variants


# ==============================================================================
# 1. Statistical Edge Cases & Two-Proportion Pooled Z-Test
# ==============================================================================

class TestStatisticalEdgeCases:
    """Empirically stress-test statistical calculations, edge cases, and bounds."""

    def test_identical_ctrs_across_variants(self, tmp_path: Path) -> None:
        """When variants have identical CTR, decision must be inconclusive with p_value=1.0."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 120, 65.0, 0.65),  # CTR = 12.0%
                ("B", 1000, 120, 65.0, 0.65),  # CTR = 12.0%
            ],
        )
        initialize_experiment(tmp_path, "vid_identical", variants=variants)
        decision = evaluate_performance(tmp_path, "vid_identical")

        assert decision.winner_variant_id is None
        assert decision.is_significant is False
        assert decision.winning_score == pytest.approx(0.12, abs=1e-5)
        assert decision.margin == 0.0
        assert decision.p_value == 1.0
        assert "Identical CTR" in decision.rationale

    def test_zero_impressions_and_zero_views(self, tmp_path: Path) -> None:
        """Verify zero impressions with min_impressions=0 does not divide by zero."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 0, 0, 0.0, 0.0),
                ("B", 0, 0, 0.0, 0.0),
            ],
        )
        initialize_experiment(tmp_path, "vid_zeros", variants=variants)
        # Calling evaluate with min_impressions=0 to bypass sample size guardrail
        decision = evaluate_performance(tmp_path, "vid_zeros", min_impressions=0)

        assert decision.winner_variant_id is None
        assert decision.is_significant is False
        assert decision.p_value == 1.0
        assert decision.winning_score == 0.0

    def test_extreme_sample_sizes_no_overflow(self, tmp_path: Path) -> None:
        """Verify 10,000,000 impressions evaluate accurately without float overflow."""
        # Variant A: 12.00% CTR on 10,000,000 impressions
        # Variant B: 12.05% CTR on 10,000,000 impressions (tiny 0.05% margin, but highly significant at N=20M)
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 10_000_000, 1_200_000, 60.0, 0.60),
                ("B", 10_000_000, 1_205_000, 60.0, 0.60),
            ],
        )
        initialize_experiment(tmp_path, "vid_extreme", variants=variants)
        decision = evaluate_performance(tmp_path, "vid_extreme")

        assert decision.winner_variant_id == "B"
        assert decision.is_significant is True
        assert decision.winning_score == pytest.approx(0.1205, abs=1e-5)
        assert decision.margin == pytest.approx(0.0005, abs=1e-5)
        assert decision.p_value is not None
        assert decision.p_value < 0.001
        assert "Statistically significant" in decision.rationale

    def test_sample_size_per_variant_guardrail(self, tmp_path: Path) -> None:
        """Total impressions meet threshold, but one variant is under-sampled."""
        # min_impressions default is 500. Threshold per variant with 2 variants is 500 // 2 = 250.
        # Variant A has 800 impressions (well above 250), but Variant B has only 200 (< 250).
        # Total is 1000 >= 500, but Variant B triggers the per-variant guardrail.
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 800, 120, 60.0, 0.60),
                ("B", 200, 40, 60.0, 0.60),
            ],
        )
        initialize_experiment(tmp_path, "vid_unbalanced", variants=variants, min_impressions=500)
        decision = evaluate_performance(tmp_path, "vid_unbalanced")

        assert decision.winner_variant_id is None
        assert decision.is_significant is False
        assert "INCONCLUSIVE_INSUFFICIENT_DATA" in decision.rationale
        assert "Impressions below threshold" in decision.rationale

    def test_confidence_level_threshold_sensitivity(self, tmp_path: Path) -> None:
        """Verify confidence_level=0.99 rejects differences accepted at confidence_level=0.95."""
        # Construct scenario where p-value is ~0.03 (significant at alpha=0.05, not at alpha=0.01)
        # N1 = 1000, V1 = 100 (CTR = 10.0%)
        # N2 = 1000, V2 = 135 (CTR = 13.5%)
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 100, 60.0, 0.60),
                ("B", 1000, 135, 60.0, 0.60),
            ],
        )
        initialize_experiment(tmp_path, "vid_conf", variants=variants)

        # At 95% confidence level
        decision_95 = evaluate_performance(tmp_path, "vid_conf", confidence_level=0.95)
        assert decision_95.is_significant is True
        assert decision_95.winner_variant_id == "B"

        # At 99% confidence level (alpha = 0.01)
        decision_99 = evaluate_performance(tmp_path, "vid_conf", confidence_level=0.99)
        assert decision_99.is_significant is False
        assert decision_99.winner_variant_id == "B"
        assert "Difference not statistically significant" in decision_99.rationale

    def test_fewer_than_two_variants_inconclusive(self, tmp_path: Path) -> None:
        """Single-variant experiment returns inconclusive decision without throwing error."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 150, 60.0, 0.60),
            ],
        )
        initialize_experiment(tmp_path, "vid_single", variants=variants)
        decision = evaluate_performance(tmp_path, "vid_single")

        assert decision.is_significant is False
        assert "requires at least two variants" in decision.rationale


# ==============================================================================
# 2. Audience Retention Guardrail Adversarial Challenges
# ==============================================================================

class TestRetentionGuardrailStress:
    """Stress-test the retention penalty preventing clickbait winners."""

    def test_sub_40_percent_retention_veto(self, tmp_path: Path) -> None:
        """High CTR candidate with 39.9% retention must be vetoed and overridden."""
        # Variant A: CTR = 20.0%, Retention = 39.9% (fails absolute 40% floor)
        # Variant B: CTR = 10.0%, Retention = 50.0%
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 200, 39.9, 0.399),
                ("B", 1000, 100, 50.0, 0.50),
            ],
        )
        initialize_experiment(tmp_path, "vid_sub40", variants=variants)
        decision = evaluate_performance(tmp_path, "vid_sub40")

        assert decision.winner_variant_id == "B"
        assert decision.is_significant is False
        assert decision.winning_score == pytest.approx(0.10, abs=1e-5)
        assert "Retention guardrail veto" in decision.rationale
        assert "failed audience retention check" in decision.rationale
        assert "Overriding winner to retentive variant B" in decision.rationale

    def test_excessive_retention_drop_veto(self, tmp_path: Path) -> None:
        """High CTR candidate with retention >15% below alternative must be vetoed."""
        # Variant A: CTR = 18.0%, Retention = 42.0% (passes 40% floor)
        # Variant B: CTR = 10.0%, Retention = 58.0% (diff = 16.0% > 15.0%)
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 180, 42.0, 0.42),
                ("B", 1000, 100, 58.0, 0.58),
            ],
        )
        initialize_experiment(tmp_path, "vid_drop16", variants=variants)
        decision = evaluate_performance(tmp_path, "vid_drop16")

        assert decision.winner_variant_id == "B"
        assert decision.is_significant is False
        assert "Retention guardrail veto" in decision.rationale
        assert "Overriding winner to retentive variant B" in decision.rationale

    def test_exact_retention_boundary_conditions(self, tmp_path: Path) -> None:
        """Exact 40.0% retention and exact 15.0% drop boundary must NOT be vetoed."""
        # Variant A: CTR = 16.0%, Retention = 40.0% (exact 40% floor)
        # Variant B: CTR = 10.0%, Retention = 55.0% (diff = 55.0 - 40.0 = 15.0% exact)
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 160, 40.0, 0.40),
                ("B", 1000, 100, 55.0, 0.55),
            ],
        )
        initialize_experiment(tmp_path, "vid_boundary", variants=variants)
        decision = evaluate_performance(tmp_path, "vid_boundary")

        # Variant A is NOT vetoed because cand_ret is not < 40 and drop is not > 15
        assert decision.winner_variant_id == "A"
        assert decision.winning_score == pytest.approx(0.16, abs=1e-5)
        assert decision.is_significant is True
        assert "Statistically significant" in decision.rationale

    def test_both_variants_low_retention_deterministic_override(self, tmp_path: Path) -> None:
        """When both variants are sub-40%, cand_ret < 40 triggers deterministic override to alt."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 150, 35.0, 0.35),
                ("B", 1000, 100, 25.0, 0.25),
            ],
        )
        initialize_experiment(tmp_path, "vid_both_sub40", variants=variants)
        decision = evaluate_performance(tmp_path, "vid_both_sub40")

        # Guardrail veto triggers on A and overrides to B
        assert decision.winner_variant_id == "B"
        assert decision.is_significant is False
        assert "Retention guardrail veto" in decision.rationale


# ==============================================================================
# 3. Experiment State Lifecycle & Invalid Transitions
# ==============================================================================

class TestStateLifecycleAndInvalidTransitions:
    """Stress-test experiment state transitions and verify defensive error handling."""

    def test_rotation_blocked_on_concluded_experiment(self, tmp_path: Path) -> None:
        """Cannot rotate thumbnails once experiment status is CONCLUDED."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 150, 60.0, 0.60),
                ("B", 1000, 100, 60.0, 0.60),
            ],
        )
        initialize_experiment(tmp_path, "vid_conclude_test", variants=variants)
        commit_winner(tmp_path, "vid_conclude_test", winner_id="A")

        # Verify status is CONCLUDED
        status = get_status(tmp_path)
        assert status.status == "CONCLUDED"

        # Attempting rotation must raise RuntimeError
        with pytest.raises(RuntimeError, match="Cannot rotate thumbnail on a CONCLUDED experiment"):
            rotate_thumbnail(tmp_path, "vid_conclude_test", target_variant_id="B")

    def test_rotation_rejects_non_existent_variant(self, tmp_path: Path) -> None:
        """Rotating to a variant not in experiment must raise KeyError."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 100, 60.0, 0.60),
                ("B", 1000, 100, 60.0, 0.60),
            ],
        )
        initialize_experiment(tmp_path, "vid_key_err", variants=variants)

        with pytest.raises(KeyError, match="Target variant 'NON_EXISTENT_VAR' does not exist"):
            rotate_thumbnail(tmp_path, "vid_key_err", target_variant_id="NON_EXISTENT_VAR")

    def test_commit_winner_rejects_non_existent_variant(self, tmp_path: Path) -> None:
        """Committing a variant not in experiment must raise KeyError."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 100, 60.0, 0.60),
                ("B", 1000, 100, 60.0, 0.60),
            ],
        )
        initialize_experiment(tmp_path, "vid_commit_err", variants=variants)

        with pytest.raises(KeyError, match="Winning variant 'GHOST_VAR' does not exist"):
            commit_winner(tmp_path, "vid_commit_err", winner_id="GHOST_VAR")

    def test_round_robin_three_variant_full_cycle(self, tmp_path: Path) -> None:
        """Round-robin rotation cycles cleanly through A -> B -> C -> A with rotation counts."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 100, 60.0, 0.60),
                ("B", 1000, 100, 60.0, 0.60),
                ("C", 1000, 100, 60.0, 0.60),
            ],
        )
        adapter = MockYouTubeAdapter()
        exp = initialize_experiment(tmp_path, "vid_cycle3", variants=variants, publisher=adapter)
        assert exp.active_variant_id == "A"
        assert len(exp.rotation_history) == 1

        # Rotate 1: A -> B
        ev1 = rotate_thumbnail(tmp_path, "vid_cycle3", publisher=adapter)
        assert ev1.to_variant_id == "B"
        assert get_status(tmp_path).active_variant_id == "B"
        assert get_status(tmp_path).variants["B"].rotation_count == 1

        # Rotate 2: B -> C
        ev2 = rotate_thumbnail(tmp_path, "vid_cycle3", publisher=adapter)
        assert ev2.to_variant_id == "C"
        assert get_status(tmp_path).active_variant_id == "C"
        assert get_status(tmp_path).variants["C"].rotation_count == 1

        # Rotate 3: C -> A
        ev3 = rotate_thumbnail(tmp_path, "vid_cycle3", publisher=adapter)
        assert ev3.to_variant_id == "A"
        assert get_status(tmp_path).active_variant_id == "A"
        assert get_status(tmp_path).variants["A"].rotation_count == 1

        # Rotate 4: A -> B
        ev4 = rotate_thumbnail(tmp_path, "vid_cycle3", publisher=adapter)
        assert ev4.to_variant_id == "B"
        assert get_status(tmp_path).variants["B"].rotation_count == 2

        # 1 init + 4 rotations = 5 history entries
        status = get_status(tmp_path)
        assert len(status.rotation_history) == 5

    def test_reinitialization_preserves_audit_history(self, tmp_path: Path) -> None:
        """Re-initializing same project/video preserves prior rotation events."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 100, 60.0, 0.60),
                ("B", 1000, 100, 60.0, 0.60),
            ],
        )
        initialize_experiment(tmp_path, "vid_audit", variants=variants)
        rotate_thumbnail(tmp_path, "vid_audit", target_variant_id="B")
        rotate_thumbnail(tmp_path, "vid_audit", target_variant_id="A")

        # Now re-initialize
        re_exp = initialize_experiment(tmp_path, "vid_audit", variants=variants)
        # Previous history (3 events: init, B, A) + new initial activation = 4 events
        assert len(re_exp.rotation_history) == 4
        assert re_exp.rotation_history[-1].reason == "initial_activation"


# ==============================================================================
# 4. Persistence, Atomicity & Report Generation
# ==============================================================================

class TestPersistenceAndReportGeneration:
    """Stress-test atomic JSON persistence, corrupt state handling, and report output generation."""

    def test_atomic_save_leaves_no_lingering_temp_files(self, tmp_path: Path) -> None:
        """Verify save_experiment writes cleanly and atomic temp file is removed."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 100, 60.0, 0.60),
                ("B", 1000, 100, 60.0, 0.60),
            ],
        )
        exp = initialize_experiment(tmp_path, "vid_atomic", variants=variants)
        state_file = tmp_path / "thumbnail_ab_experiment.json"
        temp_file = tmp_path / ".tmp_thumbnail_ab_experiment.json"

        assert state_file.exists()
        assert not temp_file.exists()

        # Re-save multiple times
        for _ in range(5):
            save_experiment(exp)
            assert state_file.exists()
            assert not temp_file.exists()

    def test_corrupt_state_file_error_handling(self, tmp_path: Path) -> None:
        """load_experiment raises descriptive errors on corrupted or incomplete state files."""
        state_file = tmp_path / "thumbnail_ab_experiment.json"

        # Case 1: File not found
        with pytest.raises(FileNotFoundError):
            load_experiment(tmp_path / "non_existent_folder")

        # Case 2: Malformed JSON syntax
        state_file.write_text("{invalid json truncated", encoding="utf-8")
        with pytest.raises(ValueError):
            load_experiment(tmp_path)

        # Case 3: JSON array instead of object
        state_file.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="expected object"):
            load_experiment(tmp_path)

        # Case 4: Missing required 'variants' key
        state_file.write_text(json.dumps({"experiment_id": "exp_1"}), encoding="utf-8")
        with pytest.raises(KeyError, match="Missing required 'variants' field"):
            load_experiment(tmp_path)

    def test_unicode_and_emoji_metadata_preservation(self, tmp_path: Path) -> None:
        """Japanese text, symbols, and emojis roundtrip cleanly without corruption."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 100, 60.0, 0.60),
                ("B", 1000, 100, 60.0, 0.60),
            ],
        )
        variants[0].name = "バリアントA【最強フック】🔥🚀"
        variants[0].config = {"theme": "深層ゴールド", "tag": "超絶クリック率向上！"}

        initialize_experiment(tmp_path, "vid_unicode", variants=variants)
        loaded = load_experiment(tmp_path)

        assert loaded.variants["A"].name == "バリアントA【最強フック】🔥🚀"
        assert loaded.variants["A"].config["theme"] == "深層ゴールド"
        assert loaded.variants["A"].config["tag"] == "超絶クリック率向上！"

    def test_commit_winner_generates_all_six_reports_and_promotes_thumbnail(self, tmp_path: Path) -> None:
        """commit_winner writes all 6 Markdown/JSON reports and copies canonical thumbnail."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 150, 65.0, 0.65),
                ("B", 1000, 100, 65.0, 0.65),
            ],
        )
        # Create thumbnail_config.json to verify config sync
        cfg_file = tmp_path / "thumbnail_config.json"
        cfg_file.write_text(json.dumps({"theme": "blue", "badge": "OldBadge", "default": {}}), encoding="utf-8")

        adapter = MockYouTubeAdapter()
        initialize_experiment(tmp_path, "vid_reports", variants=variants, publisher=adapter)
        evaluate_performance(tmp_path, "vid_reports")
        commit_winner(tmp_path, "vid_reports", winner_id="A", publisher=adapter)

        # 1. Verify 6 report files exist and are non-empty
        expected_reports = [
            tmp_path / "ab_test_report.md",
            tmp_path / "ab_test_report.json",
            tmp_path / "qa_reports" / "ab_test_report.md",
            tmp_path / "qa_reports" / "ab_test_report.json",
            tmp_path / "qa_reports" / "thumbnail_ab_winner_report.md",
            tmp_path / "qa_reports" / "thumbnail_ab_winner_report.json",
        ]
        for rep in expected_reports:
            assert rep.exists(), f"Missing report file: {rep}"
            assert len(rep.read_text(encoding="utf-8").strip()) > 0, f"Empty report file: {rep}"

        # 2. Verify canonical thumbnail.png was promoted
        canonical_thumb = tmp_path / "thumbnail.png"
        assert canonical_thumb.exists()
        assert canonical_thumb.read_bytes() == variants[0].thumbnail_path.read_bytes()

        # 3. Verify thumbnail_config.json was updated with winner config
        updated_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert updated_cfg.get("badge") == "Badge_A"

        # 4. Verify publisher history
        assert len(adapter.thumbnail_history) == 2  # 1 on init, 1 on commit


# ==============================================================================
# 5. Dual Invocation Parity (Class vs Instance Methods)
# ==============================================================================

class TestDualInvocationParity:
    """Verify class-level and instance-level coordinator methods behave identically."""

    def test_class_and_instance_coordinator_parity(self, tmp_path: Path) -> None:
        """Every coordinator method can be invoked via ThumbnailABCoordinator or instance."""
        variants = _create_standard_variants(
            tmp_path,
            [
                ("A", 1000, 140, 60.0, 0.60),
                ("B", 1000, 100, 60.0, 0.60),
            ],
        )
        adapter = MockYouTubeAdapter()
        coord = ThumbnailABCoordinator(publisher=adapter, analytics_provider=adapter)

        # Test class method
        exp = ThumbnailABCoordinator.initialize_experiment(
            tmp_path, "vid_dual", variants=variants, publisher=adapter
        )
        assert exp.active_variant_id == "A"

        # Test instance method
        ev = coord.rotate_thumbnail(tmp_path, "vid_dual", target_variant_id="B")
        assert ev.to_variant_id == "B"

        # Test class evaluate
        dec = ThumbnailABCoordinator.evaluate_performance(tmp_path, "vid_dual")
        assert dec.winner_variant_id == "A"

        # Test instance commit
        status = coord.commit_winner(tmp_path, "vid_dual", winner_id="A")
        assert status.status == "CONCLUDED"

        # Test class get_status
        loaded = ThumbnailABCoordinator.get_status(tmp_path)
        assert loaded.status == "CONCLUDED"
        assert loaded.winner_decision.committed is True

        # Test report rendering
        md = coord.render_ab_report(loaded)
        assert "# YouTube Thumbnail A/B Test Audit Report" in md
