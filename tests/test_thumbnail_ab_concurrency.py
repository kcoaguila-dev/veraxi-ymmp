"""Adversarial Empirical Stress Suite for YouTube Thumbnail A/B Coordinator (Milestone 2).

Author: challenger_m2_2 (Empirical Challenger)
Focus:
- Multi-variant round-robin rotation cycles across 3, 4, and 5 variants (sequential progression, is_active mutual exclusivity)
- Non-standard variant keys and single-variant boundary cases
- Winner commitment resilience: missing files, nonexistent directories, corrupted/partial/empty thumbnail_config.json
- Concurrent multi-thread rotation, atomic persistence, and race-condition safety
- Comprehensive QA audit reporting: dual-format (MD + JSON), JSON schema integrity, and dual-location parity
- Statistical edge cases: division-by-zero, boundary CTRs, and clickbait retention guardrail overrides
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import List, Optional

import pytest

from veraxi_ymmp.ir import (
    ThumbnailVariant,
    VariantMetrics,
)
from veraxi_ymmp.thumbnail_ab import (
    ThumbnailABCoordinator,
    load_experiment,
    save_experiment,
)
from veraxi_ymmp.youtube_adapter import MockYouTubeAdapter


def _create_mock_variant(
    project_dir: Path,
    variant_id: str,
    name: Optional[str] = None,
    is_active: bool = False,
    impressions: int = 1000,
    views: int = 100,
    ctr: Optional[float] = None,
    retention: float = 60.0,
    create_file: bool = True,
) -> ThumbnailVariant:
    """Helper to generate a ThumbnailVariant with a valid dummy PNG file."""
    thumbs_dir = project_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumbs_dir / f"thumb_{variant_id.lower()}.png"
    if create_file:
        thumb_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    calculated_ctr = ctr if ctr is not None else (views / impressions if impressions > 0 else 0.0)
    metrics = VariantMetrics(
        variant_id=variant_id,
        impressions=impressions,
        views=views,
        ctr=calculated_ctr,
        average_view_percentage=retention,
        average_view_duration_sec=120.0,
        retention_score=retention / 100.0,
    )
    return ThumbnailVariant(
        variant_id=variant_id,
        name=name or f"Variant {variant_id}",
        thumbnail_path=thumb_path,
        config={"theme": f"theme_{variant_id}", "badge": f"badge_{variant_id}"},
        metrics=metrics,
        is_active=is_active,
        rotation_count=0,
    )


# ==============================================================================
# 1. Multi-Variant Round-Robin Rotation Cycles (3, 4, 5 Variants)
# ==============================================================================

class TestMultiVariantRotationCycles:
    """Stress-test sequential round-robin rotation cycles across 3, 4, and 5 variants."""

    @pytest.mark.parametrize("variant_count", [3, 4, 5])
    def test_round_robin_cycles_sequential_and_mutual_exclusion(
        self, tmp_path: Path, variant_count: int
    ) -> None:
        """Verify sequential progression and strict mutual exclusivity of is_active flags across N cycles."""
        proj = tmp_path / f"proj_cycle_{variant_count}"
        proj.mkdir()
        video_id = f"video_rr_{variant_count}"

        var_keys = [chr(ord("A") + i) for i in range(variant_count)]
        variants = [_create_mock_variant(proj, vid, is_active=(vid == "A")) for vid in var_keys]

        mock_pub = MockYouTubeAdapter()
        coordinator = ThumbnailABCoordinator(publisher=mock_pub)
        exp = coordinator.initialize_experiment(
            project_dir=proj,
            video_id=video_id,
            variants=variants,
        )

        assert exp.active_variant_id == "A"
        active_flags = [v.is_active for v in exp.variants.values()]
        assert active_flags.count(True) == 1
        assert exp.variants["A"].is_active is True

        # Perform 3 full round-robin cycles (e.g. 3 * 3 = 9, 3 * 5 = 15 rotations)
        num_rotations = variant_count * 3
        expected_sequence = [var_keys[(i + 1) % variant_count] for i in range(num_rotations)]

        for step, expected_vid in enumerate(expected_sequence):
            event = coordinator.rotate_thumbnail(project_dir=proj, video_id=video_id)
            assert event.to_variant_id == expected_vid, (
                f"Step {step}: Expected rotation to {expected_vid}, got {event.to_variant_id}"
            )

            # Reload directly from disk to verify atomic persistence
            disk_exp = coordinator.get_status(proj)
            assert disk_exp.active_variant_id == expected_vid

            # Strict mutual exclusivity check: exactly one is_active == True
            is_active_map = {vid: disk_exp.variants[vid].is_active for vid in var_keys}
            true_counts = list(is_active_map.values()).count(True)
            assert true_counts == 1, (
                f"Step {step}: Expected exactly 1 active variant, found {true_counts}: {is_active_map}"
            )
            assert disk_exp.variants[expected_vid].is_active is True

            # Rotation counts check
            expected_rotations = (step // variant_count) + 1
            assert disk_exp.variants[expected_vid].rotation_count == expected_rotations

        # Check total rotation history on disk
        final_exp = coordinator.get_status(proj)
        # 1 initial activation event + num_rotations
        assert len(final_exp.rotation_history) == num_rotations + 1
        assert final_exp.rotation_history[0].reason == "initial_activation"
        assert all(ev.reason == "scheduled_rotation" for ev in final_exp.rotation_history[1:])

    def test_rotation_with_custom_lexicographical_keys(self, tmp_path: Path) -> None:
        """Verify round-robin behaves deterministically with arbitrary string keys."""
        proj = tmp_path / "proj_custom_keys"
        proj.mkdir()
        video_id = "v_custom_keys"

        custom_keys = ["delta_04", "alpha_01", "gamma_03", "beta_02"]
        variants = [_create_mock_variant(proj, vid) for vid in custom_keys]

        coordinator = ThumbnailABCoordinator()
        exp = coordinator.initialize_experiment(
            project_dir=proj,
            video_id=video_id,
            variants=variants,
        )

        # Lexicographically sorted: alpha_01, beta_02, delta_04, gamma_03
        sorted_keys = sorted(custom_keys)
        # Since 'A' is not in keys, default active is first key in variants dict
        initial_active = exp.active_variant_id
        assert initial_active in sorted_keys

        # Rotate through all keys
        curr_idx = sorted_keys.index(initial_active)
        for i in range(len(sorted_keys) * 2):
            next_expected = sorted_keys[(curr_idx + 1) % len(sorted_keys)]
            ev = coordinator.rotate_thumbnail(project_dir=proj, video_id=video_id)
            assert ev.to_variant_id == next_expected
            curr_idx = (curr_idx + 1) % len(sorted_keys)

    def test_single_variant_rotation_boundary(self, tmp_path: Path) -> None:
        """Verify boundary condition when experiment contains only 1 variant."""
        proj = tmp_path / "proj_single"
        proj.mkdir()
        video_id = "v_single"
        variants = [_create_mock_variant(proj, "ONLY_ONE")]

        coordinator = ThumbnailABCoordinator()
        exp = coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=variants)
        assert exp.active_variant_id == "ONLY_ONE"

        # Round robin on 1 variant: keys[(0 + 1) % 1] == keys[0] == "ONLY_ONE"
        ev = coordinator.rotate_thumbnail(project_dir=proj, video_id=video_id)
        assert ev.from_variant_id == "ONLY_ONE"
        assert ev.to_variant_id == "ONLY_ONE"
        disk_exp = coordinator.get_status(proj)
        assert disk_exp.variants["ONLY_ONE"].rotation_count == 1
        assert disk_exp.variants["ONLY_ONE"].is_active is True

    def test_rotation_rejects_concluded_experiment(self, tmp_path: Path) -> None:
        """Verify RuntimeError is strictly raised if rotation is attempted on CONCLUDED experiment."""
        proj = tmp_path / "proj_concluded"
        proj.mkdir()
        video_id = "v_concluded"
        variants = [_create_mock_variant(proj, "A"), _create_mock_variant(proj, "B")]

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=variants)
        coordinator.commit_winner(project_dir=proj, video_id=video_id, winner_id="A")

        with pytest.raises(RuntimeError, match="Cannot rotate thumbnail on a CONCLUDED experiment"):
            coordinator.rotate_thumbnail(project_dir=proj, video_id=video_id)


# ==============================================================================
# 2. Winner Commitment Resilience & Edge Cases
# ==============================================================================

class TestWinnerCommitmentResilience:
    """Stress-test winner commitment under missing files, corrupt configs, and partial states."""

    def test_commit_winner_with_missing_thumbnail_file(self, tmp_path: Path) -> None:
        """Verify commit_winner gracefully concludes even if the thumbnail image file was deleted."""
        proj = tmp_path / "proj_missing_img"
        proj.mkdir()
        video_id = "v_missing_img"

        # create_file=False ensures thumbnail_path does NOT exist
        var_a = _create_mock_variant(proj, "A", create_file=False)
        var_b = _create_mock_variant(proj, "B", create_file=False)

        mock_pub = MockYouTubeAdapter()
        coordinator = ThumbnailABCoordinator(publisher=mock_pub)
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=[var_a, var_b])

        # Commit winner A
        concluded_exp = coordinator.commit_winner(project_dir=proj, video_id=video_id, winner_id="A")

        assert concluded_exp.status == "CONCLUDED"
        assert concluded_exp.active_variant_id == "A"
        assert concluded_exp.winner_decision is not None
        assert concluded_exp.winner_decision.committed is True
        assert concluded_exp.winner_decision.winner_variant_id == "A"

        # Should not have uploaded to publisher since file was missing
        assert len(mock_pub.thumbnail_history) == 0
        # Canonical thumbnail.png should not exist
        assert not (proj / "thumbnail.png").exists()

        # Audit reports must still be generated cleanly
        assert (proj / "ab_test_report.md").exists()
        assert (proj / "ab_test_report.json").exists()

    def test_commit_winner_nonexistent_directory(self, tmp_path: Path) -> None:
        """Verify commit_winner raises FileNotFoundError when given a nonexistent directory."""
        nonexistent = tmp_path / "ghost_directory"
        coordinator = ThumbnailABCoordinator()

        with pytest.raises(FileNotFoundError, match="Experiment state file not found"):
            coordinator.commit_winner(project_dir=nonexistent, video_id="ghost_vid")

    @pytest.mark.parametrize(
        "corrupt_config_content",
        [
            "",  # empty file
            "{not a valid json:",  # invalid json syntax
            "[]",  # array instead of dict
            '"plain string"',  # primitive string
            "42",  # primitive number
            '{"hook": "legacy"}',  # partial dict without default key
            '{"default": "not a dict"}',  # default is not a dict
        ],
    )
    def test_commit_winner_with_corrupted_or_partial_thumbnail_config(
        self, tmp_path: Path, corrupt_config_content: str
    ) -> None:
        """Verify commit_winner does NOT crash when thumbnail_config.json is corrupted or partial."""
        proj = tmp_path / f"proj_cfg_{abs(hash(corrupt_config_content))}"
        proj.mkdir()
        video_id = "v_cfg_stress"

        cfg_file = proj / "thumbnail_config.json"
        cfg_file.write_text(corrupt_config_content, encoding="utf-8")

        var_a = _create_mock_variant(proj, "A")
        var_b = _create_mock_variant(proj, "B")

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=[var_a, var_b])

        # commit_winner must complete without raising json.JSONDecodeError or TypeError
        concluded_exp = coordinator.commit_winner(project_dir=proj, video_id=video_id, winner_id="A")
        assert concluded_exp.status == "CONCLUDED"
        assert concluded_exp.active_variant_id == "A"
        assert (proj / "thumbnail.png").exists()

    def test_commit_winner_with_valid_and_nested_thumbnail_config(self, tmp_path: Path) -> None:
        """Verify winning variant parameters merge into existing thumbnail_config.json."""
        proj = tmp_path / "proj_cfg_valid"
        proj.mkdir()
        video_id = "v_cfg_valid"

        initial_config = {
            "title": "Existing Title",
            "default": {
                "theme": "old_theme",
                "badge": "old_badge",
                "keep_me": "intact",
            },
        }
        cfg_file = proj / "thumbnail_config.json"
        cfg_file.write_text(json.dumps(initial_config), encoding="utf-8-sig")

        var_a = _create_mock_variant(proj, "A")
        var_a.config = {"theme": "gold_winner", "badge": "NEW_BADGE"}
        var_b = _create_mock_variant(proj, "B")

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=[var_a, var_b])
        coordinator.commit_winner(project_dir=proj, video_id=video_id, winner_id="A")

        # Reload configuration
        updated_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert updated_cfg["theme"] == "gold_winner"
        assert updated_cfg["badge"] == "NEW_BADGE"
        assert updated_cfg["default"]["theme"] == "gold_winner"
        assert updated_cfg["default"]["badge"] == "NEW_BADGE"
        assert updated_cfg["default"]["keep_me"] == "intact"

    def test_commit_winner_fallback_when_winner_id_not_provided(self, tmp_path: Path) -> None:
        """Verify automatic winner fallback evaluation when winner_id is omitted."""
        proj = tmp_path / "proj_no_winner_id"
        proj.mkdir()
        video_id = "v_no_winner_id"

        # Var A has significantly higher CTR: 15% vs 5% (150 vs 50 views out of 1000)
        var_a = _create_mock_variant(proj, "A", impressions=1000, views=150, retention=65.0)
        var_b = _create_mock_variant(proj, "B", impressions=1000, views=50, retention=65.0)

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=[var_a, var_b])

        # Commit without winner_id
        concluded = coordinator.commit_winner(project_dir=proj, video_id=video_id)
        assert concluded.winner_decision is not None
        assert concluded.winner_decision.winner_variant_id == "A"
        assert concluded.winner_decision.is_significant is True
        assert concluded.active_variant_id == "A"


# ==============================================================================
# 3. Concurrent Multi-Thread Rotation and State Reload Safety
# ==============================================================================

class TestConcurrencyAndThreadSafety:
    """Stress-test concurrent readers, writers, and atomic state replacement under multi-threading."""

    def test_concurrent_state_readers_during_active_rotations(self, tmp_path: Path) -> None:
        """Verify that concurrent readers never encounter corrupted JSON or partially written files."""
        proj = tmp_path / "proj_concurrent_readers"
        proj.mkdir()
        video_id = "v_concurr_readers"

        variants = [_create_mock_variant(proj, "A"), _create_mock_variant(proj, "B"), _create_mock_variant(proj, "C")]
        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=variants)

        stop_event = threading.Event()
        read_errors: List[str] = []
        read_count = [0]

        def reader_worker() -> None:
            while not stop_event.is_set():
                try:
                    exp = load_experiment(proj)
                    assert exp.video_id == video_id
                    assert exp.active_variant_id in ["A", "B", "C"]
                    assert len(exp.variants) == 3
                    read_count[0] += 1
                except Exception as exc:
                    read_errors.append(f"Reader failed with: {exc}")
                time.sleep(0.001)

        # Launch 5 reader threads
        threads = [threading.Thread(target=reader_worker) for _ in range(5)]
        for t in threads:
            t.start()

        # Perform 25 rotations on main thread
        try:
            for step in range(25):
                coordinator.rotate_thumbnail(project_dir=proj, video_id=video_id)
                time.sleep(0.005)
        finally:
            stop_event.set()
            for t in threads:
                t.join(timeout=5.0)

        assert len(read_errors) == 0, f"Encountered read corruption during concurrent writes: {read_errors}"
        assert read_count[0] > 50, f"Expected substantial number of concurrent reads, got {read_count[0]}"

    def test_atomic_save_experiment_preserves_valid_json_on_disk(self, tmp_path: Path) -> None:
        """Verify atomic serialization never leaves incomplete json or unhandled temp files."""
        proj = tmp_path / "proj_atomic_save"
        proj.mkdir()
        video_id = "v_atomic"

        variants = [_create_mock_variant(proj, "A"), _create_mock_variant(proj, "B")]
        coordinator = ThumbnailABCoordinator()
        exp = coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=variants)

        # Overwrite experiment 50 times in rapid succession
        for i in range(50):
            exp.active_variant_id = "B" if i % 2 == 0 else "A"
            save_experiment(exp)

            target_file = proj / "thumbnail_ab_experiment.json"
            content = target_file.read_text(encoding="utf-8")
            parsed = json.loads(content)
            assert parsed["active_variant_id"] == exp.active_variant_id

        # Temp staging file should NOT linger after replace
        temp_file = proj / ".tmp_thumbnail_ab_experiment.json"
        assert not temp_file.exists()

    def test_concurrent_rotations_collision(self, tmp_path: Path) -> None:
        """Verify behavior when multiple threads simultaneously attempt to rotate thumbnails."""
        proj = tmp_path / "proj_concurrent_rotations"
        proj.mkdir()
        video_id = "v_concurr_rotations"

        variants = [_create_mock_variant(proj, "A"), _create_mock_variant(proj, "B"), _create_mock_variant(proj, "C")]
        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=variants)

        errors: List[Exception] = []

        def worker() -> None:
            try:
                coordinator.rotate_thumbnail(project_dir=proj, video_id=video_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check errors and final disk state
        assert len(errors) == 0, f"Concurrent rotation threads failed with: {errors}"
        disk_exp = coordinator.get_status(proj)
        assert disk_exp.video_id == video_id

    def test_concurrent_rotations_across_distinct_projects(self, tmp_path: Path) -> None:
        """Verify that concurrent rotations on distinct project directories succeed without interference."""
        num_projects = 8
        proj_dirs = [tmp_path / f"proj_distinct_{i}" for i in range(num_projects)]
        for p in proj_dirs:
            p.mkdir()

        coordinator = ThumbnailABCoordinator()
        for i, p in enumerate(proj_dirs):
            variants = [_create_mock_variant(p, "A"), _create_mock_variant(p, "B"), _create_mock_variant(p, "C")]
            coordinator.initialize_experiment(project_dir=p, video_id=f"v_distinct_{i}", variants=variants)

        errors: List[Exception] = []

        def worker(idx: int) -> None:
            try:
                p = proj_dirs[idx]
                coordinator.rotate_thumbnail(project_dir=p, video_id=f"v_distinct_{idx}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_projects)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Cross-project concurrent rotations failed: {errors}"
        for i, p in enumerate(proj_dirs):
            exp = coordinator.get_status(p)
            assert exp.active_variant_id == "B"


# ==============================================================================
# 4. QA Audit Reporting Consistency (Markdown & JSON)
# ==============================================================================

class TestAuditReportConsistency:
    """Stress-test consistency, formatting, and dual-location synchronization of QA reports."""

    def test_all_six_report_files_generated_and_parseable(self, tmp_path: Path) -> None:
        """Verify all 6 report files exist, are strictly formatted, and contain valid JSON."""
        proj = tmp_path / "proj_reports"
        proj.mkdir()
        video_id = "v_reports_test"

        var_a = _create_mock_variant(proj, "A", name="バリアントA【激推し】🔥", impressions=2000, views=240, retention=68.0)
        var_b = _create_mock_variant(proj, "B", name="バリアントB【疑問形】❓", impressions=2000, views=160, retention=62.0)

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=[var_a, var_b])
        coordinator.rotate_thumbnail(project_dir=proj, video_id=video_id)
        coordinator.evaluate_performance(project_dir=proj, video_id=video_id)
        concluded = coordinator.commit_winner(project_dir=proj, video_id=video_id, winner_id="A")

        expected_files = [
            proj / "ab_test_report.md",
            proj / "ab_test_report.json",
            proj / "qa_reports" / "ab_test_report.md",
            proj / "qa_reports" / "ab_test_report.json",
            proj / "qa_reports" / "thumbnail_ab_winner_report.md",
            proj / "qa_reports" / "thumbnail_ab_winner_report.json",
        ]

        for p in expected_files:
            assert p.exists(), f"Expected report file missing: {p}"
            assert p.stat().st_size > 0, f"Report file is empty: {p}"

            if p.suffix == ".json":
                data = json.loads(p.read_text(encoding="utf-8"))
                assert data["experiment_id"] == concluded.experiment_id
                assert data["video_id"] == video_id
                assert data["status"] == "CONCLUDED"
                assert data["active_variant_id"] == "A"
                assert data["winner_decision"]["winner_variant_id"] == "A"
                assert data["winner_decision"]["committed"] is True
                assert len(data["variants"]) == 2
                assert len(data["rotation_history"]) >= 2
            elif p.suffix == ".md":
                content = p.read_text(encoding="utf-8")
                # Scorecard checks
                assert "# YouTube Thumbnail A/B Test Audit Report" in content
                assert f"`{video_id}`" in content
                assert "## Winner Decision Scorecard" in content
                assert "- **Winner Variant**: **A**" in content
                assert "- **Winning Score (CTR)**: 12.00%" in content
                assert "- **Statistically Significant**: True" in content
                # Variant performance table checks
                assert "## Variant Performance Table" in content
                assert "| Variant ID | Name | Impressions | Views | CTR | Avg Watch % | Retention Score | Active | Rotations |" in content
                assert "バリアントA【激推し】🔥" in content
                assert "バリアントB【疑問形】❓" in content
                # Rotation history table checks
                assert "## Rotation History Log" in content
                assert "| Timestamp | From | To | Reason |" in content
                assert "initial_activation" in content
                assert "scheduled_rotation" in content

    def test_report_content_identical_across_locations(self, tmp_path: Path) -> None:
        """Verify root reports match qa_reports exactly."""
        proj = tmp_path / "proj_reports_parity"
        proj.mkdir()
        video_id = "v_parity"

        variants = [_create_mock_variant(proj, "A"), _create_mock_variant(proj, "B")]
        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=variants)
        coordinator.commit_winner(project_dir=proj, video_id=video_id, winner_id="A")

        md_root = (proj / "ab_test_report.md").read_text(encoding="utf-8")
        md_qa = (proj / "qa_reports" / "ab_test_report.md").read_text(encoding="utf-8")
        assert md_root == md_qa

        json_root = (proj / "ab_test_report.json").read_text(encoding="utf-8")
        json_qa = (proj / "qa_reports" / "ab_test_report.json").read_text(encoding="utf-8")
        assert json_root == json_qa


# ==============================================================================
# 5. Statistical & Retention Guardrail Stress Tests
# ==============================================================================

class TestStatisticalAndRetentionGuardrails:
    """Stress-test evaluation mathematical stability, sample size limits, and clickbait penalties."""

    def test_sample_size_guardrail_prevents_premature_decision(self, tmp_path: Path) -> None:
        """Verify that total impressions below min_impressions results in INCONCLUSIVE_INSUFFICIENT_DATA."""
        proj = tmp_path / "proj_low_sample"
        proj.mkdir()
        video_id = "v_low_sample"

        # Total impressions = 200 (default min_impressions = 500)
        var_a = _create_mock_variant(proj, "A", impressions=100, views=20)
        var_b = _create_mock_variant(proj, "B", impressions=100, views=5)

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(
            project_dir=proj, video_id=video_id, variants=[var_a, var_b], min_impressions=500
        )

        decision = coordinator.evaluate_performance(project_dir=proj, video_id=video_id)
        assert decision.is_significant is False
        assert decision.winner_variant_id is None
        assert "INCONCLUSIVE_INSUFFICIENT_DATA" in decision.rationale

    def test_identical_ctr_across_variants_returns_inconclusive(self, tmp_path: Path) -> None:
        """Verify identical CTR does not declare a spurious winner."""
        proj = tmp_path / "proj_identical_ctr"
        proj.mkdir()
        video_id = "v_identical_ctr"

        var_a = _create_mock_variant(proj, "A", impressions=1000, views=100)
        var_b = _create_mock_variant(proj, "B", impressions=1000, views=100)

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=[var_a, var_b])

        decision = coordinator.evaluate_performance(project_dir=proj, video_id=video_id)
        assert decision.is_significant is False
        assert decision.winner_variant_id is None
        assert "Identical CTR" in decision.rationale

    def test_clickbait_retention_penalty_under_40_percent(self, tmp_path: Path) -> None:
        """Verify candidate with higher CTR is vetoed if average_view_percentage < 40.0%."""
        proj = tmp_path / "proj_cb_40"
        proj.mkdir()
        video_id = "v_cb_40"

        # Var A: 14% CTR, but 35% retention (< 40%)
        # Var B: 8% CTR, but 65% retention
        var_a = _create_mock_variant(proj, "A", impressions=2000, views=280, retention=35.0)
        var_b = _create_mock_variant(proj, "B", impressions=2000, views=160, retention=65.0)

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=[var_a, var_b])

        decision = coordinator.evaluate_performance(project_dir=proj, video_id=video_id)
        # Winner must be overridden to B due to retention veto
        assert decision.winner_variant_id == "B"
        assert decision.is_significant is False
        assert "Retention guardrail veto" in decision.rationale
        assert "Variant A had higher CTR" in decision.rationale

    def test_clickbait_retention_penalty_drop_over_15_percent(self, tmp_path: Path) -> None:
        """Verify candidate with higher CTR is vetoed if retention drops by > 15% vs alternative."""
        proj = tmp_path / "proj_cb_diff"
        proj.mkdir()
        video_id = "v_cb_diff"

        # Var A: 12% CTR, 48% retention
        # Var B: 9% CTR, 65% retention (65 - 48 = 17% drop > 15%)
        var_a = _create_mock_variant(proj, "A", impressions=2000, views=240, retention=48.0)
        var_b = _create_mock_variant(proj, "B", impressions=2000, views=180, retention=65.0)

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(project_dir=proj, video_id=video_id, variants=[var_a, var_b])

        decision = coordinator.evaluate_performance(project_dir=proj, video_id=video_id)
        assert decision.winner_variant_id == "B"
        assert decision.is_significant is False
        assert "Retention guardrail veto" in decision.rationale

    def test_boundary_zero_impressions_no_crash(self, tmp_path: Path) -> None:
        """Verify coordinator handles variants with zero impressions gracefully without ZeroDivisionError."""
        proj = tmp_path / "proj_zero_imp"
        proj.mkdir()
        video_id = "v_zero_imp"

        var_a = _create_mock_variant(proj, "A", impressions=0, views=0, ctr=0.0, retention=0.0)
        var_b = _create_mock_variant(proj, "B", impressions=0, views=0, ctr=0.0, retention=0.0)

        coordinator = ThumbnailABCoordinator()
        coordinator.initialize_experiment(
            project_dir=proj, video_id=video_id, variants=[var_a, var_b], min_impressions=0
        )

        decision = coordinator.evaluate_performance(project_dir=proj, video_id=video_id, min_impressions=0)
        # Both CTRs are 0.0, identical CTR -> inconclusive
        assert decision.is_significant is False
        assert decision.winner_variant_id is None
