"""Video file validation utility.

Checks existence, format (.mp4), vertical 9:16 aspect ratio, and video metadata.
"""

from __future__ import annotations

import os
import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = None


@dataclass
class VideoInfo:
    """Metadata container for a validated video file."""
    path: Path
    width: int
    height: int
    aspect_ratio: float
    duration_seconds: float
    fps: float
    is_vertical: bool
    is_9_16: bool
    size_bytes: int

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


class VideoValidationError(Exception):
    """Raised when video file fails format, existence, or aspect ratio validation."""
    pass


def probe_video_with_ffmpeg(video_path: Path) -> dict:
    """Probes video metadata using imageio-ffmpeg bundled binary."""
    if not FFMPEG_EXE:
        raise VideoValidationError("FFmpeg binary not available for video probing.")

    # Run ffmpeg -i <path> and parse output streams
    cmd = [
        FFMPEG_EXE,
        "-hide_banner",
        "-i",
        str(video_path),
    ]

    # ffmpeg writes file info to stderr
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    stderr = process.stderr

    # Fallback to OpenCV if available, or regex parse ffmpeg output
    import re

    width = 0
    height = 0
    fps = 0.0
    duration = 0.0

    # Parse duration: "Duration: 00:00:15.24"
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", stderr)
    if duration_match:
        hours = float(duration_match.group(1))
        minutes = float(duration_match.group(2))
        seconds = float(duration_match.group(3))
        duration = hours * 3600 + minutes * 60 + seconds

    # Parse video stream: Stream #0:0: Video: ... 1080x1920 [SAR 1:1 DAR 9:16], ... 30 fps
    video_stream_match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", stderr)
    if video_stream_match:
        width = int(video_stream_match.group(1))
        height = int(video_stream_match.group(2))

    fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", stderr)
    if fps_match:
        fps = float(fps_match.group(1))

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
    }


def probe_video_with_cv2(video_path: Path) -> dict:
    """Alternative probe using cv2 if installed."""
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise VideoValidationError(f"Could not open video file: {video_path}")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = (frame_count / fps) if fps > 0 else 0.0
        cap.release()

        return {
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration,
        }
    except ImportError:
        return {}


def validate_video(
    file_path: str | Path,
    strict_9_16: bool = True,
    tolerance: float = 0.05,
    max_duration_seconds: float = 180.0,
) -> VideoInfo:
    """Validates video file existence, format (.mp4), dimensions, and 9:16 aspect ratio.

    Args:
        file_path: Path to the video file.
        strict_9_16: If True, raises VideoValidationError when aspect ratio differs from 9:16.
        tolerance: Allowed deviation from target aspect ratio (9/16 = 0.5625).
        max_duration_seconds: Maximum allowed duration (Shorts/Reels typically 60s - 90s, TikTok up to 10m).

    Returns:
        VideoInfo dataclass containing verified metadata.

    Raises:
        VideoValidationError: When validation checks fail.
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise VideoValidationError(f"Videodatei existiert nicht: {path}")

    if not path.is_file():
        raise VideoValidationError(f"Pfad ist keine Datei: {path}")

    if path.stat().st_size == 0:
        raise VideoValidationError(f"Videodatei ist leer (0 Bytes): {path}")

    # Check extension
    if path.suffix.lower() != ".mp4":
        raise VideoValidationError(
            f"Ungültiges Dateiformat: '{path.suffix}'. Nur .mp4-Dateien werden unterstützt."
        )

    # Probe dimensions
    metadata = {}
    if FFMPEG_EXE:
        try:
            metadata = probe_video_with_ffmpeg(path)
        except Exception as e:
            logger.warning(f"FFmpeg probing failed: {e}. Trying cv2 fallback...")

    if not metadata or metadata.get("width", 0) == 0:
        cv_meta = probe_video_with_cv2(path)
        if cv_meta and cv_meta.get("width", 0) > 0:
            metadata = cv_meta

    width = metadata.get("width", 0)
    height = metadata.get("height", 0)
    fps = metadata.get("fps", 0.0)
    duration = metadata.get("duration", 0.0)

    if width == 0 or height == 0:
        raise VideoValidationError(
            f"Konnte Videodimensionen nicht auslesen für: {path.name}"
        )

    aspect_ratio = width / height
    target_ratio = 9.0 / 16.0  # 0.5625
    is_vertical = height > width
    is_9_16 = abs(aspect_ratio - target_ratio) <= tolerance

    if not is_vertical:
        error_msg = (
            f"Video ist horizontal ({width}x{height}, Ratio: {aspect_ratio:.2f})! "
            "Shorts, Reels und TikTok erfordern ein vertikales Video (Hochformat)."
        )
        if strict_9_16:
            raise VideoValidationError(error_msg)
        logger.warning(error_msg)

    if not is_9_16:
        error_msg = (
            f"Video-Seitenverhältnis ({width}x{height} = {aspect_ratio:.3f}) weicht vom 9:16-Standard "
            f"({target_ratio:.3f}) ab (Toleranz ±{tolerance})."
        )
        if strict_9_16:
            raise VideoValidationError(error_msg)
        logger.warning(error_msg)

    if duration > max_duration_seconds:
        logger.warning(
            f"Videolänge ({duration:.1f}s) überschreitet {max_duration_seconds}s. "
            "YouTube Shorts unterstützt max. 60s (bzw. bis zu 3min für bestimmte Formate)."
        )

    info = VideoInfo(
        path=path,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        duration_seconds=duration,
        fps=fps,
        is_vertical=is_vertical,
        is_9_16=is_9_16,
        size_bytes=path.stat().st_size,
    )

    logger.info(
        f"Video erfolgreich validiert: {path.name} "
        f"({width}x{height}, {fps:.1f}fps, {duration:.1f}s, {info.size_mb:.2f} MB)"
    )
    return info
