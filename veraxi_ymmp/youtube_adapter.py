"""YouTube Data API v3 and YouTube Analytics API v2 Adapter.

Provides:
- YouTubeAdapter: Production adapter implementing VideoPublisher and VideoAnalyticsProvider
  with resumable chunked video upload, exponential backoff retry on HTTP 5xx,
  thumbnail upload with 2MB validation, and OAuth2 token discovery.
- MockYouTubeAdapter: Pure standard library mock adapter implementing VideoPublisher
  and VideoAnalyticsProvider for 100% offline testing with deterministic chunk simulation,
  failure injection, and synthetic retention curves.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logging import logger
from .ports import (
    ProgressCallback,
    RetentionDropoffPoint,
    UploadResult,
    VideoPublishMetadata,
    VideoRetentionReport,
)

# Constants & Defaults
CHUNK_SIZE_DEFAULT: int = 8 * 1024 * 1024  # 8 MB (32 * 256 KB)
MOCK_CHUNK_SIZE_DEFAULT: int = 1 * 1024 * 1024  # 1 MB (4 * 256 KB)
CHUNK_MULTIPLE: int = 256 * 1024  # 256 KB YouTube required chunk multiple
THUMBNAIL_MAX_SIZE_BYTES: int = 2 * 1024 * 1024  # 2 MB YouTube thumbnail limit
MAX_RETRIES_DEFAULT: int = 5
BASE_RETRY_DELAY: float = 1.0
MAX_RETRY_DELAY: float = 60.0
RETRYABLE_STATUS_CODES: set[int] = {500, 502, 503, 504}

DEFAULT_RETENTION_CURVE: List[Tuple[float, float]] = [
    (0.00, 1.00),
    (0.05, 0.90),
    (0.10, 0.85),
    (0.20, 0.80),
    (0.30, 0.77),
    (0.40, 0.75),
    (0.45, 0.65),  # -0.10 drop at 45%
    (0.60, 0.60),
    (0.80, 0.52),
    (1.00, 0.40),
]


def _is_retryable_http_error(e: Exception) -> Tuple[bool, int]:
    """Check if an exception represents a retryable HTTP 5xx error."""
    status: Optional[int] = None
    if hasattr(e, "resp") and hasattr(e.resp, "status"):
        try:
            status = int(e.resp.status)
        except (ValueError, TypeError):
            pass
    elif hasattr(e, "status_code"):
        try:
            status = int(e.status_code)
        except (ValueError, TypeError):
            pass
    elif hasattr(e, "status"):
        try:
            status = int(e.status)
        except (ValueError, TypeError):
            pass

    if status is not None and status in RETRYABLE_STATUS_CODES:
        return True, status
    return False, status if status is not None else 0


class YouTubeAdapter:
    """Production YouTube Data API v3 and Analytics API v2 Adapter.

    Implements VideoPublisher and VideoAnalyticsProvider protocols with:
    - Lazy loading of googleapiclient and google.oauth2
    - Resumable chunked upload with exponential backoff on HTTP 5xx
    - Named keyword arguments for thumbnail upload with 2MB validation
    - Multi-stage OAuth2 / token discovery without hardcoded secrets
    """

    def __init__(
        self,
        credentials: Optional[Any] = None,
        token_path: Optional[Path] = None,
        client_secrets_path: Optional[Path] = None,
        chunk_size: int = CHUNK_SIZE_DEFAULT,
        max_retries: int = MAX_RETRIES_DEFAULT,
        base_retry_delay: float = BASE_RETRY_DELAY,
        max_retry_delay: float = MAX_RETRY_DELAY,
        youtube_service: Optional[Any] = None,
        analytics_service: Optional[Any] = None,
        media_file_upload_cls: Optional[Any] = None,
    ) -> None:
        if chunk_size <= 0 or chunk_size % CHUNK_MULTIPLE != 0:
            raise ValueError(
                f"chunk_size must be a positive integer multiple of 256 KB ({CHUNK_MULTIPLE} bytes), got {chunk_size}"
            )

        self.token_path = token_path
        self.client_secrets_path = client_secrets_path
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self._credentials = credentials
        self._youtube = youtube_service
        self._analytics = analytics_service
        self._media_file_upload_cls = media_file_upload_cls

    def _get_media_file_upload_cls(self) -> Any:
        """Get MediaFileUpload class lazily or raise informative ImportError."""
        if self._media_file_upload_cls is not None:
            return self._media_file_upload_cls
        try:
            from googleapiclient.http import MediaFileUpload
            return MediaFileUpload
        except ImportError as e:
            raise ImportError(
                "Google API client libraries are required to use YouTubeAdapter. "
                "Install them with: pip install google-api-python-client google-auth-oauthlib"
            ) from e

    def get_resolved_token_path(self) -> Optional[Path]:
        """Resolve token file path without importing external Google libraries."""
        if self.token_path and self.token_path.exists():
            return self.token_path

        env_path = os.getenv("VERAXI_YOUTUBE_TOKEN_PATH") or os.getenv("YOUTUBE_TOKEN_PATH")
        if env_path:
            p = Path(env_path)
            if p.exists():
                return p

        default_path = Path.home() / ".veraxi-ymmp" / "youtube_token.json"
        if default_path.exists():
            return default_path

        return None

    def _resolve_credentials(self) -> Any:
        """Resolve OAuth2 credentials following the priority chain."""
        if self._credentials is not None:
            return self._credentials

        try:
            from google.oauth2.credentials import Credentials
        except ImportError as e:
            raise ImportError(
                "Google auth libraries are required for YouTube authentication. "
                "Install them with: pip install google-api-python-client google-auth-oauthlib"
            ) from e

        # 1. Explicit token path
        if self.token_path and self.token_path.exists():
            self._credentials = Credentials.from_authorized_user_file(str(self.token_path))
            return self._credentials

        # 2. Environment variable token path
        env_token_path = os.getenv("VERAXI_YOUTUBE_TOKEN_PATH") or os.getenv("YOUTUBE_TOKEN_PATH")
        if env_token_path:
            p = Path(env_token_path)
            if p.exists():
                self._credentials = Credentials.from_authorized_user_file(str(p))
                return self._credentials

        # 3. Environment variable JSON string (for CI / headless containers)
        env_json = os.getenv("VERAXI_YOUTUBE_AUTHORIZED_USER_JSON")
        if env_json:
            user_info = json.loads(env_json)
            self._credentials = Credentials.from_authorized_user_info(user_info)
            return self._credentials

        # 4. Default user directory fallback
        default_home_token = Path.home() / ".veraxi-ymmp" / "youtube_token.json"
        if default_home_token.exists():
            self._credentials = Credentials.from_authorized_user_file(str(default_home_token))
            return self._credentials

        raise ValueError(
            "YouTube credentials not found. Provide credentials, token_path, "
            "or set VERAXI_YOUTUBE_TOKEN_PATH or VERAXI_YOUTUBE_AUTHORIZED_USER_JSON."
        )

    @property
    def youtube(self) -> Any:
        """Lazily instantiate YouTube Data API v3 service."""
        if self._youtube is None:
            try:
                from googleapiclient.discovery import build
            except ImportError as e:
                raise ImportError(
                    "Google API client libraries are required to use YouTubeAdapter. "
                    "Install them with: pip install google-api-python-client google-auth-oauthlib"
                ) from e
            creds = self._resolve_credentials()
            self._youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        return self._youtube

    @property
    def analytics(self) -> Any:
        """Lazily instantiate YouTube Analytics API v2 service."""
        if self._analytics is None:
            try:
                from googleapiclient.discovery import build
            except ImportError as e:
                raise ImportError(
                    "Google API client libraries are required to use YouTubeAdapter. "
                    "Install them with: pip install google-api-python-client google-auth-oauthlib"
                ) from e
            creds = self._resolve_credentials()
            self._analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        return self._analytics

    def upload_video(
        self,
        video_path: Path,
        metadata: VideoPublishMetadata,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UploadResult:
        """Upload a video with chunked resumable streaming and retry backoff."""
        if metadata.publish_at and metadata.privacy_status != "private":
            raise ValueError(
                f"YouTube requires privacy_status='private' when scheduling publish_at (got '{metadata.privacy_status}')."
            )

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        MediaFileUpload = self._get_media_file_upload_cls()

        total_bytes = video_path.stat().st_size
        body: Dict[str, Any] = {
            "snippet": {
                "title": metadata.title[:100],
                "description": metadata.description[:5000],
                "tags": metadata.tags,
                "categoryId": metadata.category_id,
                "defaultLanguage": metadata.language,
                "defaultAudioLanguage": metadata.language,
            },
            "status": {
                "privacyStatus": metadata.privacy_status,
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }
        if metadata.publish_at:
            body["status"]["publishAt"] = metadata.publish_at

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=self.chunk_size,
            resumable=True,
        )

        request = self.youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        retries = 0

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    retries = 0  # Reset retry counter on successful chunk transmission
                    if progress_callback:
                        progress_callback(status.progress(), status.resumable_progress, total_bytes)
            except Exception as e:
                retryable, status_code = _is_retryable_http_error(e)
                if retryable:
                    retries += 1
                    if retries > self.max_retries:
                        logger.error(
                            f"Max retries ({self.max_retries}) exceeded during video chunk upload."
                        )
                        raise
                    delay = min(
                        self.max_retry_delay,
                        (self.base_retry_delay * (2 ** (retries - 1))) + random.uniform(0.0, 1.0),
                    )
                    logger.warning(
                        f"HTTP {status_code} during chunk upload. Retrying in {delay:.2f}s "
                        f"(Attempt {retries}/{self.max_retries})..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Non-retryable upload error (HTTP {status_code}): {e}")
                    raise

        video_id = response.get("id", "") if isinstance(response, dict) else ""
        url = f"https://youtu.be/{video_id}" if video_id else ""

        thumb_uploaded = False
        if metadata.thumbnail_path and metadata.thumbnail_path.exists():
            thumb_uploaded = self.upload_thumbnail(video_id=video_id, thumbnail_path=metadata.thumbnail_path)

        return UploadResult(
            video_id=video_id,
            url=url,
            status="uploaded",
            thumbnail_uploaded=thumb_uploaded,
            bytes_uploaded=total_bytes,
            total_bytes=total_bytes,
            raw_response=response if isinstance(response, dict) else {},
        )

    def upload_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        """Upload custom thumbnail for a video with keyword arguments and 2MB validation."""
        if not thumbnail_path.exists():
            raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")

        file_size = thumbnail_path.stat().st_size
        if file_size > THUMBNAIL_MAX_SIZE_BYTES:
            raise ValueError(f"Thumbnail size ({file_size} bytes) exceeds YouTube 2MB limit.")

        MediaFileUpload = self._get_media_file_upload_cls()

        mime_type = "image/png" if thumbnail_path.suffix.lower() == ".png" else "image/jpeg"
        media = MediaFileUpload(str(thumbnail_path), mimetype=mime_type, resumable=False)

        request = self.youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        )
        request.execute()
        return True

    def upload_caption(
        self,
        video_id: str,
        caption_path: Path,
        language: str = "ja",
        name: str = "Japanese",
    ) -> bool:
        """Upload custom caption track (e.g. SRT) using YouTube Data API v3 captions().insert."""
        cap_path = Path(caption_path)
        if not cap_path.exists():
            raise FileNotFoundError(f"Caption file not found: {caption_path}")

        try:
            MediaFileUpload = self._get_media_file_upload_cls()
            media = MediaFileUpload(str(cap_path), mimetype="*/*", resumable=False)

            body: Dict[str, Any] = {
                "snippet": {
                    "videoId": video_id,
                    "language": language,
                    "name": name,
                    "isDraft": False,
                }
            }

            request = self.youtube.captions().insert(
                part="snippet",
                body=body,
                media_body=media,
            )
            response = request.execute()
            caption_id = response.get("id", "") if isinstance(response, dict) else ""
            logger.info(
                f"Uploaded caption '{name}' ({language}) for video {video_id}: caption_id={caption_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upload caption for video {video_id}: {e}")
            return False

    def fetch_retention_curve(
        self,
        video_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Tuple[float, float]]:
        """Fetch audience retention curve as list of (elapsed_ratio, watch_ratio) tuples."""
        request = self.analytics.reports().query(
            ids="channel==MINE",
            dimensions="elapsedVideoTimeRatio",
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            filters=f"video=={video_id}",
            startDate=start_date or "2020-01-01",
            endDate=end_date or "2030-12-31",
        )
        res = request.execute()
        rows = res.get("rows", [])
        return [(float(row[0]), float(row[1])) for row in rows]

    def get_retention_report(
        self,
        video_id: str,
        total_duration_sec: float,
        dropoff_threshold: float = 0.05,
    ) -> VideoRetentionReport:
        """Fetch retention data and build a basic VideoRetentionReport."""
        curve = self.fetch_retention_curve(video_id)
        dropoffs: List[RetentionDropoffPoint] = []
        prev = 1.0
        tot = 0.0

        for ratio, ret in curve:
            tot += ret
            drop = prev - ret
            if drop >= dropoff_threshold:
                dropoffs.append(
                    RetentionDropoffPoint(
                        timestamp_sec=ratio * total_duration_sec,
                        elapsed_ratio=ratio,
                        retention_before=prev,
                        retention_after=ret,
                        drop_magnitude=drop,
                        cut_index=0,
                        speaker="",
                        subtitle_text="",
                        emotion="normal",
                        broll_image=None,
                        issue_type="PACING_OR_FATIGUE",
                        recommendation="",
                    )
                )
            prev = ret

        avg = tot / len(curve) if curve else 0.0
        return VideoRetentionReport(
            video_id=video_id,
            video_title="",
            total_duration_sec=total_duration_sec,
            total_cuts=0,
            retention_score=avg,
            average_view_percentage=avg * 100.0,
            dropoff_threshold=dropoff_threshold,
            dropoff_points=dropoffs,
            cut_metrics=[],
            summary_verdict="NOMINAL" if not dropoffs else "RETENTION_DROPOFF_DETECTED",
            editorial_recommendations=[],
        )


class MockYouTubeAdapter:
    """Offline mock adapter implementing VideoPublisher and VideoAnalyticsProvider.

    Pure standard library + dataclasses. Requires zero Google client libraries or network access.
    Supports deterministic chunk streaming, progress callbacks, failure injection,
    and synthetic retention curves.
    """

    def __init__(
        self,
        fail_upload: bool = False,
        fail_at_chunk: Optional[int] = None,
        transient_failure_count: int = 0,
        http_error_code: int = 500,
        chunk_size: int = MOCK_CHUNK_SIZE_DEFAULT,
        max_retries: int = MAX_RETRIES_DEFAULT,
        simulated_retention_data: Optional[List[Tuple[float, float]]] = None,
        token_path: Optional[Path] = None,
    ) -> None:
        self.fail_upload = fail_upload
        self.fail_at_chunk = fail_at_chunk
        self.transient_failure_count = transient_failure_count
        self.http_error_code = http_error_code
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.simulated_retention_data = simulated_retention_data
        self.token_path = token_path

        # State tracking for test assertions
        self.uploaded_videos: Dict[str, Tuple[Path, VideoPublishMetadata]] = {}
        self.uploaded_thumbnails: Dict[str, Path] = {}
        self.uploaded_captions: List[Dict[str, Any]] = []
        self.recorded_chunks: List[Dict[str, Any]] = []
        self.retries_attempted: int = 0
        self.call_log: List[str] = []

    def upload_video(
        self,
        video_path: Path,
        metadata: VideoPublishMetadata,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UploadResult:
        """Simulate chunked video upload with error injection and progress reporting."""
        self.call_log.append(f"upload_video:{video_path.name}")

        if metadata.publish_at and metadata.privacy_status != "private":
            raise ValueError(
                f"YouTube requires privacy_status='private' when scheduling publish_at (got '{metadata.privacy_status}')."
            )

        if self.fail_upload:
            return UploadResult(
                video_id="",
                url="",
                status="failed",
                error_message=f"Simulated upload failure (HTTP {self.http_error_code})",
                bytes_uploaded=0,
                total_bytes=0,
            )

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size = video_path.stat().st_size

        if file_size == 0:
            # Handle 0-byte video edge case
            if self.fail_at_chunk == 1:
                self._handle_simulated_chunk_failure(1)
            self.recorded_chunks.append({
                "chunk": 1,
                "bytes_done": 0,
                "ratio": 1.0,
            })
            if progress_callback:
                progress_callback(1.0, 0, 0)
        else:
            num_chunks = max(1, (file_size + self.chunk_size - 1) // self.chunk_size)
            for chunk_idx in range(1, num_chunks + 1):
                if self.fail_at_chunk == chunk_idx:
                    self._handle_simulated_chunk_failure(chunk_idx)

                bytes_done = min(file_size, chunk_idx * self.chunk_size)
                ratio = bytes_done / file_size
                self.recorded_chunks.append({
                    "chunk": chunk_idx,
                    "bytes_done": bytes_done,
                    "ratio": ratio,
                })
                if progress_callback:
                    progress_callback(ratio, bytes_done, file_size)

        video_id = f"mock_{abs(hash(video_path.name)) % 1000000:06d}"
        self.uploaded_videos[video_id] = (video_path, metadata)

        thumb_uploaded = False
        if metadata.thumbnail_path and metadata.thumbnail_path.exists():
            thumb_uploaded = self.upload_thumbnail(video_id=video_id, thumbnail_path=metadata.thumbnail_path)

        return UploadResult(
            video_id=video_id,
            url=f"https://youtu.be/{video_id}",
            status="uploaded",
            thumbnail_uploaded=thumb_uploaded,
            bytes_uploaded=file_size,
            total_bytes=file_size,
            raw_response={"mock": True, "id": video_id},
        )

    def _handle_simulated_chunk_failure(self, chunk_idx: int) -> None:
        """Process failure injection rules for a specific chunk index."""
        if self.http_error_code not in RETRYABLE_STATUS_CODES:
            # Non-retryable error (e.g. 400 Bad Request): fail immediately with 0 retries
            raise RuntimeError(
                f"HTTP {self.http_error_code} Error: Non-retryable client error at chunk {chunk_idx}"
            )

        if self.transient_failure_count > 0:
            if self.transient_failure_count > self.max_retries:
                self.retries_attempted += self.max_retries
                raise RuntimeError(
                    f"HTTP {self.http_error_code} Error: Max retries ({self.max_retries}) exceeded at chunk {chunk_idx}"
                )
            # Simulated retry recovery
            self.retries_attempted += self.transient_failure_count
            self.transient_failure_count = 0
            logger.info(
                f"Simulated recovery after {self.retries_attempted} retries on chunk {chunk_idx}"
            )
        else:
            # Permanent 5xx failure without retries configured
            raise RuntimeError(
                f"HTTP {self.http_error_code} Error: Simulated permanent failure at chunk {chunk_idx}"
            )

    def upload_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        """Simulate thumbnail upload with 2MB validation."""
        self.call_log.append(f"upload_thumbnail:{video_id}")

        if not thumbnail_path.exists():
            raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")

        file_size = thumbnail_path.stat().st_size
        if file_size > THUMBNAIL_MAX_SIZE_BYTES:
            raise ValueError(f"Thumbnail size ({file_size} bytes) exceeds YouTube 2MB limit.")

        self.uploaded_thumbnails[video_id] = thumbnail_path
        return True

    def upload_caption(
        self,
        video_id: str,
        caption_path: Path,
        language: str = "ja",
        name: str = "Japanese",
    ) -> bool:
        """Simulate caption track upload for offline testing."""
        self.call_log.append(f"upload_caption:{video_id}")
        cap_path = Path(caption_path)
        if not cap_path.exists():
            raise FileNotFoundError(f"Caption file not found: {caption_path}")

        self.uploaded_captions.append(
            {
                "video_id": video_id,
                "caption_path": cap_path,
                "language": language,
                "name": name,
            }
        )
        logger.info(
            f"[Mock] Caption '{name}' ({language}) uploaded for video '{video_id}' from {caption_path}"
        )
        return True

    def fetch_retention_curve(
        self,
        video_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Tuple[float, float]]:
        """Fetch synthetic retention curve points."""
        self.call_log.append(f"fetch_retention_curve:{video_id}")
        if self.simulated_retention_data is not None:
            return list(self.simulated_retention_data)
        return list(DEFAULT_RETENTION_CURVE)

    def get_retention_report(
        self,
        video_id: str,
        total_duration_sec: float,
        dropoff_threshold: float = 0.05,
    ) -> VideoRetentionReport:
        """Generate a VideoRetentionReport from synthetic retention telemetry."""
        self.call_log.append(f"get_retention_report:{video_id}")
        curve = self.fetch_retention_curve(video_id)
        dropoffs: List[RetentionDropoffPoint] = []
        prev = 1.0
        tot = 0.0

        for ratio, ret in curve:
            tot += ret
            drop = prev - ret
            if drop >= dropoff_threshold:
                dropoffs.append(
                    RetentionDropoffPoint(
                        timestamp_sec=ratio * total_duration_sec,
                        elapsed_ratio=ratio,
                        retention_before=prev,
                        retention_after=ret,
                        drop_magnitude=drop,
                        cut_index=0,
                        speaker="",
                        subtitle_text="",
                        emotion="normal",
                        broll_image=None,
                        issue_type="PACING_OR_FATIGUE",
                        recommendation="",
                    )
                )
            prev = ret

        avg = tot / len(curve) if curve else 0.0
        return VideoRetentionReport(
            video_id=video_id,
            video_title="Mock Video",
            total_duration_sec=total_duration_sec,
            total_cuts=0,
            retention_score=avg,
            average_view_percentage=avg * 100.0,
            dropoff_threshold=dropoff_threshold,
            dropoff_points=dropoffs,
            cut_metrics=[],
            summary_verdict="NOMINAL" if not dropoffs else "RETENTION_DROPOFF_DETECTED",
            editorial_recommendations=[],
        )


__all__ = [
    "CHUNK_SIZE_DEFAULT",
    "MOCK_CHUNK_SIZE_DEFAULT",
    "CHUNK_MULTIPLE",
    "THUMBNAIL_MAX_SIZE_BYTES",
    "MAX_RETRIES_DEFAULT",
    "BASE_RETRY_DELAY",
    "MAX_RETRY_DELAY",
    "RETRYABLE_STATUS_CODES",
    "DEFAULT_RETENTION_CURVE",
    "YouTubeAdapter",
    "MockYouTubeAdapter",
]
