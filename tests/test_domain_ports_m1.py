"""Empirical adversarial test suite for Milestone M1: Domain Models and Ports.

Tests:
1. Mutable defaults isolation (field default_factory integrity) across all models.
2. Boundary and edge-case values (zeros, negatives, empty collections, massive payloads).
3. Protocol runtime checking (@runtime_checkable) for VideoPublisher and VideoAnalyticsProvider.
4. Dataclass equality, copy/replace semantics, and dictionary serialization.
5. Re-exports and Clean Architecture boundary contracts.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import List, Optional, Tuple

from veraxi_ymmp.ir import (
    CutRetentionMetric,
    RetentionDropoffPoint,
    RetentionPoint,
    UploadResult,
    VideoPublishMetadata,
    VideoRetentionReport,
)
from veraxi_ymmp.ports import (
    CutRetentionMetric as PortCutRetentionMetric,
    ProgressCallback,
    RetentionDropoffPoint as PortRetentionDropoffPoint,
    RetentionPoint as PortRetentionPoint,
    UploadResult as PortUploadResult,
    VideoAnalyticsProvider,
    VideoPublisher,
    VideoPublishMetadata as PortVideoPublishMetadata,
    VideoRetentionReport as PortVideoRetentionReport,
)


class TestMutableDefaultsIsolation:
    """Verify that mutable fields do not share default collections across instances."""

    def test_video_publish_metadata_tags_isolation(self) -> None:
        meta1 = VideoPublishMetadata(title="Video 1")
        meta2 = VideoPublishMetadata(title="Video 2")

        assert meta1.tags is not meta2.tags
        assert len(meta1.tags) == 0
        assert len(meta2.tags) == 0

        meta1.tags.append("leak_tag")
        assert "leak_tag" in meta1.tags
        assert "leak_tag" not in meta2.tags
        assert len(meta2.tags) == 0

    def test_upload_result_raw_response_isolation(self) -> None:
        res1 = UploadResult(video_id="id1", url="http://1", status="ok")
        res2 = UploadResult(video_id="id2", url="http://2", status="ok")

        assert res1.raw_response is not res2.raw_response
        res1.raw_response["custom_token"] = "leak"
        assert "custom_token" in res1.raw_response
        assert "custom_token" not in res2.raw_response

    def test_video_retention_report_collections_isolation(self) -> None:
        rep1 = VideoRetentionReport(
            video_id="v1",
            video_title="Title 1",
            total_duration_sec=60.0,
            total_cuts=5,
            retention_score=85.0,
            average_view_percentage=70.0,
        )
        rep2 = VideoRetentionReport(
            video_id="v2",
            video_title="Title 2",
            total_duration_sec=120.0,
            total_cuts=10,
            retention_score=90.0,
            average_view_percentage=80.0,
        )

        assert rep1.dropoff_points is not rep2.dropoff_points
        assert rep1.cut_metrics is not rep2.cut_metrics
        assert rep1.editorial_recommendations is not rep2.editorial_recommendations

        drop = RetentionDropoffPoint(
            timestamp_sec=10.0,
            elapsed_ratio=0.16,
            retention_before=0.8,
            retention_after=0.7,
            drop_magnitude=0.1,
            cut_index=1,
            speaker="ずんだもん",
            subtitle_text="テスト",
            emotion="normal",
        )
        cut = CutRetentionMetric(
            cut_index=0,
            speaker="四国めたん",
            text="セリフ",
            start_sec=0.0,
            end_sec=5.0,
            start_retention=1.0,
            end_retention=0.9,
            retention_change=-0.1,
        )

        rep1.dropoff_points.append(drop)
        rep1.cut_metrics.append(cut)
        rep1.editorial_recommendations.append("Cut pacing")

        assert len(rep2.dropoff_points) == 0
        assert len(rep2.cut_metrics) == 0
        assert len(rep2.editorial_recommendations) == 0


class TestBoundaryAndEdgeCases:
    """Stress-test domain models under boundary and extreme conditions."""

    def test_video_publish_metadata_extreme_strings(self) -> None:
        huge_str = "A" * 100_000
        meta = VideoPublishMetadata(
            title=huge_str,
            description=huge_str,
            tags=[huge_str, "", "tag with spaces", "🚀🎉", "日本語タグ"],
            category_id="0",
            privacy_status="private",
            made_for_kids=True,
            publish_at="2026-12-31T23:59:59Z",
            language="zh-CN",
            thumbnail_path=Path("non_existent_dir") / "huge.png",
        )
        assert len(meta.title) == 100_000
        assert len(meta.description) == 100_000
        assert len(meta.tags) == 5
        assert meta.thumbnail_path == Path("non_existent_dir") / "huge.png"

    def test_video_publish_metadata_defaults(self) -> None:
        meta = VideoPublishMetadata(title="Minimal")
        assert meta.title == "Minimal"
        assert meta.description == ""
        assert meta.tags == []
        assert meta.category_id == "22"
        assert meta.privacy_status == "private"
        assert meta.made_for_kids is False
        assert meta.publish_at is None
        assert meta.language == "ja"
        assert meta.thumbnail_path is None

    def test_upload_result_boundaries(self) -> None:
        # Zero bytes
        res_zero = UploadResult(video_id="", url="", status="pending", bytes_uploaded=0, total_bytes=0)
        assert res_zero.bytes_uploaded == 0
        assert res_zero.total_bytes == 0

        # Overshoot / large byte counts (100GB)
        res_large = UploadResult(
            video_id="abc",
            url="https://youtube.com/watch?v=abc",
            status="completed",
            thumbnail_uploaded=True,
            bytes_uploaded=107374182400,
            total_bytes=107374182400,
            raw_response={"kind": "youtube#video", "id": "abc"},
        )
        assert res_large.bytes_uploaded == 107374182400
        assert res_large.thumbnail_uploaded is True

    def test_retention_point_boundaries(self) -> None:
        # 0.0 boundary
        p0 = RetentionPoint(elapsed_time_ratio=0.0, watch_ratio=1.0, timestamp_sec=0.0)
        assert p0.elapsed_time_ratio == 0.0
        assert p0.watch_ratio == 1.0
        assert p0.relative_retention is None

        # 1.0 boundary
        p1 = RetentionPoint(elapsed_time_ratio=1.0, watch_ratio=0.35, timestamp_sec=3600.0, relative_retention=0.8)
        assert p1.elapsed_time_ratio == 1.0
        assert p1.watch_ratio == 0.35
        assert p1.relative_retention == 0.8

        # Rewatched segment (watch_ratio > 1.0)
        p_rewatch = RetentionPoint(elapsed_time_ratio=0.5, watch_ratio=1.85, timestamp_sec=30.0)
        assert p_rewatch.watch_ratio > 1.0

    def test_retention_dropoff_point_defaults_and_options(self) -> None:
        drop = RetentionDropoffPoint(
            timestamp_sec=15.5,
            elapsed_ratio=0.25,
            retention_before=0.92,
            retention_after=0.81,
            drop_magnitude=0.11,
            cut_index=3,
            speaker="ずんだもん",
            subtitle_text="ここで離脱発生なのだ！",
            emotion="surprised",
        )
        assert drop.broll_image is None
        assert drop.issue_type == "PACING_OR_FATIGUE"
        assert drop.recommendation == ""

    def test_video_retention_report_defaults(self) -> None:
        rep = VideoRetentionReport(
            video_id="xyz",
            video_title="Summary Test",
            total_duration_sec=0.0,
            total_cuts=0,
            retention_score=0.0,
            average_view_percentage=0.0,
        )
        assert rep.dropoff_threshold == 0.05
        assert rep.dropoff_points == []
        assert rep.cut_metrics == []
        assert rep.summary_verdict == "NOMINAL"
        assert rep.editorial_recommendations == []


class TestProtocolRuntimeChecking:
    """Adversarially challenge runtime_checkable Protocol behavior."""

    def test_video_publisher_valid_implementation(self) -> None:
        class ValidPublisher:
            def upload_video(self, video_path, metadata, progress_callback=None):
                return UploadResult(video_id="d1", url="", status="uploaded")
            def upload_thumbnail(self, video_id, thumbnail_path):
                return True
            def upload_caption(self, video_id, caption_path, language="ja", name="", is_draft=False):
                return True

        pub = ValidPublisher()
        assert isinstance(pub, VideoPublisher)

    def test_video_publisher_missing_upload_thumbnail(self) -> None:
        class IncompletePublisher:
            def upload_video(
                self,
                video_path: Path,
                metadata: VideoPublishMetadata,
                progress_callback: Optional[ProgressCallback] = None,
            ) -> UploadResult:
                return UploadResult(video_id="v", url="u", status="s")

        pub = IncompletePublisher()
        assert not isinstance(pub, VideoPublisher)

    def test_video_publisher_missing_upload_video(self) -> None:
        class IncompletePublisher:
            def upload_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
                return True

        pub = IncompletePublisher()
        assert not isinstance(pub, VideoPublisher)

    def test_video_publisher_pep544_runtime_checkable_semantics(self) -> None:
        """Under PEP 544, @runtime_checkable checks hasattr, not callability or type signatures."""
        class NonCallablePublisher:
            upload_video = "not_callable"
            upload_thumbnail = 42
            upload_caption = 42
            upload_caption = 42

        pub = NonCallablePublisher()
        # PEP 544 standard behavior: hasattr is True, so isinstance is True
        assert isinstance(pub, VideoPublisher)
        # However, calling them at runtime would fail with TypeError
        assert not callable(getattr(pub, "upload_video"))

    def test_video_analytics_provider_valid_implementation(self) -> None:
        class ValidAnalytics:
            def fetch_retention_curve(self, video_id, start_date=None, end_date=None):
                return [(0.0, 1.0), (1.0, 0.5)]
            def fetch_variant_metrics(self, video_id, start_date=None, end_date=None):
                return {}
            def fetch_stats_report(self, video_ids, start_date, end_date, metrics, granularity="total"):
                from veraxi_ymmp.ports import VideoStatsReport
                return VideoStatsReport(video_id=video_ids[0], title="", published_at="", rows=[])
            def get_channel_info(self):
                return ("id", "title")

        analytics = ValidAnalytics()
        assert isinstance(analytics, VideoAnalyticsProvider)

    def test_video_analytics_provider_missing_fetch_curve(self) -> None:
        class IncompleteAnalytics:
            def other_method(self) -> None:
                pass

        analytics = IncompleteAnalytics()
        assert not isinstance(analytics, VideoAnalyticsProvider)

    def test_video_analytics_provider_pep544_runtime_checkable_semantics(self) -> None:
        """Under PEP 544, @runtime_checkable checks hasattr, not callability or type signatures."""
        class NonCallableAnalytics:
            fetch_retention_curve = 12345
            fetch_variant_metrics = 12345
            fetch_stats_report = 12345
            get_channel_info = 12345

        analytics = NonCallableAnalytics()
        # PEP 544 standard behavior: hasattr is True, so isinstance is True
        assert isinstance(analytics, VideoAnalyticsProvider)
        assert not callable(getattr(analytics, "fetch_retention_curve"))

    def test_progress_callback_invocation(self) -> None:
        calls: List[Tuple[float, int, int]] = []

        def my_callback(ratio: float, current: int, total: int) -> None:
            calls.append((ratio, current, total))

        # ProgressCallback is a type alias Callable[[float, int, int], None]
        cb: ProgressCallback = my_callback
        cb(0.5, 50, 100)
        assert len(calls) == 1
        assert calls[0] == (0.5, 50, 100)


class TestDataclassSemantics:
    """Verify dataclass copy, replacement, equality, and dict conversion."""

    def test_dataclass_equality_and_replace(self) -> None:
        meta1 = VideoPublishMetadata(title="Test", tags=["tag1"])
        meta2 = VideoPublishMetadata(title="Test", tags=["tag1"])
        assert meta1 == meta2

        meta3 = replace(meta1, title="Changed")
        assert meta3.title == "Changed"
        assert meta3.tags == ["tag1"]
        assert meta1.title == "Test"

    def test_asdict_serialization(self) -> None:
        rep = VideoRetentionReport(
            video_id="v123",
            video_title="Retention Test",
            total_duration_sec=120.0,
            total_cuts=2,
            retention_score=78.5,
            average_view_percentage=65.2,
            dropoff_points=[
                RetentionDropoffPoint(
                    timestamp_sec=20.0,
                    elapsed_ratio=0.166,
                    retention_before=0.9,
                    retention_after=0.8,
                    drop_magnitude=0.1,
                    cut_index=0,
                    speaker="ずんだもん",
                    subtitle_text="テスト",
                    emotion="neutral",
                )
            ],
            cut_metrics=[
                CutRetentionMetric(
                    cut_index=0,
                    speaker="ずんだもん",
                    text="テスト",
                    start_sec=0.0,
                    end_sec=20.0,
                    start_retention=1.0,
                    end_retention=0.8,
                    retention_change=-0.2,
                )
            ],
            editorial_recommendations=["Pacing check"],
        )
        d = asdict(rep)
        assert isinstance(d, dict)
        assert d["video_id"] == "v123"
        assert len(d["dropoff_points"]) == 1
        assert d["dropoff_points"][0]["drop_magnitude"] == 0.1
        assert len(d["cut_metrics"]) == 1
        assert d["cut_metrics"][0]["retention_change"] == -0.2


class TestPortsReExports:
    """Verify identical identity between veraxi_ymmp.ir and veraxi_ymmp.ports."""

    def test_reexported_types_identity(self) -> None:
        assert PortVideoPublishMetadata is VideoPublishMetadata
        assert PortUploadResult is UploadResult
        assert PortRetentionPoint is RetentionPoint
        assert PortRetentionDropoffPoint is RetentionDropoffPoint
        assert PortCutRetentionMetric is CutRetentionMetric
        assert PortVideoRetentionReport is VideoRetentionReport
