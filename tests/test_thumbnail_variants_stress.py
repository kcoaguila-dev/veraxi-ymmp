"""Adversarial Empirical Stress Suite for YouTube Thumbnail A/B Variant Engine (Milestone 1).

Author: challenger_m1_2 (Empirical Challenger)
Focus:
- Nested serialization / deserialization of ThumbnailExperiment, RotationEvent, VariantMetrics
- Boundary coercion, sparse dicts, and deep copy isolation in domain models
- Unicode, emoji, RTL, special characters, and massive strings in auto_extract_variant_configs
- Polymorphic input parsing and error resilience (corrupt JSON, UTF-8 BOM, missing fields)
- Multi-video state isolation and rapid rotation state tracking in MockYouTubeAdapter
- Monotonic timestamp ordering, division-by-zero protection, and multithreaded concurrency
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import Dict, List


from veraxi_ymmp.ir import (
    RotationEvent,
    ThumbnailExperiment,
    ThumbnailVariant,
    VariantMetrics,
    WinnerDecision,
)
from veraxi_ymmp.thumbnail import (
    ThumbnailConfig,
    auto_extract_variant_configs,
    validate_thumbnail_file_size,
)
from veraxi_ymmp.youtube_adapter import (
    THUMBNAIL_MAX_SIZE_BYTES,
    MockYouTubeAdapter,
)


# ==============================================================================
# 1. Complex Domain Model Serialization, Deserialization & Type Coercion
# ==============================================================================

class TestDomainModelStressAndSerialization:
    """Stress-test domain models under heavy payloads, nested structures, and type coercion."""

    def test_massive_thumbnail_experiment_roundtrip(self, tmp_path: Path) -> None:
        """Verify ThumbnailExperiment serializes and restores with 10+ variants and 500+ events."""
        proj_dir = tmp_path / "project_深層検証_2026_🚀"
        proj_dir.mkdir(parents=True, exist_ok=True)

        # Generate 12 distinct variants with nested metrics
        variants: Dict[str, ThumbnailVariant] = {}
        for i in range(12):
            vid = f"V_{i:02d}"
            v_path = proj_dir / f"thumb_{vid.lower()}.png"
            metrics = VariantMetrics(
                variant_id=vid,
                impressions=1000 * (i + 1),
                views=120 * (i + 1),
                ctr=(120 * (i + 1)) / (1000 * (i + 1)),
                average_view_percentage=55.0 + i,
                average_view_duration_sec=110.0 + (i * 2),
                retention_score=(55.0 + i) / 100.0,
                sample_start=f"2026-10-{10 + i:02d}T00:00:00Z",
                sample_end=f"2026-10-{11 + i:02d}T00:00:00Z",
                raw_metrics={"batch_id": i, "unicode_tag": f"実験タグ_{i}番"},
            )
            variants[vid] = ThumbnailVariant(
                variant_id=vid,
                name=f"バリアント_{vid}【最高峰】🔥",
                thumbnail_path=v_path,
                config={"theme": "gold" if i % 2 == 0 else "red", "index": i},
                metrics=metrics,
                is_active=(i == 11),
                rotation_count=i * 3,
            )

        # Generate 500 rotation events
        history: List[RotationEvent] = []
        for step in range(500):
            from_v = f"V_{step % 12:02d}"
            to_v = f"V_{(step + 1) % 12:02d}"
            history.append(
                RotationEvent(
                    timestamp=f"2026-10-20T{(step // 60) % 24:02d}:{step % 60:02d}:00Z",
                    video_id="video_stress_999",
                    from_variant_id=from_v,
                    to_variant_id=to_v,
                    reason=f"rapid_rotation_step_{step}",
                )
            )

        decision = WinnerDecision(
            winner_variant_id="V_11",
            winning_score=0.942,
            margin=0.185,
            is_significant=True,
            p_value=0.00042,
            committed=True,
            committed_at="2026-10-21T18:30:00Z",
            rationale="勝率99.9%有意差確定 (Z=3.52, p=0.00042) - 圧倒的CTRと視聴維持率達成",
        )

        experiment = ThumbnailExperiment(
            experiment_id="exp_massive_stress_001",
            video_id="video_stress_999",
            project_dir=proj_dir,
            status="CONCLUDED",
            active_variant_id="V_11",
            variants=variants,
            rotation_history=history,
            winner_decision=decision,
            min_impressions=10000,
            min_observation_hours=72.0,
            created_at="2026-10-15T00:00:00Z",
            updated_at="2026-10-21T18:30:00Z",
        )

        d = experiment.to_dict()
        # Strictly verify full JSON serializability without throwing
        json_str = json.dumps(d, ensure_ascii=False)
        assert len(json_str) > 10000

        data = json.loads(json_str)
        restored = ThumbnailExperiment.from_dict(data)

        # Deep assertions
        assert restored.experiment_id == "exp_massive_stress_001"
        assert restored.video_id == "video_stress_999"
        assert restored.project_dir == proj_dir
        assert restored.status == "CONCLUDED"
        assert restored.active_variant_id == "V_11"
        assert len(restored.variants) == 12
        assert len(restored.rotation_history) == 500
        assert restored.rotation_history[0].from_variant_id == "V_00"
        assert restored.rotation_history[0].to_variant_id == "V_01"
        assert restored.rotation_history[499].to_variant_id == f"V_{(499 + 1) % 12:02d}"
        assert restored.winner_decision is not None
        assert restored.winner_decision.winner_variant_id == "V_11"
        assert restored.winner_decision.p_value == 0.00042
        assert restored.winner_decision.is_significant is True
        assert "有意差確定" in restored.winner_decision.rationale
        assert restored.variants["V_05"].name == "バリアント_V_05【最高峰】🔥"
        assert restored.variants["V_05"].metrics.raw_metrics["unicode_tag"] == "実験タグ_5番"

    def test_type_coercion_from_string_payloads(self) -> None:
        """Verify from_dict methods cleanly coerce stringified numbers and handle missing keys."""
        # VariantMetrics string coercion
        raw_metrics_data = {
            "variant_id": "A",
            "impressions": "5400",
            "views": "648",
            "ctr": "0.12",
            "average_view_percentage": "68.4",
            "average_view_duration_sec": "136.8",
            "retention_score": "0.684",
        }
        vm = VariantMetrics.from_dict(raw_metrics_data)
        assert vm.impressions == 5400
        assert vm.views == 648
        assert abs(vm.ctr - 0.12) < 1e-6
        assert abs(vm.average_view_percentage - 68.4) < 1e-6

        # WinnerDecision string coercion and null handling
        raw_winner_data = {
            "winner_variant_id": "B",
            "winning_score": "0.85",
            "margin": "0.10",
            "is_significant": True,
            "p_value": "0.025",
            "committed": True,
            "rationale": "Strong CTR lead",
        }
        wd = WinnerDecision.from_dict(raw_winner_data)
        assert wd.winning_score == 0.85
        assert wd.margin == 0.10
        assert wd.p_value == 0.025

        # Minimal / sparse dicts
        sparse_vm = VariantMetrics.from_dict({})
        assert sparse_vm.variant_id == ""
        assert sparse_vm.impressions == 0
        assert sparse_vm.ctr == 0.0

        sparse_event = RotationEvent.from_dict({})
        assert sparse_event.timestamp == ""
        assert sparse_event.from_variant_id is None
        assert sparse_event.to_variant_id == ""

        sparse_exp = ThumbnailExperiment.from_dict({"project_dir": "temp/proj"})
        assert sparse_exp.experiment_id == ""
        assert sparse_exp.project_dir == Path("temp/proj")
        assert sparse_exp.status == "DRAFT"
        assert sparse_exp.variants == {}
        assert sparse_exp.rotation_history == []
        assert sparse_exp.winner_decision is None

    def test_dataclass_mutation_isolation(self) -> None:
        """Verify default instances do not share mutable collections across instances."""
        m1 = VariantMetrics(variant_id="M1")
        m2 = VariantMetrics(variant_id="M2")
        m1.raw_metrics["key"] = "value1"
        assert "key" not in m2.raw_metrics

        v1 = ThumbnailVariant(variant_id="V1", name="V1", thumbnail_path=Path("v1.png"))
        v2 = ThumbnailVariant(variant_id="V2", name="V2", thumbnail_path=Path("v2.png"))
        v1.config["theme"] = "red"
        assert "theme" not in v2.config

        exp1 = ThumbnailExperiment(experiment_id="E1", video_id="V1", project_dir=Path("p1"))
        exp2 = ThumbnailExperiment(experiment_id="E2", video_id="V2", project_dir=Path("p2"))
        exp1.variants["A"] = v1
        exp1.rotation_history.append(RotationEvent("t", "v", "A", "B", "r"))
        assert "A" not in exp2.variants
        assert len(exp2.rotation_history) == 0


# ==============================================================================
# 2. Unicode, Special Characters, Emoji & Long Text Stress Tests
# ==============================================================================

class TestUnicodeAndBoundaryStress:
    """Stress auto_extract_variant_configs and thumbnail helpers with adverse text payloads."""

    def test_auto_extract_with_complex_unicode_and_emojis(self) -> None:
        """Verify unicode, emoji, and full-width punctuation propagate cleanly without corruption."""
        cfg = ThumbnailConfig(
            title_line1="【超驚愕】ビットコイン🚀💥",
            title_line2="爆騰か大暴落か！？😱💰",
            highlight_word="大暴落",
            sub_hook="▶ 99.9%の投資家が気付いていない罠！？🔥",
            badge="【緊急速報】",
            character="ずんだもん",
            emotion="surprised",
        )
        variants = auto_extract_variant_configs(cfg)
        assert "A" in variants
        assert "B" in variants

        # Variant A preserves base titles and applies gold theme
        assert variants["A"].title_line1 == "【超驚愕】ビットコイン🚀💥"
        assert variants["A"].theme == "gold"
        assert variants["A"].emotion == "surprised"
        assert variants["A"].badge == "【緊急速報】"

        # Variant B uses red theme, angry emotion, and urgency badge
        assert variants["B"].theme == "red"
        assert variants["B"].emotion == "angry"
        assert variants["B"].badge == "【緊急警告】"
        assert "ビットコイン" in variants["B"].title_line1

    def test_auto_extract_with_extremely_long_strings(self) -> None:
        """Verify 500+ character strings do not cause unhandled exceptions or infinite loops."""
        long_title1 = "本当に信じられない衝撃的事実が判明" * 30  # 540 chars
        long_title2 = "絶対に知っておくべき究極の裏技" * 30    # 450 chars
        cfg = ThumbnailConfig(
            title_line1=long_title1,
            title_line2=long_title2,
            highlight_word="究極の裏技",
            sub_hook="▶ " + ("詳細情報を今すぐ確認！" * 20),
            badge="【超巨大警告】",
            character="ずんだもん",
            emotion="surprised",
        )
        variants = auto_extract_variant_configs(cfg)
        assert len(variants["A"].title_line1) == len(long_title1)
        assert len(variants["B"].title_line1) == len(long_title1)
        assert variants["A"].theme == "gold"
        assert variants["B"].theme == "red"

    def test_auto_extract_with_special_characters_and_injections(self) -> None:
        """Verify quotes, newlines, slashes, and code injection characters are safely handled."""
        weird_text = 'Test "quotes" & \'single\' \n\t <script>alert("xss")</script> \\/ $#!%^*~'
        cfg = ThumbnailConfig(
            title_line1=weird_text,
            title_line2="安全確認！？",
            highlight_word="安全確認",
            sub_hook="▶ 特殊文字テスト",
            badge="【検証】",
        )
        variants = auto_extract_variant_configs(cfg)
        assert variants["A"].title_line1 == weird_text
        assert variants["B"].title_line1 == weird_text

    def test_auto_extract_from_script_list_with_unicode_and_anomalies(self) -> None:
        """Verify parsing script dialogue list containing empty elements, unicode, and varied emotions."""
        script_data = [
            None,  # anomaly: non-dict
            {"character": "四国めたん", "text": "皆様、こんにちは。", "emotion": "happy"},
            {"character": "ずんだもん", "text": "株式市場が大暴落なのだ！😱", "emotion": "surprised"},
            {"character": "ずんだもん", "text": "もうおしまいなのだー！", "emotion": "angry"},
            {},    # anomaly: empty dict
            {"character": "ずんだもん", "text": "新NISAで大損する人が続出なのだ！？", "emotion": "sad"},
        ]
        variants = auto_extract_variant_configs(script_data)  # type: ignore[arg-type]
        assert "A" in variants
        assert "B" in variants
        assert variants["A"].character == "ずんだもん"
        assert variants["A"].theme == "gold"
        assert variants["B"].theme == "red"
        assert variants["B"].emotion == "angry"

    def test_auto_extract_from_project_directory_with_utf8_bom(self, tmp_path: Path) -> None:
        """Verify handling of UTF-8 with BOM (utf-8-sig) in thumbnail_config.json."""
        proj_dir = tmp_path / "bom_proj"
        proj_dir.mkdir()
        cfg_file = proj_dir / "thumbnail_config.json"
        content = json.dumps({
            "default": {
                "title_line1": "BOM付きJSON",
                "title_line2": "正常解析確認",
                "highlight_word": "正常解析",
            },
            "variants": {
                "A": {"theme": "gold", "badge": "【BOM成功】"},
                "B": {"theme": "red", "badge": "【警告】"},
            },
        }, ensure_ascii=False)
        cfg_file.write_bytes(content.encode("utf-8-sig"))

        configs = auto_extract_variant_configs(proj_dir)
        assert len(configs) == 2
        assert configs["A"].badge == "【BOM成功】"
        assert configs["A"].theme == "gold"
        assert configs["B"].theme == "red"

    def test_auto_extract_corrupt_json_fallback(self, tmp_path: Path) -> None:
        """Verify corrupt or unparseable thumbnail_config.json triggers graceful fallback."""
        proj_dir = tmp_path / "corrupt_proj"
        proj_dir.mkdir()
        cfg_file = proj_dir / "thumbnail_config.json"
        cfg_file.write_text("{ unclosed invalid json ...", encoding="utf-8")

        # Must not crash; should log warning and fallback to heuristic or default config
        configs = auto_extract_variant_configs(proj_dir)
        assert "A" in configs
        assert "B" in configs
        assert configs["A"].theme == "gold"
        assert configs["B"].theme == "red"

    def test_validate_thumbnail_file_size_stress(self, tmp_path: Path) -> None:
        """Exhaustive boundary testing for validate_thumbnail_file_size."""
        # Non-file cases
        assert validate_thumbnail_file_size(tmp_path) is False
        assert validate_thumbnail_file_size(tmp_path / "non_existent.png") is False

        # 0 bytes
        f0 = tmp_path / "zero.png"
        f0.write_bytes(b"")
        assert validate_thumbnail_file_size(f0) is True

        # 1 byte
        f1 = tmp_path / "one.png"
        f1.write_bytes(b"x")
        assert validate_thumbnail_file_size(f1) is True

        # Exact limit: 2MB (2,097,152 bytes)
        f_exact = tmp_path / "exact.png"
        with open(f_exact, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES - 1)
            f.write(b"x")
        assert f_exact.stat().st_size == THUMBNAIL_MAX_SIZE_BYTES
        assert validate_thumbnail_file_size(f_exact) is True

        # 1 byte over limit: 2,097,153 bytes
        f_over = tmp_path / "over.png"
        with open(f_over, "wb") as f:
            f.seek(THUMBNAIL_MAX_SIZE_BYTES)
            f.write(b"x")
        assert f_over.stat().st_size == THUMBNAIL_MAX_SIZE_BYTES + 1
        assert validate_thumbnail_file_size(f_over) is False


# ==============================================================================
# 3. Multi-Video Isolation & Rapid Rotation State Tracking in MockYouTubeAdapter
# ==============================================================================

class TestMockYouTubeAdapterIsolationAndRotation:
    """Stress-test MockYouTubeAdapter across multiple video IDs, rapid rotations, and concurrency."""

    def test_multi_video_state_isolation(self, tmp_path: Path) -> None:
        """Verify that thumbnail uploads for distinct video IDs remain completely decoupled."""
        adapter = MockYouTubeAdapter()
        video_ids = [f"video_isolate_{i:03d}" for i in range(5)]

        # Prepare dummy thumbnail files
        thumbs: Dict[str, Dict[str, Path]] = {}
        for vid in video_ids:
            thumbs[vid] = {}
            for var in ["A", "B", "C"]:
                t_path = tmp_path / f"{vid}_{var}.png"
                t_path.write_bytes(f"bytes_{vid}_{var}".encode())
                thumbs[vid][var] = t_path

        # Perform interleaved uploads across videos
        # Video 0: A -> B
        adapter.upload_thumbnail(video_ids[0], thumbs[video_ids[0]]["A"])
        adapter.upload_thumbnail(video_ids[0], thumbs[video_ids[0]]["B"])

        # Video 1: A -> C -> B
        adapter.upload_thumbnail(video_ids[1], thumbs[video_ids[1]]["A"])
        adapter.upload_thumbnail(video_ids[1], thumbs[video_ids[1]]["C"])
        adapter.upload_thumbnail(video_ids[1], thumbs[video_ids[1]]["B"])

        # Video 2: B
        adapter.upload_thumbnail(video_ids[2], thumbs[video_ids[2]]["B"])

        # Video 3: A -> B -> A
        adapter.upload_thumbnail(video_ids[3], thumbs[video_ids[3]]["A"])
        adapter.upload_thumbnail(video_ids[3], thumbs[video_ids[3]]["B"])
        adapter.upload_thumbnail(video_ids[3], thumbs[video_ids[3]]["A"])

        # Video 4: C
        adapter.upload_thumbnail(video_ids[4], thumbs[video_ids[4]]["C"])

        # Assert isolated active thumbnail per video
        assert adapter.uploaded_thumbnails[video_ids[0]] == thumbs[video_ids[0]]["B"]
        assert adapter.uploaded_thumbnails[video_ids[1]] == thumbs[video_ids[1]]["B"]
        assert adapter.uploaded_thumbnails[video_ids[2]] == thumbs[video_ids[2]]["B"]
        assert adapter.uploaded_thumbnails[video_ids[3]] == thumbs[video_ids[3]]["A"]
        assert adapter.uploaded_thumbnails[video_ids[4]] == thumbs[video_ids[4]]["C"]

        # Assert total history count and per-video filtering
        assert len(adapter.thumbnail_history) == 2 + 3 + 1 + 3 + 1  # 10 total
        for vid in video_ids:
            vid_events = [e for e in adapter.thumbnail_history if e["video_id"] == vid]
            assert len(vid_events) > 0
            assert all(e["thumbnail_path"].name.startswith(vid) for e in vid_events)

    def test_rapid_rotation_state_tracking_and_monotonicity(self, tmp_path: Path) -> None:
        """Verify 100 rapid thumbnail rotations track exact history and maintain monotonic timestamps."""
        adapter = MockYouTubeAdapter()
        vid = "video_rapid_rot_01"

        thumb_a = tmp_path / "thumb_a.png"
        thumb_b = tmp_path / "thumb_b.png"
        thumb_a.write_bytes(b"thumb_a")
        thumb_b.write_bytes(b"thumb_b")

        # Execute 100 back-and-forth rotations
        for i in range(100):
            target_thumb = thumb_a if i % 2 == 0 else thumb_b
            adapter.upload_thumbnail(vid, target_thumb)

        assert len(adapter.thumbnail_history) == 100
        assert adapter.uploaded_thumbnails[vid] == thumb_b  # 99th is odd -> B

        # Verify timestamp monotonicity
        timestamps = [e["timestamp"] for e in adapter.thumbnail_history]
        for idx in range(len(timestamps) - 1):
            assert timestamps[idx] <= timestamps[idx + 1], f"Non-monotonic timestamp at index {idx}"

        # Verify call log entries
        expected_calls = [f"upload_thumbnail:{vid}"] * 100
        actual_calls = [c for c in adapter.call_log if c.startswith("upload_thumbnail")]
        assert actual_calls == expected_calls

    def test_simulated_variant_metrics_multi_key_isolation(self) -> None:
        """Verify simulated metrics retrieval across multiple keys and default fallbacks."""
        adapter = MockYouTubeAdapter()

        # Zero simulated metrics -> returns default metrics for any video_id
        default_m = adapter.fetch_variant_metrics("vid_unknown")
        assert default_m.variant_id == "vid_unknown"
        assert default_m.impressions == 1000
        assert default_m.views == 120

        # One simulated metric -> returned for single variant
        adapter.set_simulated_metrics("variant_solo", impressions=5000, views=750, ctr=0.15)
        solo_m = adapter.fetch_variant_metrics("variant_solo")
        assert solo_m.variant_id == "variant_solo"
        assert solo_m.impressions == 5000
        assert solo_m.views == 750
        assert solo_m.ctr == 0.15

        # Multiple simulated metrics -> strictly isolated by key
        adapter.set_simulated_metrics("variant_alpha", impressions=2000, views=200, ctr=0.10)
        adapter.set_simulated_metrics("variant_beta", impressions=4000, views=800, ctr=0.20)

        m_alpha = adapter.fetch_variant_metrics("variant_alpha")
        m_beta = adapter.fetch_variant_metrics("variant_beta")
        m_other = adapter.fetch_variant_metrics("variant_unconfigured")

        assert m_alpha.impressions == 2000
        assert m_alpha.views == 200
        assert m_alpha.ctr == 0.10

        assert m_beta.impressions == 4000
        assert m_beta.views == 800
        assert m_beta.ctr == 0.20

        # Unconfigured key with multiple simulated metrics falls back to defaults
        assert m_other.variant_id == "variant_unconfigured"
        assert m_other.impressions == 1000
        assert m_other.views == 120

    def test_simulated_variant_metrics_division_by_zero_safety(self) -> None:
        """Verify set_simulated_metrics handles 0 impressions and 0 views without crashing."""
        adapter = MockYouTubeAdapter()
        adapter.set_simulated_metrics("variant_zero", impressions=0, views=0)
        m = adapter.fetch_variant_metrics("variant_zero")
        assert m.variant_id == "variant_zero"
        assert m.impressions == 0
        assert m.views == 0
        assert m.ctr == 0.0

    def test_multithreaded_concurrent_upload_stress(self, tmp_path: Path) -> None:
        """Verify thread-safety of MockYouTubeAdapter state when 10 threads concurrently upload thumbnails."""
        adapter = MockYouTubeAdapter()
        num_threads = 10
        uploads_per_thread = 10

        # Prepare dummy thumbnails
        thumb_files = [tmp_path / f"thread_thumb_{i}.png" for i in range(num_threads)]
        for f in thumb_files:
            f.write_bytes(b"thread_safe_data")

        def worker(thread_idx: int) -> None:
            vid = f"vid_thread_{thread_idx % 5}"  # 5 shared videos
            for u in range(uploads_per_thread):
                adapter.upload_thumbnail(vid, thumb_files[thread_idx])

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()  # raise exception if any thread failed

        # Verify state integrity
        expected_total = num_threads * uploads_per_thread  # 100
        assert len(adapter.thumbnail_history) == expected_total
        assert len(adapter.uploaded_thumbnails) == 5  # 5 distinct video IDs
        assert len([c for c in adapter.call_log if c.startswith("upload_thumbnail")]) == expected_total
