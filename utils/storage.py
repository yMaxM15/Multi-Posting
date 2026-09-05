"""Storage utility for temporary video hosting on AWS S3 or Cloudflare R2.

Instagram Graph API requires a publicly accessible HTTPS URL to fetch video content.
This module manages upload, pre-signed / public URL generation, and cleanup.
"""

from __future__ import annotations

import os
import uuid
import mimetypes
from pathlib import Path
from typing import Optional
from loguru import logger
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config import settings


class StorageManager:
    """Handles S3/R2 uploads, signed URL generation, and cleanup."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        public_base_url: Optional[str] = None,
        presigned_expiry: Optional[int] = None,
    ) -> None:
        cfg = settings.storage
        self.bucket_name = bucket_name or cfg.bucket_name
        self.access_key_id = access_key_id or cfg.access_key_id
        self.secret_access_key = secret_access_key or cfg.secret_access_key
        self.region_name = region_name or cfg.region_name
        self.endpoint_url = endpoint_url or cfg.endpoint_url
        self.public_base_url = (public_base_url or cfg.public_base_url or "").rstrip("/")
        self.presigned_expiry = presigned_expiry or cfg.presigned_expiry

        self._client: Optional[boto3.client] = None

    @property
    def client(self):
        """Lazy initialization of boto3 S3 client with standard signature v4."""
        if self._client is None:
            if not self.bucket_name or not self.access_key_id or not self.secret_access_key:
                raise ValueError(
                    "S3/R2 Storage credentials are not fully configured in .env! "
                    "Please check S3_BUCKET_NAME, S3_ACCESS_KEY_ID, and S3_SECRET_ACCESS_KEY."
                )

            s3_config = Config(
                signature_version="s3v4",
                retries={"max_attempts": 5, "mode": "standard"},
            )

            kwargs = {
                "service_name": "s3",
                "aws_access_key_id": self.access_key_id,
                "aws_secret_access_key": self.secret_access_key,
                "region_name": self.region_name,
                "config": s3_config,
            }
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url

            self._client = boto3.client(**kwargs)
        return self._client

    def upload_file(
        self,
        local_path: str | Path,
        remote_prefix: str = "temp_reels_upload",
    ) -> tuple[str, str]:
        """Uploads a local video file to S3/R2.

        Args:
            local_path: Path to the local file to upload.
            remote_prefix: Folder prefix in the bucket.

        Returns:
            Tuple of (public_or_presigned_url, s3_object_key).
        """
        path = Path(local_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden für Cloud-Upload: {path}")

        # Unique object key with uuid to prevent collisions
        file_ext = path.suffix or ".mp4"
        object_key = f"{remote_prefix}/{uuid.uuid4().hex}{file_ext}"

        content_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
        file_size_mb = path.stat().st_size / (1024 * 1024)

        logger.info(
            f"Lade Video '{path.name}' ({file_size_mb:.2f} MB) in Bucket '{self.bucket_name}' "
            f"als '{object_key}' hoch..."
        )

        try:
            extra_args = {"ContentType": content_type}
            self.client.upload_file(
                Filename=str(path),
                Bucket=self.bucket_name,
                Key=object_key,
                ExtraArgs=extra_args,
            )
            logger.success(f"Upload in Cloud-Storage erfolgreich: {object_key}")
        except ClientError as e:
            logger.error(f"Fehler beim S3/R2 Upload: {e}")
            raise

        # Generate accessible URL for Meta Graph API
        download_url = self.get_file_url(object_key)
        return download_url, object_key

    def get_file_url(self, object_key: str) -> str:
        """Returns either public base URL or a pre-signed HTTPS GET URL."""
        if self.public_base_url:
            return f"{self.public_base_url}/{object_key}"

        # Generate pre-signed URL
        try:
            url = self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": object_key,
                },
                ExpiresIn=self.presigned_expiry,
            )
            return url
        except ClientError as e:
            logger.error(f"Konnte Pre-Signed URL nicht generieren: {e}")
            raise

    def delete_file(self, object_key: str) -> bool:
        """Deletes a temporary file from the S3/R2 bucket."""
        if not object_key:
            return False

        logger.info(f"Lösche temporäre Datei aus Cloud-Storage: {object_key}")
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=object_key)
            logger.success(f"Temporäre Cloud-Datei erfolgreich gelöscht: {object_key}")
            return True
        except ClientError as e:
            logger.warning(f"Konnte temporäre S3-Datei nicht löschen ({object_key}): {e}")
            return False
