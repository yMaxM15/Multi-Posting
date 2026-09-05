"""YouTube Shorts Uploader using Google Data API v3 and Resumable Upload."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional
from loguru import logger
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config import settings
from uploader.base import BaseUploader, UploadResult
from utils.auth import get_youtube_service


class YouTubeShortsUploader(BaseUploader):
    """Handles uploading short vertical videos to YouTube Shorts."""

    def __init__(
        self,
        privacy_status: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> None:
        super().__init__(name="YouTube Shorts")
        cfg = settings.youtube
        self.privacy_status = privacy_status or cfg.privacy_status
        self.category_id = category_id or cfg.category_id

    def is_configured(self) -> bool:
        return settings.youtube.is_configured()

    def _ensure_shorts_hashtag(self, title: str, description: str) -> tuple[str, str]:
        """Ensures that #Shorts is present in either the title or description."""
        title_clean = title.strip()
        desc_clean = description.strip()

        # YouTube recommends having #Shorts in title or description
        if "#shorts" not in title_clean.lower():
            # If title is not too long (max 100 chars on YouTube)
            if len(title_clean) + len(" #Shorts") <= 100:
                title_clean = f"{title_clean} #Shorts"
            elif "#shorts" not in desc_clean.lower():
                desc_clean = f"{desc_clean}\n\n#Shorts"

        if "#shorts" not in desc_clean.lower():
            desc_clean = f"{desc_clean}\n\n#Shorts"

        return title_clean, desc_clean

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> UploadResult:
        """Uploads video to YouTube Shorts using resumable upload chunks."""
        if not self.is_configured():
            return UploadResult(
                platform=self.name,
                success=False,
                message="YouTube ist nicht konfiguriert (client_secrets.json fehlt).",
                error="Missing client_secrets.json",
            )

        # 1. Prepare metadata
        final_title, final_description = self._ensure_shorts_hashtag(title, description)
        all_tags = list(tags or [])
        if "Shorts" not in all_tags and "shorts" not in all_tags:
            all_tags.append("Shorts")

        privacy = kwargs.get("privacy_status", self.privacy_status)

        # 2. Get authenticated service
        service = get_youtube_service()

        body = {
            "snippet": {
                "title": final_title,
                "description": final_description,
                "tags": all_tags,
                "categoryId": str(self.category_id),
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        # 3. Setup resumable media upload (4 MB chunks)
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=4 * 1024 * 1024,
            resumable=True,
        )

        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        logger.info(
            f"[YouTube] Starte Resumable Upload für '{final_title}' "
            f"(Status: {privacy}, Tags: {len(all_tags)})..."
        )

        response = None
        retry_count = 0
        max_retries = 5

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    percent = int(status.progress() * 100)
                    logger.info(f"[YouTube] Upload-Fortschritt: {percent}%")
            except HttpError as http_err:
                if http_err.resp.status in [500, 502, 503, 504]:
                    retry_count += 1
                    if retry_count > max_retries:
                        raise
                    wait_sec = 2 ** retry_count
                    logger.warning(
                        f"[YouTube] Temporärer Serverfehler ({http_err.resp.status}). "
                        f"Warte {wait_sec}s (Versuch {retry_count}/{max_retries})..."
                    )
                    time.sleep(wait_sec)
                else:
                    raise

        video_id = response.get("id")
        shorts_url = f"https://www.youtube.com/shorts/{video_id}"
        watch_url = f"https://www.youtube.com/watch?v={video_id}"

        logger.success(f"[YouTube] Video erfolgreich hochgeladen! Video-ID: {video_id}")

        return UploadResult(
            platform=self.name,
            success=True,
            message=f"Erfolgreich auf YouTube Shorts veröffentlicht (Status: {privacy})",
            video_id=video_id,
            url=shorts_url,
            extra={
                "watch_url": watch_url,
                "title": final_title,
                "privacy": privacy,
                "tags": all_tags,
            },
        )
