"""
Challenger 2 Empirical Verification Suite for Milestone M1.

Tests typing, runtime protocols, dataclass serialization (asdict & JSON),
mutable default factory isolation, and import side effects.
"""

from __future__ import annotations

import collections.abc
import inspect
import json
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple, get_args, get_origin

import pytest

from veraxi_ymmp.ir import (
    CutRetentionMetric,
    RetentionDropoffPoint,
    RetentionPoint,
    UploadResult,
    VideoPublishMetadata,
    VideoRetentionReport,
)
from veraxi_ymmp.ports import (
    ProgressCallback,
    VideoAnalyticsProvider,
    VideoPublisher,
)


# ==============================================================================
# 1. Protocol Runtime Checkability & Partial Class Discrimination
# ==============================================================================

class DummyPublisherComplete:
    def upload_video(self, video_path, metadata, progress_callback=None):
        return UploadResult(video_id="test", url="url", status="ok")
    def upload_thumbnail(self, video_id, thumbnail_path):
        return True
    def upload_caption(self, video_id, caption_path, language="ja", name="", is_draft=False):
        return True


class DummyPublisherMissingThumbnail:
    def upload_video(
        self,
        video_path: Path,
        metadata: VideoPublishMetadata,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UploadResult:
        return UploadResult(video_id="dummy", url="https://youtu.be/dummy", status="uploaded")


class DummyPublisherMissingVideo:
    def upload_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        return True


class DummyAnalyticsComplete:
    def fetch_retention_curve(self, video_id, start_date=None, end_date=None):
        return [(0.0, 1.0)]
    def fetch_variant_metrics(self, video_id, start_date=None, end_date=None):
        return {}
    def fetch_stats_report(self, video_ids, start_date, end_date, metrics, granularity="total"):
        from veraxi_ymmp.ports import VideoStatsReport
        return VideoStatsReport(video_id=video_ids[0], title="", published_at="", rows=[])
    def get_channel_info(self):
        return ("id", "title")


class DummyAnalyticsMissingMethod:
    pass


def test_video_publisher_protocol_complete_passes_isinstance():
    complete = DummyPublisherComplete()
    assert isinstance(complete, VideoPublisher)


def test_video_publisher_protocol_partial_fails_isinstance():
    missing_thumb = DummyPublisherMissingThumbnail()
    missing_video = DummyPublisherMissingVideo()
    empty_obj = object()

    assert not isinstance(missing_thumb, VideoPublisher), "Missing upload_thumbnail should fail isinstance"
    assert not isinstance(missing_video, VideoPublisher), "Missing upload_video should fail isinstance"
    assert not isinstance(empty_obj, VideoPublisher)


def test_video_analytics_protocol_complete_passes_isinstance():
    complete = DummyAnalyticsComplete()
    assert isinstance(complete, VideoAnalyticsProvider)


def test_video_analytics_protocol_partial_fails_isinstance():
    missing = DummyAnalyticsMissingMethod()
    assert not isinstance(missing, VideoAnalyticsProvider)


def test_protocol_pep544_runtime_checkable_attribute_semantics():
    """Document and verify PEP 544 @runtime_checkable behavior.

    PEP 544 runtime_checkable verifies that attributes exist on the class or instance.
    It does not inspect type signatures or callability by default.
    """
    class NonCallablePublisher:
        upload_video = "not_callable"
        upload_thumbnail = 42
        upload_caption = "not_callable"

    # Under PEP 544, hasattr checks pass
    assert isinstance(NonCallablePublisher(), VideoPublisher)

    # However, strict contract validation should check callable()
    assert not callable(getattr(NonCallablePublisher, "upload_video"))
    assert callable(getattr(DummyPublisherComplete, "upload_video"))


def test_protocol_method_signatures():
    # VideoPublisher signatures
    pub_sig = inspect.signature(VideoPublisher.upload_video)
    assert "video_path" in pub_sig.parameters
    assert "metadata" in pub_sig.parameters
    assert "progress_callback" in pub_sig.parameters

    thumb_sig = inspect.signature(VideoPublisher.upload_thumbnail)
    assert "video_id" in thumb_sig.parameters
    assert "thumbnail_path" in thumb_sig.parameters

    # VideoAnalyticsProvider signatures
    analytics_sig = inspect.signature(VideoAnalyticsProvider.fetch_retention_curve)
    assert "video_id" in analytics_sig.parameters
    assert "start_date" in analytics_sig.parameters
    assert "end_date" in analytics_sig.parameters


# ==============================================================================
# 2. ProgressCallback Signature Verification
# ==============================================================================

def test_progress_callback_type_contract():
    # ProgressCallback = Callable[[float, int, int], None]
    origin = get_origin(ProgressCallback)
    args = get_args(ProgressCallback)

    assert origin is collections.abc.Callable or origin is Callable
    assert len(args) == 2
    # args[0] is parameter types, args[1] is return type
    param_types = args[0]
    return_type = args[1]

    assert list(param_types) == [float, int, int]
    assert return_type is type(None)


def test_progress_callback_execution():
    called_records: List[Tuple[float, int, int]] = []

    def mock_cb(ratio: float, uploaded: int, total: int) -> None:
        called_records.append((ratio, uploaded, total))

    # Verify mock_cb adheres to signature
    sig = inspect.signature(mock_cb)
    params = list(sig.parameters.values())
    assert len(params) == 3

    # Call it
    mock_cb(0.5, 512, 1024)
    assert called_records == [(0.5, 512, 1024)]

    # Mismatched argument count should raise TypeError
    with pytest.raises(TypeError):
        mock_cb(0.5, 512)  # type: ignore


# ==============================================================================
# 3. Dataclass Serialization (`asdict`) & Mutable Default Isolation
# ==============================================================================

def test_dataclass_conformance_and_asdict():
    # 1. RetentionPoint
    rp = RetentionPoint(elapsed_time_ratio=0.25, watch_ratio=0.88, timestamp_sec=15.0, relative_retention=1.05)
    assert is_dataclass(rp)
    rp_dict = asdict(rp)
    assert rp_dict == {
        "elapsed_time_ratio": 0.25,
        "watch_ratio": 0.88,
        "timestamp_sec": 15.0,
        "relative_retention": 1.05,
    }
    assert json.loads(json.dumps(rp_dict)) == rp_dict

    # 2. RetentionDropoffPoint
    rdp = RetentionDropoffPoint(
        timestamp_sec=20.5,
        elapsed_ratio=0.34,
        retention_before=0.80,
        retention_after=0.72,
        drop_magnitude=0.08,
        cut_index=4,
        speaker="ずんだもん",
        subtitle_text="テストなのだ！",
        emotion="surprised",
        broll_image="slide_04.png",
        issue_type="PACING_OR_FATIGUE",
        recommendation="短縮を検討",
    )
    assert is_dataclass(rdp)
    rdp_dict = asdict(rdp)
    assert rdp_dict["drop_magnitude"] == 0.08
    assert rdp_dict["speaker"] == "ずんだもん"
    assert json.loads(json.dumps(rdp_dict)) == rdp_dict

    # 3. CutRetentionMetric
    crm = CutRetentionMetric(
        cut_index=1,
        speaker="四国めたん",
        text="こんにちは",
        start_sec=0.0,
        end_sec=3.5,
        start_retention=1.0,
        end_retention=0.96,
        retention_change=-0.04,
        broll_image=None,
    )
    assert is_dataclass(crm)
    crm_dict = asdict(crm)
    assert json.loads(json.dumps(crm_dict)) == crm_dict

    # 4. VideoRetentionReport with nested dataclasses
    rep = VideoRetentionReport(
        video_id="test_vid_123",
        video_title="検証動画",
        total_duration_sec=60.0,
        total_cuts=10,
        retention_score=82.5,
        average_view_percentage=75.0,
        dropoff_threshold=0.05,
        dropoff_points=[rdp],
        cut_metrics=[crm],
        summary_verdict="ACTION_REQUIRED",
        editorial_recommendations=["Cut 4 is too slow"],
    )
    assert is_dataclass(rep)
    rep_dict = asdict(rep)
    assert len(rep_dict["dropoff_points"]) == 1
    assert rep_dict["dropoff_points"][0]["speaker"] == "ずんだもん"
    assert len(rep_dict["cut_metrics"]) == 1
    # Check full JSON round-trip of nested report
    json_str = json.dumps(rep_dict, ensure_ascii=False)
    assert json.loads(json_str) == rep_dict

    # 5. UploadResult
    ur = UploadResult(
        video_id="abc12345",
        url="https://youtu.be/abc12345",
        status="uploaded",
        thumbnail_uploaded=True,
        error_message=None,
        bytes_uploaded=1048576,
        total_bytes=1048576,
        raw_response={"id": "abc12345", "kind": "youtube#video"},
    )
    assert is_dataclass(ur)
    ur_dict = asdict(ur)
    assert json.loads(json.dumps(ur_dict)) == ur_dict


def test_video_publish_metadata_asdict_and_path_serialization():
    # Case A: thumbnail_path is None -> standard JSON serializable
    vpm_none = VideoPublishMetadata(title="タイトル", description="説明", tags=["tag1", "tag2"])
    dict_none = asdict(vpm_none)
    assert dict_none["thumbnail_path"] is None
    assert json.loads(json.dumps(dict_none, ensure_ascii=False)) == dict_none

    # Case B: thumbnail_path is Path -> asdict preserves Path, json.dumps requires str converter
    thumb_path = Path("artifacts/thumbnails/thumb.jpg")
    vpm_path = VideoPublishMetadata(title="タイトル", thumbnail_path=thumb_path)
    dict_path = asdict(vpm_path)
    assert dict_path["thumbnail_path"] == thumb_path

    # Standard json.dumps fails without default=str
    with pytest.raises(TypeError):
        json.dumps(dict_path)

    # With default=str it serializes properly
    json_path_str = json.dumps(dict_path, default=str)
    deserialized = json.loads(json_path_str)
    assert Path(deserialized["thumbnail_path"]) == thumb_path


def test_mutable_default_isolation():
    """Verify that mutable collections are separate instances across instances."""
    m1 = VideoPublishMetadata(title="M1")
    m2 = VideoPublishMetadata(title="M2")
    m1.tags.append("custom_tag")
    assert "custom_tag" not in m2.tags

    r1 = VideoRetentionReport(
        video_id="v1", video_title="V1", total_duration_sec=10.0, total_cuts=1, retention_score=90.0, average_view_percentage=80.0
    )
    r2 = VideoRetentionReport(
        video_id="v2", video_title="V2", total_duration_sec=20.0, total_cuts=2, retention_score=85.0, average_view_percentage=75.0
    )
    r1.dropoff_points.append(
        RetentionDropoffPoint(
            timestamp_sec=1.0, elapsed_ratio=0.1, retention_before=0.9, retention_after=0.8,
            drop_magnitude=0.1, cut_index=0, speaker="s", subtitle_text="t", emotion="e"
        )
    )
    assert len(r2.dropoff_points) == 0

    u1 = UploadResult(video_id="u1", url="url1", status="ok")
    u2 = UploadResult(video_id="u2", url="url2", status="ok")
    u1.raw_response["key"] = "value"
    assert "key" not in u2.raw_response


# ==============================================================================
# 4. Import Side Effects & Purity (Subprocess Isolation)
# ==============================================================================

def test_protocol_issubclass_checks():
    """Verify issubclass works with @runtime_checkable protocols."""
    assert issubclass(DummyPublisherComplete, VideoPublisher)
    assert not issubclass(DummyPublisherMissingThumbnail, VideoPublisher)
    assert not issubclass(DummyPublisherMissingVideo, VideoPublisher)

    assert issubclass(DummyAnalyticsComplete, VideoAnalyticsProvider)
    assert not issubclass(DummyAnalyticsMissingMethod, VideoAnalyticsProvider)


def test_progress_callback_callable_class():
    """Verify that a callable class instance can act as ProgressCallback."""
    class CallableTracker:
        def __init__(self) -> None:
            self.events: List[Tuple[float, int, int]] = []

        def __call__(self, ratio: float, uploaded: int, total: int) -> None:
            self.events.append((ratio, uploaded, total))

    tracker = CallableTracker()
    # Large 4GB+ upload handling
    four_gb = 4 * 1024 * 1024 * 1024
    two_gb = 2 * 1024 * 1024 * 1024
    tracker(0.5, two_gb, four_gb)

    assert len(tracker.events) == 1
    assert tracker.events[0] == (0.5, two_gb, four_gb)


def test_domain_models_edge_cases():
    """Stress test domain models with boundary values, Unicode, and empty collections."""
    # Unicode and Japanese text handling in all fields
    rdp = RetentionDropoffPoint(
        timestamp_sec=0.0,
        elapsed_ratio=0.0,
        retention_before=1.0,
        retention_after=0.85,
        drop_magnitude=0.15,
        cut_index=0,
        speaker="東北ずん子（CV:佐藤聡美）",
        subtitle_text="「ずんだ餅を食べるのだ！✨」",
        emotion="excited",
        broll_image="assets/slide_zunda_01.png",
        issue_type="RAPID_RETENTION_CLIFF",
        recommendation="オープニングフックを1.5秒短縮してください。",
    )
    d = asdict(rdp)
    serialized = json.dumps(d, ensure_ascii=False)
    deserialized = json.loads(serialized)
    assert deserialized["speaker"] == "東北ずん子（CV:佐藤聡美）"
    assert deserialized["subtitle_text"] == "「ずんだ餅を食べるのだ！✨」"

    # Extreme numeric values (e.g. 0 duration, empty lists)
    empty_report = VideoRetentionReport(
        video_id="",
        video_title="",
        total_duration_sec=0.0,
        total_cuts=0,
        retention_score=0.0,
        average_view_percentage=0.0,
    )
    rep_dict = asdict(empty_report)
    assert rep_dict["dropoff_points"] == []
    assert rep_dict["cut_metrics"] == []
    assert rep_dict["editorial_recommendations"] == []
    assert rep_dict["summary_verdict"] == "NOMINAL"
    assert json.loads(json.dumps(rep_dict)) == rep_dict


def test_import_purity_in_clean_subprocess():
    """Run an isolated Python process that imports veraxi_ymmp.ir and veraxi_ymmp.ports and asserts no side effects."""
    verification_code = """
import sys
import os

# Snapshot initial state
initial_cwd_files = set(os.listdir('.'))

from veraxi_ymmp.ir import (
    RetentionPoint, RetentionDropoffPoint, CutRetentionMetric,
    VideoRetentionReport, VideoPublishMetadata, UploadResult
)
from veraxi_ymmp.ports import (
    VideoPublisher, VideoAnalyticsProvider, ProgressCallback
)

# 1. Check no external Google client or YouTube adapter libraries were loaded
prohibited_submodules = [
    'google', 'googleapiclient', 'google_auth_oauthlib',
    'veraxi_ymmp.youtube_adapter'
]
loaded_prohibited = [m for m in prohibited_submodules if m in sys.modules]
if loaded_prohibited:
    print(f"FAIL_LOADED_PROHIBITED: {loaded_prohibited}")
    sys.exit(1)

# 2. Check no files created in current directory
post_cwd_files = set(os.listdir('.'))
if post_cwd_files != initial_cwd_files:
    print(f"FAIL_FILES_CREATED: {post_cwd_files - initial_cwd_files}")
    sys.exit(2)

print("PURITY_PASSED")
"""
    result = subprocess.run(
        [sys.executable, "-c", verification_code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0, f"Import purity failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert "PURITY_PASSED" in result.stdout
