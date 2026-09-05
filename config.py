"""Configuration module for Multi-Posting Automation Tool.

Loads environment variables from .env file and provides structured,
validated settings for all platforms and storage backends.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file from project root
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


class StorageConfig:
    """Configuration for Cloud Storage (AWS S3 or Cloudflare R2)."""

    def __init__(self) -> None:
        self.provider: str = os.getenv("STORAGE_PROVIDER", "s3").lower()
        self.bucket_name: str = os.getenv("S3_BUCKET_NAME", "")
        self.access_key_id: str = os.getenv("S3_ACCESS_KEY_ID", "")
        self.secret_access_key: str = os.getenv("S3_SECRET_ACCESS_KEY", "")
        self.region_name: str = os.getenv("S3_REGION_NAME", "eu-central-1")
        self.endpoint_url: Optional[str] = os.getenv("S3_ENDPOINT_URL") or None
        self.public_base_url: Optional[str] = os.getenv("S3_PUBLIC_BASE_URL") or None
        self.presigned_expiry: int = int(os.getenv("S3_PRESIGNED_EXPIRY", "3600"))

    def is_configured(self) -> bool:
        return bool(self.bucket_name and self.access_key_id and self.secret_access_key)


class YouTubeConfig:
    """Configuration for YouTube Data API v3."""

    def __init__(self) -> None:
        secrets_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
        self.client_secrets_file: Path = Path(secrets_file)
        if not self.client_secrets_file.is_absolute():
            self.client_secrets_file = Path(__file__).resolve().parent / secrets_file

        token_file = os.getenv("YOUTUBE_TOKEN_FILE", "token.json")
        self.token_file: Path = Path(token_file)
        if not self.token_file.is_absolute():
            self.token_file = Path(__file__).resolve().parent / token_file

        self.privacy_status: str = os.getenv("YOUTUBE_PRIVACY_STATUS", "public")
        self.category_id: str = os.getenv("YOUTUBE_CATEGORY_ID", "22")

    def is_configured(self) -> bool:
        return self.client_secrets_file.exists() or self.token_file.exists()


class InstagramConfig:
    """Configuration for Instagram Graph API."""

    def __init__(self) -> None:
        self.access_token: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.account_id: str = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
        self.graph_api_version: str = os.getenv("GRAPH_API_VERSION", "v19.0")

    def is_configured(self) -> bool:
        return bool(self.access_token and self.account_id)


class TikTokConfig:
    """Configuration for TikTok Playwright Automation."""

    def __init__(self) -> None:
        session_dir = os.getenv("TIKTOK_SESSION_DIR", "./tiktok_session")
        self.session_dir: Path = Path(session_dir)
        if not self.session_dir.is_absolute():
            self.session_dir = Path(__file__).resolve().parent / session_dir

        self.headless: bool = os.getenv("TIKTOK_HEADLESS", "false").lower() in ("true", "1", "yes")
        self.timeout_ms: int = int(os.getenv("TIKTOK_TIMEOUT_MS", "120000"))

    def is_configured(self) -> bool:
        from uploader.tiktok import is_tiktok_authenticated
        return is_tiktok_authenticated(self.session_dir)


class Settings:
    """Global configuration aggregator."""

    def __init__(self) -> None:
        self.storage = StorageConfig()
        self.youtube = YouTubeConfig()
        self.instagram = InstagramConfig()
        self.tiktok = TikTokConfig()

    def get_status_summary(self) -> dict[str, bool]:
        """Returns readiness status for all platforms and services."""
        return {
            "Storage (S3/R2)": self.storage.is_configured(),
            "YouTube Shorts": self.youtube.is_configured(),
            "Instagram Reels": self.instagram.is_configured() and self.storage.is_configured(),
            "TikTok": self.tiktok.is_configured(),
        }


settings = Settings()
