"""Authentication and Session Management utility.

Handles OAuth2 tokens for YouTube Data API, verifies Meta Graph API tokens,
and provides interactive login utilities for TikTok Playwright session cookies.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
from loguru import logger
import requests

from config import settings

# YouTube Scopes
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def get_youtube_service(
    client_secrets_file: Optional[Path] = None,
    token_file: Optional[Path] = None,
) -> Any:
    """Authenticates and returns a YouTube Data API v3 service resource.

    Uses stored credentials in token_file (token.json) if available and valid.
    Otherwise, starts local OAuth2 web flow using client_secrets_file (client_secrets.json).
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    cfg = settings.youtube
    secrets_path = client_secrets_file or cfg.client_secrets_file
    token_path = token_file or cfg.token_file

    creds = None

    # 1. Try loading cached token
    if token_path.exists():
        logger.info(f"Lade bestehendes YouTube-Token aus: {token_path}")
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)
        except Exception as e:
            logger.warning(f"Konnte token.json nicht laden: {e}. Starte Neu-Authentifizierung.")
            creds = None

    # 2. Refresh or trigger OAuth flow if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("YouTube-Token abgelaufen. Erneuere Token mit Refresh-Token...")
            try:
                creds.refresh(Request())
                logger.success("YouTube-Token erfolgreich aktualisiert.")
            except Exception as e:
                logger.warning(f"Token-Refresh fehlgeschlagen: {e}. Starte vollen OAuth-Flow.")
                creds = None

        if not creds:
            if not secrets_path.exists():
                raise FileNotFoundError(
                    f"YouTube client_secrets.json nicht gefunden unter: {secrets_path}\n"
                    "Bitte erstelle ein OAuth 2.0 Client-Secret im Google Cloud Console "
                    "und lege die JSON-Datei dort ab."
                )

            logger.info("Starte lokalen Browser für YouTube OAuth 2.0 Authentifizierung...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secrets_path),
                scopes=YOUTUBE_SCOPES,
            )
            creds = flow.run_local_server(
                port=0,
                prompt="consent",
                authorization_prompt_message="Bitte autorisiere die App im Browser...",
                success_message="Authentifizierung erfolgreich! Du kannst diesen Tab schliessen.",
            )

        # Save the valid token locally
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
        logger.success(f"YouTube-Token gespeichert unter: {token_path}")

    return build("youtube", "v3", credentials=creds)


def verify_instagram_credentials(
    access_token: Optional[str] = None,
    account_id: Optional[str] = None,
    api_version: Optional[str] = None,
) -> dict[str, Any]:
    """Verifies Instagram access token and account ID against Meta Graph API."""
    cfg = settings.instagram
    token = access_token or cfg.access_token
    acc_id = account_id or cfg.account_id
    version = api_version or cfg.graph_api_version

    if not token or not acc_id:
        return {
            "valid": False,
            "error": "Instagram Access Token oder Account ID fehlt in der Konfiguration.",
        }

    url = f"https://graph.facebook.com/{version}/{acc_id}"
    params = {
        "fields": "id,name,username",
        "access_token": token,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if response.status_code == 200 and "id" in data:
            return {
                "valid": True,
                "id": data.get("id"),
                "name": data.get("name"),
                "username": data.get("username"),
            }
        else:
            error_info = data.get("error", {}).get("message", response.text)
            return {"valid": False, "error": error_info}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def interactive_tiktok_login(session_dir: Optional[Path] = None) -> bool:
    """Launches Playwright in headed mode allowing the user to manually log into TikTok.

    Once logged in, the session state/cookies are automatically preserved
    in the persistent context directory for future automated headless uploads.
    """
    from playwright.sync_api import sync_playwright

    target_dir = session_dir or settings.tiktok.session_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starte interaktiven TikTok-Login mit Session-Verzeichnis: {target_dir}")
    logger.info("Ein Browserfenster öffnet sich. Bitte melde dich bei TikTok an und schliesse den Tab oder das Fenster.")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(target_dir),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        page = context.new_page()
        page.goto("https://www.tiktok.com/login", wait_until="networkidle")

        print("\n" + "=" * 60)
        print("TIKTOK LOGIN ANLEITUNG:")
        print("1. Melde dich im geöffneten Browserfenster bei deinem TikTok-Konto an.")
        print("2. Sobald du angemeldet bist, navigiere zur Startseite oder Upload-Seite.")
        print("3. Drücke hier in der Konsole [ENTER], sobald du eingeloggt bist.")
        print("=" * 60 + "\n")

        try:
            input("Drücke [ENTER], um den Login zu bestätigen und die Session zu sichern... ")
        except (KeyboardInterrupt, EOFError):
            pass

        context.close()
        logger.success(f"TikTok-Session im Verzeichnis gesichert: {target_dir}")
        return True
