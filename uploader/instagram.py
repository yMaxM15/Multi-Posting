"""Instagram Reels Uploader using Meta Graph API v19+ and S3/R2 temporary hosting."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional
import requests
from loguru import logger

from config import settings
from uploader.base import BaseUploader, UploadResult
from utils.storage import StorageManager


class InstagramReelsUploader(BaseUploader):
    """Handles publishing vertical videos to Instagram Reels via Meta Graph API."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        account_id: Optional[str] = None,
        api_version: Optional[str] = None,
        storage_manager: Optional[StorageManager] = None,
    ) -> None:
        super().__init__(name="Instagram Reels")
        cfg = settings.instagram
        self.access_token = access_token or cfg.access_token
        self.account_id = account_id or cfg.account_id
        self.api_version = api_version or cfg.graph_api_version
        self.storage = storage_manager or StorageManager()
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    def is_configured(self) -> bool:
        return settings.instagram.is_configured() and settings.storage.is_configured()

    def _format_caption(self, title: str, description: str, tags: Optional[list[str]] = None) -> str:
        """Formats the Instagram caption with title, description, and hashtags."""
        parts = []
        if title:
            parts.append(title.strip())
        if description and description.strip() != title.strip():
            parts.append(description.strip())
        if tags:
            tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
            parts.append(tag_str)
        return "\n\n".join(parts)

    def _create_media_container(self, video_url: str, caption: str) -> str:
        """Creates an Instagram Reels container via Meta Graph API."""
        url = f"{self.base_url}/{self.account_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": self.access_token,
        }

        logger.info(f"[Instagram] Erstelle Reels-Container bei Meta Graph API ({url})...")
        response = requests.post(url, data=payload, timeout=30)
        data = response.json()

        if response.status_code != 200 or "id" not in data:
            error_details = data.get("error", {})
            error_msg = error_details.get("message", response.text)
            error_code = error_details.get("code", "unknown")
            error_subcode = error_details.get("error_subcode", "none")
            raise RuntimeError(
                f"Container-Erstellung fehlgeschlagen (Code {error_code}/{error_subcode}): {error_msg}"
            )

        container_id = data["id"]
        logger.info(f"[Instagram] Media-Container erfolgreich erstellt: {container_id}")
        return container_id

    def _poll_container_status(self, container_id: str, max_wait_seconds: int = 300, poll_interval: int = 5) -> None:
        """Polls container until status is FINISHED or raises on ERROR."""
        url = f"{self.base_url}/{container_id}"
        params = {
            "fields": "status_code,status",
            "access_token": self.access_token,
        }

        start_time = time.time()
        logger.info(f"[Instagram] Warte auf Video-Verarbeitung für Container {container_id}...")

        while time.time() - start_time < max_wait_seconds:
            response = requests.get(url, params=params, timeout=15)
            data = response.json()

            if response.status_code != 200:
                logger.warning(f"[Instagram] Statusabfrage HTTP {response.status_code}: {response.text}")
            else:
                status_code = data.get("status_code", "")
                logger.info(f"[Instagram] Container {container_id} Status: {status_code}")

                if status_code == "FINISHED":
                    logger.success(f"[Instagram] Container-Verarbeitung abgeschlossen ({status_code})!")
                    return
                elif status_code in ("ERROR", "EXPIRED"):
                    raise RuntimeError(
                        f"Instagram Video-Verarbeitung fehlgeschlagen mit Status: {status_code}. "
                        f"Details: {data.get('status', 'Keine Details')}"
                    )

            time.sleep(poll_interval)

        raise TimeoutError(
            f"Instagram Container-Verarbeitung überschritt Zeitlimit von {max_wait_seconds} Sekunden."
        )

    def _publish_media(self, container_id: str) -> str:
        """Publishes the processed Instagram Reels container."""
        url = f"{self.base_url}/{self.account_id}/media_publish"
        payload = {
            "creation_id": container_id,
            "access_token": self.access_token,
        }

        logger.info(f"[Instagram] Veröffentliche Container {container_id}...")
        response = requests.post(url, data=payload, timeout=30)
        data = response.json()

        if response.status_code != 200 or "id" not in data:
            error_msg = data.get("error", {}).get("message", response.text)
            raise RuntimeError(f"Veröffentlichung fehlgeschlagen: {error_msg}")

        published_media_id = data["id"]
        logger.success(f"[Instagram] Reels erfolgreich publiziert! Media-ID: {published_media_id}")
        return published_media_id

    def _get_permalink(self, media_id: str) -> Optional[str]:
        """Fetches post permalink if available."""
        url = f"{self.base_url}/{media_id}"
        params = {
            "fields": "permalink",
            "access_token": self.access_token,
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                return res.json().get("permalink")
        except Exception:
            pass
        return None

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> UploadResult:
        """Executes the full Instagram Reels publish flow with temporary cloud storage."""
        if not settings.instagram.is_configured():
            return UploadResult(
                platform=self.name,
                success=False,
                message="Instagram ist nicht konfiguriert (INSTAGRAM_ACCESS_TOKEN oder ACCOUNT_ID fehlt).",
                error="Missing Instagram credentials",
            )
        if not settings.storage.is_configured():
            return UploadResult(
                platform=self.name,
                success=False,
                message="Cloud Storage (S3/R2) ist nicht konfiguriert für Instagram Video-Hosting.",
                error="Missing S3/R2 storage credentials",
            )

        caption = self._format_caption(title, description, tags)
        s3_object_key = None
        temp_video_url = None

        try:
            # 1. Upload to temporary cloud storage
            temp_video_url, s3_object_key = self.storage.upload_file(
                video_path, remote_prefix="temp_reels"
            )

            # 2. Create Instagram Reels container
            container_id = self._create_media_container(temp_video_url, caption)

            # 3. Poll container until FINISHED
            self._poll_container_status(container_id)

            # 4. Publish Reels
            published_media_id = self._publish_media(container_id)

            # 5. Get permalink
            permalink = self._get_permalink(published_media_id)

            return UploadResult(
                platform=self.name,
                success=True,
                message="Erfolgreich auf Instagram Reels veröffentlicht!",
                video_id=published_media_id,
                url=permalink or f"https://www.instagram.com/",
                extra={
                    "container_id": container_id,
                    "permalink": permalink,
                    "caption": caption,
                },
            )
        finally:
            # 5. Clean up temporary cloud file
            if s3_object_key:
                try:
                    self.storage.delete_file(s3_object_key)
                except Exception as del_err:
                    logger.warning(f"[Instagram] Konnte temporäre S3-Datei nicht löschen: {del_err}")
