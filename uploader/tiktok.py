"""TikTok Uploader using Playwright Headless/Headed Browser Automation."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional
from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from config import settings
from uploader.base import BaseUploader, UploadResult


class TikTokUploader(BaseUploader):
    """Automates TikTok upload using Playwright with persistent session context."""

    def __init__(
        self,
        session_dir: Optional[Path] = None,
        headless: Optional[bool] = None,
        timeout_ms: Optional[int] = None,
    ) -> None:
        super().__init__(name="TikTok")
        cfg = settings.tiktok
        self.session_dir = session_dir or cfg.session_dir
        self.headless = headless if headless is not None else cfg.headless
        self.timeout_ms = timeout_ms or cfg.timeout_ms
        self.upload_url = "https://www.tiktok.com/creator-center/upload?from=upload"

    def is_configured(self) -> bool:
        return True

    def has_saved_session(self) -> bool:
        """Checks if session directory exists and contains user data."""
        return self.session_dir.exists() and any(self.session_dir.iterdir())

    def _format_caption(self, title: str, tags: Optional[list[str]] = None) -> str:
        """Builds concise TikTok caption with hashtags."""
        parts = [title.strip()] if title else []
        if tags:
            tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
            parts.append(tag_str)
        return " ".join(parts)

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> UploadResult:
        """Uploads video to TikTok by automating Creator Center in Playwright."""
        caption = self._format_caption(title or description, tags)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[TikTok] Initialisiere Browser-Automation (Headless: {self.headless}, "
            f"Session: {self.session_dir})..."
        )

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=self.headless,
                viewport={"width": 1280, "height": 850},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ],
            )

            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)

            try:
                logger.info(f"[TikTok] Öffne Upload-Seite: {self.upload_url}")
                page.goto(self.upload_url, wait_until="domcontentloaded")
                time.sleep(3)

                # Check if redirected to login page
                current_url = page.url
                if "login" in current_url:
                    raise RuntimeError(
                        "TikTok erfordert Authentifizierung! Bitte führe zuerst den interaktiven Login aus:\n"
                        "-> Befehl: python app.py tiktok-login\n"
                        "Danach werden deine Login-Cookies in 'tiktok_session' gespeichert."
                    )

                # Wait for file input or upload iframe
                logger.info("[TikTok] Suche nach Datei-Upload-Element...")
                file_input = None

                # 1. Direct file input
                try:
                    page.wait_for_selector('input[type="file"]', timeout=15000)
                    file_input = page.locator('input[type="file"]').first
                except PlaywrightTimeoutError:
                    # Check inside iframes (TikTok Creator Center sometimes uses an iframe)
                    for frame in page.frames:
                        try:
                            if frame.locator('input[type="file"]').count() > 0:
                                file_input = frame.locator('input[type="file"]').first
                                logger.info("[TikTok] Datei-Input in iFrame gefunden.")
                                break
                        except Exception:
                            continue

                if not file_input:
                    raise RuntimeError(
                        "Konnte das Datei-Upload-Element auf TikTok nicht finden. "
                        "Möglicherweise ist das Creator Center noch nicht eingeloggt oder das Layout hat sich geändert."
                    )

                logger.info(f"[TikTok] Lade Videodatei hoch: {video_path.name}")
                file_input.set_input_files(str(video_path))

                # Wait for caption field
                logger.info("[TikTok] Warte auf Beschreibungsfeld...")
                time.sleep(4)

                # Modern TikTok caption field selectors
                caption_selectors = [
                    'div[contenteditable="true"]',
                    '.DraftEditor-root div[contenteditable="true"]',
                    '.notranslate.public-DraftEditor-content',
                    '[data-placeholder*="caption" i]',
                    '[data-placeholder*="Beschreibung" i]',
                    'input[placeholder*="caption" i]',
                ]

                caption_elem = None
                for sel in caption_selectors:
                    try:
                        elem = page.locator(sel).first
                        if elem.is_visible(timeout=3000):
                            caption_elem = elem
                            break
                    except Exception:
                        continue

                if caption_elem:
                    logger.info(f"[TikTok] Trage Caption ein: {caption[:40]}...")
                    try:
                        caption_elem.click()
                        # Select all existing text and replace
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(caption, delay=20)
                    except Exception as e:
                        logger.warning(f"[TikTok] Konnte Caption nicht optimal einfügen: {e}")
                else:
                    logger.warning("[TikTok] Beschreibungsfeld nicht direkt gefunden; fahre fort...")

                # Wait for video upload & processing completion
                logger.info("[TikTok] Warte auf vollständigen Video-Upload (100% bzw. Verarbeitungsabschluss)...")

                # Look for progress indicators or post button enablement
                post_button_selectors = [
                    'button:has-text("Post")',
                    'button:has-text("Posten")',
                    'button:has-text("Veröffentlichen")',
                    '.btn-post',
                    'button[data-e2e="post_video_button"]',
                ]

                post_btn = None
                start_wait = time.time()
                while time.time() - start_wait < (self.timeout_ms / 1000):
                    for p_sel in post_button_selectors:
                        try:
                            candidate = page.locator(p_sel).first
                            if candidate.is_visible() and candidate.is_enabled():
                                post_btn = candidate
                                break
                        except Exception:
                            continue
                    if post_btn:
                        # Give extra 3 seconds for TikTok video preview and transcoding check
                        time.sleep(3)
                        break
                    time.sleep(2)

                if not post_btn:
                    raise TimeoutError(
                        "Timeout beim Warten auf die Fertigstellung des Video-Uploads auf TikTok. "
                        "Der 'Posten'-Button wurde nicht aktiv."
                    )

                logger.info("[TikTok] Klicke auf 'Posten' / 'Post'...")
                post_btn.click()

                # Wait for success dialog or confirmation redirect
                logger.info("[TikTok] Warte auf Veröffentlichungsbestätigung...")
                time.sleep(5)

                success_indicators = [
                    'text="Your video is being uploaded"',
                    'text="Dein Video wird hochgeladen"',
                    'text="Video uploaded"',
                    'text="Manage your posts"',
                    'text="Beiträge verwalten"',
                ]

                post_confirmed = False
                for ind in success_indicators:
                    try:
                        if page.locator(ind).first.is_visible(timeout=5000):
                            post_confirmed = True
                            logger.success(f"[TikTok] Erfolgsmeldung erkannt: {ind}")
                            break
                    except Exception:
                        continue

                return UploadResult(
                    platform=self.name,
                    success=True,
                    message="Video erfolgreich an TikTok übermittelt!",
                    url="https://www.tiktok.com/creator-center",
                    extra={"caption": caption, "confirmed": post_confirmed},
                )

            except Exception as e:
                logger.error(f"[TikTok] Automationsfehler: {e}")
                raise
            finally:
                context.close()
