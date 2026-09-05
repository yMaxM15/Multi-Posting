"""Base classes and data structures for social media uploaders."""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from loguru import logger


@dataclass
class UploadResult:
    """Standardized result returned by all platform uploaders."""
    platform: str
    success: bool
    message: str
    video_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "success": self.success,
            "message": self.message,
            "video_id": self.video_id,
            "url": self.url,
            "error": self.error,
            "execution_time": round(self.execution_time, 2),
            "extra": self.extra,
        }


class BaseUploader(abc.ABC):
    """Abstract base class for all platform uploaders."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Returns True if all required credentials and configurations exist."""
        pass

    @abc.abstractmethod
    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> UploadResult:
        """Publishes the video to the respective platform.

        Args:
            video_path: Path to the validated local MP4 video file.
            title: Title for the post / short.
            description: Description / caption for the post.
            tags: List of hashtags or tags.
            **kwargs: Platform-specific options.

        Returns:
            UploadResult dataclass.
        """
        pass

    def run_safe(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> UploadResult:
        """Wraps upload() with timing, exception logging, and safety guards."""
        start_time = time.time()
        logger.info(f"[{self.name}] Starte Upload-Prozess für: {video_path.name}")

        try:
            result = self.upload(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags or [],
                **kwargs,
            )
            result.execution_time = time.time() - start_time
            if result.success:
                logger.success(
                    f"[{self.name}] Upload erfolgreich in {result.execution_time:.2f}s! "
                    f"URL: {result.url or 'N/A'}"
                )
            else:
                logger.error(
                    f"[{self.name}] Upload fehlgeschlagen: {result.error or result.message}"
                )
            return result
        except Exception as exc:
            duration = time.time() - start_time
            logger.exception(f"[{self.name}] Unerwarteter Fehler beim Upload: {exc}")
            return UploadResult(
                platform=self.name,
                success=False,
                message=f"Fehler: {exc}",
                error=str(exc),
                execution_time=duration,
            )
