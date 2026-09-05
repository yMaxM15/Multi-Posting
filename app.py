"""Multi-Posting Automation Tool.

Simultaneously publishes vertical short videos across:
- YouTube Shorts
- Instagram Reels
- TikTok

Supports both Typer CLI and interactive Streamlit Web UI.
"""

from __future__ import annotations

import concurrent.futures
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from config import settings
from uploader.base import BaseUploader, UploadResult
from uploader.instagram import InstagramReelsUploader
from uploader.tiktok import TikTokUploader
from uploader.youtube import YouTubeShortsUploader
from utils.auth import interactive_tiktok_login, verify_instagram_credentials
from utils.validator import VideoInfo, VideoValidationError, validate_video

# Configure Loguru logger
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO",
)
LOG_FILE = Path(__file__).resolve().parent / "logs" / "multi_posting_{time:YYYY-MM-DD}.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logger.add(
    str(LOG_FILE),
    rotation="10 MB",
    retention="14 days",
    level="DEBUG",
    encoding="utf-8",
)


# =====================================================================
# CORE ORCHESTRATION (Parallel Multi-Posting)
# =====================================================================
def get_available_uploaders() -> dict[str, BaseUploader]:
    """Returns initialized uploader instances."""
    return {
        "youtube": YouTubeShortsUploader(),
        "instagram": InstagramReelsUploader(),
        "tiktok": TikTokUploader(),
    }


def publish_all_parallel(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[list[str]] = None,
    platforms: Optional[list[str]] = None,
    strict_validation: bool = True,
) -> tuple[Optional[VideoInfo], dict[str, UploadResult]]:
    """Validates the video and concurrently uploads to selected platforms.

    Args:
        video_path: Path to the local MP4 video.
        title: Title of the video.
        description: Description / caption of the video.
        tags: Hashtags or keyword tags.
        platforms: List of platforms ('youtube', 'instagram', 'tiktok') or None for all.
        strict_validation: If True, enforces strict 9:16 vertical ratio check.

    Returns:
        Tuple of (VideoInfo metadata, dict mapping platform key to UploadResult).
    """
    logger.info(f"=== Starte Multi-Posting Workflow für: {video_path.name} ===")

    # 1. Video validation
    try:
        video_info = validate_video(video_path, strict_9_16=strict_validation)
    except VideoValidationError as val_err:
        logger.error(f"Video-Validierung fehlgeschlagen: {val_err}")
        raise

    # 2. Determine target uploaders
    all_uploaders = get_available_uploaders()
    if platforms:
        selected_keys = [p.strip().lower() for p in platforms]
        uploaders = {k: v for k, v in all_uploaders.items() if k in selected_keys}
    else:
        uploaders = all_uploaders

    if not uploaders:
        raise ValueError("Keine gültigen Plattformen für den Upload ausgewählt.")

    logger.info(
        f"Ausgewählte Plattformen für parallelen Upload: {', '.join([u.name for u in uploaders.values()])}"
    )

    results: dict[str, UploadResult] = {}

    # 3. Concurrent execution with ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(uploaders)) as executor:
        future_to_platform = {
            executor.submit(
                uploader.run_safe,
                video_path=video_info.path,
                title=title,
                description=description,
                tags=tags,
            ): key
            for key, uploader in uploaders.items()
        }

        for future in concurrent.futures.as_completed(future_to_platform):
            platform_key = future_to_platform[future]
            try:
                result = future.result()
                results[platform_key] = result
            except Exception as exc:
                logger.critical(f"Kritischer Ausnahmefehler bei {platform_key}: {exc}")
                results[platform_key] = UploadResult(
                    platform=platform_key,
                    success=False,
                    message=f"Kritischer Fehler: {exc}",
                    error=str(exc),
                )

    # 4. Summary Log
    logger.info("=== Multi-Posting Zusammenfassung ===")
    for key, res in results.items():
        status = "ERFOLGREICH" if res.success else "FEHLGESCHLAGEN"
        logger.info(f"[{res.platform}] {status} ({res.execution_time:.1f}s): {res.message}")

    return video_info, results


# =====================================================================
# STREAMLIT DASHBOARD UI
# =====================================================================
def run_streamlit_dashboard() -> None:
    """Renders the Streamlit Web UI."""
    import streamlit as st

    st.set_page_config(
        page_title="Multi-Posting Automation Tool",
        page_icon="🚀",
        layout="wide",
    )

    st.title("🚀 Multi-Posting Automation Tool")
    st.markdown(
        "Veröffentliche deine Videos **gleichzeitig** und automatisiert auf "
        "**YouTube Shorts**, **Instagram Reels** und **TikTok**."
    )

    # Sidebar: System Status
    st.sidebar.header("⚙️ Konfigurationsstatus")
    status_summary = settings.get_status_summary()
    for name, is_ready in status_summary.items():
        if is_ready:
            st.sidebar.success(f"✅ {name}: Bereit")
        else:
            st.sidebar.warning(f"⚠️ {name}: Nicht konfiguriert")

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔑 TikTok Session")
    if settings.tiktok.session_dir.exists() and any(settings.tiktok.session_dir.iterdir()):
        st.sidebar.success("✅ TikTok Session-Cookies vorhanden")
    else:
        st.sidebar.info(
            "ℹ️ Noch keine TikTok-Session. Führe im Terminal `python app.py tiktok-login` aus."
        )

    # Main columns
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.subheader("1. Video auswählen & Details")
        uploaded_file = st.file_uploader(
            "Wähle ein MP4-Video (9:16 Hochformat)",
            type=["mp4"],
            help="Video für Shorts/Reels/TikTok im Hochformat.",
        )

        video_path_input = st.text_input(
            "Oder lokaler Dateipfad:",
            placeholder="C:/Videos/mein_short.mp4",
        )

        title = st.text_input(
            "Titel des Videos:",
            placeholder="5 KI-Tools, die du 2026 kennen musst",
            help="#Shorts wird bei YouTube automatisch ergänzt.",
        )

        description = st.text_area(
            "Beschreibung / Caption:",
            placeholder="In diesem Video zeige ich die besten KI-Tools für Entwickler...",
            height=120,
        )

        tags_str = st.text_input(
            "Tags / Hashtags (Kommagetrennt oder mit #):",
            placeholder="ai, coding, tech, shorts, reel",
        )

        strict_val = st.checkbox(
            "Strikte 9:16 Validierung erzwingen",
            value=True,
            help="Prüft exakt, ob das Video im 9:16 Hochformat vorliegt.",
        )

        st.subheader("2. Zielplattformen")
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            yt_selected = st.checkbox("YouTube Shorts", value=True)
        with col_p2:
            ig_selected = st.checkbox("Instagram Reels", value=True)
        with col_p3:
            tt_selected = st.checkbox("TikTok", value=True)

        selected_platforms = []
        if yt_selected:
            selected_platforms.append("youtube")
        if ig_selected:
            selected_platforms.append("instagram")
        if tt_selected:
            selected_platforms.append("tiktok")

    with col_right:
        st.subheader("3. Video-Vorschau & Validierung")
        active_video_path: Optional[Path] = None

        if uploaded_file is not None:
            # Save uploaded file temporarily
            temp_dir = Path(tempfile.gettempdir()) / "multi_posting_uploads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_video_file = temp_dir / uploaded_file.name
            with open(temp_video_file, "wb") as f:
                f.write(uploaded_file.getbuffer())
            active_video_path = temp_video_file
        elif video_path_input.strip():
            candidate = Path(video_path_input.strip())
            if candidate.exists():
                active_video_path = candidate
            else:
                st.error(f"Datei nicht gefunden: {candidate}")

        if active_video_path:
            st.video(str(active_video_path))
            try:
                info = validate_video(active_video_path, strict_9_16=False)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Auflösung", f"{info.width}x{info.height}")
                c2.metric("Ratio", f"{info.aspect_ratio:.2f}", "9:16" if info.is_9_16 else "Abweichung")
                c3.metric("Dauer", f"{info.duration_seconds:.1f}s")
                c4.metric("Dateigröße", f"{info.size_mb:.1f} MB")

                if not info.is_9_16:
                    st.warning("⚠️ Das Video weicht vom 9:16-Format ab!")
                else:
                    st.success("✅ Perfektes 9:16 Hochformat für Shorts/Reels/TikTok!")
            except Exception as e:
                st.error(f"Validierungsfehler: {e}")

    # Action Button
    st.markdown("---")
    can_upload = bool(active_video_path and title.strip() and selected_platforms)
    if st.button("🚀 Parallel auf allen Plattformen veröffentlichen", type="primary", disabled=not can_upload):
        tags_list = [
            t.strip().lstrip("#")
            for t in tags_str.replace(";", ",").split(",")
            if t.strip()
        ]

        with st.spinner("Paralleler Upload läuft auf ausgewählten Plattformen..."):
            try:
                v_info, upload_results = publish_all_parallel(
                    video_path=active_video_path,
                    title=title,
                    description=description,
                    tags=tags_list,
                    platforms=selected_platforms,
                    strict_validation=strict_val,
                )

                st.subheader("📊 Upload-Ergebnisse")
                res_cols = st.columns(len(upload_results))
                for col, (platform_key, res) in zip(res_cols, upload_results.items()):
                    with col:
                        if res.success:
                            st.success(f"**{res.platform}**\n\n✅ {res.message}")
                            if res.url:
                                st.markdown(f"[🔗 Zum Beitrag]({res.url})")
                            st.caption(f"⏱️ Zeit: {res.execution_time:.1f}s")
                        else:
                            st.error(f"**{res.platform}**\n\n❌ Fehlgeschlagen")
                            st.caption(f"Fehler: {res.error or res.message}")
            except Exception as main_err:
                st.error(f"Fehler beim Multi-Posting: {main_err}")


# =====================================================================
# TYPER CLI INTERFACE
# =====================================================================
import typer
from rich.console import Console
from rich.table import Table

cli = typer.Typer(
    help="Multi-Posting Automation Tool - Paralleler Upload für YouTube Shorts, Instagram Reels & TikTok.",
    no_args_is_help=True,
)
console = Console()


@cli.command(name="upload")
def cmd_upload(
    video_path: Path = typer.Argument(..., help="Pfad zur vertikalen MP4-Videodatei"),
    title: str = typer.Option(..., "--title", "-t", help="Titel des Videos"),
    description: str = typer.Option("", "--description", "-d", help="Beschreibung / Caption"),
    tags: str = typer.Option("", "--tags", help="Tags / Hashtags getrennt durch Komma"),
    platforms: str = typer.Option(
        "all",
        "--platforms",
        "-p",
        help="Kommagetrennte Liste der Plattformen (youtube,instagram,tiktok) oder 'all'",
    ),
    strict: bool = typer.Option(
        True,
        "--strict/--no-strict",
        help="Strikte Prüfung auf 9:16 Hochformat erzwingen",
    ),
    privacy: str = typer.Option(
        "public",
        "--privacy",
        help="YouTube Privacy Status (public, unlisted, private)",
    ),
) -> None:
    """Lädt ein Video parallel auf YouTube Shorts, Instagram Reels und TikTok hoch."""
    console.rule("[bold cyan]Multi-Posting Automation CLI[/bold cyan]")

    target_platforms = None if platforms.lower() == "all" else [p.strip() for p in platforms.split(",")]
    tags_list = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]

    try:
        _, results = publish_all_parallel(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags_list,
            platforms=target_platforms,
            strict_validation=strict,
        )

        table = Table(title="Upload-Ergebnisse", show_header=True, header_style="bold magenta")
        table.add_column("Plattform", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Dauer", justify="right")
        table.add_column("URL / ID", style="blue")
        table.add_column("Details", style="dim")

        for key, res in results.items():
            status_text = "[bold green]ERFOLG[/bold green]" if res.success else "[bold red]FEHLER[/bold red]"
            url_text = res.url or res.video_id or "N/A"
            details = res.message if res.success else (res.error or res.message)
            table.add_row(res.platform, status_text, f"{res.execution_time:.1f}s", url_text, details)

        console.print(table)

    except Exception as e:
        console.print(f"[bold red]Abbruch mit Fehler:[/bold red] {e}")
        sys.exit(1)


@cli.command(name="validate")
def cmd_validate(
    video_path: Path = typer.Argument(..., help="Pfad zum zu prüfenden MP4-Video"),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Strikte 9:16 Validierung"),
) -> None:
    """Prüft ein Video auf MP4-Format, vertikales 9:16-Seitenverhältnis und Metadaten."""
    console.rule("[bold cyan]Video-Validierung[/bold cyan]")
    try:
        info = validate_video(video_path, strict_9_16=strict)
        table = Table(title=f"Metadaten: {video_path.name}")
        table.add_column("Eigenschaft", style="cyan")
        table.add_column("Wert", style="green")

        table.add_row("Dateigröße", f"{info.size_mb:.2f} MB")
        table.add_row("Auflösung", f"{info.width} x {info.height}")
        table.add_row("Seitenverhältnis", f"{info.aspect_ratio:.4f} (Ideal 9:16: 0.5625)")
        table.add_row("Ist Vertikal", "Ja" if info.is_vertical else "Nein")
        table.add_row("Entspricht 9:16", "Ja" if info.is_9_16 else "Nein")
        table.add_row("Dauer", f"{info.duration_seconds:.2f} Sekunden")
        table.add_row("Bildrate (FPS)", f"{info.fps:.2f}")

        console.print(table)
        console.print("[bold green]Video ist optimal für Shorts, Reels und TikTok geeignet![/bold green]")
    except VideoValidationError as e:
        console.print(f"[bold red]Validierungsfehler:[/bold red] {e}")
        sys.exit(1)


@cli.command(name="status")
def cmd_status() -> None:
    """Prüft den Konfigurations- und Authentifizierungsstatus aller Plattformen."""
    console.rule("[bold cyan]System & API Status[/bold cyan]")
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Dienst", style="cyan")
    table.add_column("Konfiguriert", justify="center")
    table.add_column("Details")

    # Storage
    st_ready = settings.storage.is_configured()
    table.add_row(
        f"Cloud Storage ({settings.storage.provider.upper()})",
        "[green]Ja[/green]" if st_ready else "[red]Nein[/red]",
        f"Bucket: {settings.storage.bucket_name or 'nicht gesetzt'}",
    )

    # YouTube
    yt_ready = settings.youtube.is_configured()
    table.add_row(
        "YouTube Shorts",
        "[green]Ja[/green]" if yt_ready else "[red]Nein[/red]",
        f"Secrets: {settings.youtube.client_secrets_file.name} | Token: {settings.youtube.token_file.exists()}",
    )

    # Instagram
    ig_ready = settings.instagram.is_configured()
    ig_verify = verify_instagram_credentials() if ig_ready else {"valid": False, "error": "Nicht konfiguriert"}
    ig_status = "[green]Ja[/green]" if ig_verify.get("valid") else "[yellow]Token ungültig/fehlt[/yellow]"
    table.add_row(
        "Instagram Reels",
        ig_status,
        f"Account ID: {settings.instagram.account_id or 'fehlt'} ({ig_verify.get('username') or ig_verify.get('error')})",
    )

    # TikTok
    tt_session = TikTokUploader().has_saved_session()
    table.add_row(
        "TikTok",
        "[green]Session OK[/green]" if tt_session else "[yellow]Keine Session[/yellow]",
        f"Session Dir: {settings.tiktok.session_dir} (Login via 'python app.py tiktok-login')",
    )

    console.print(table)


@cli.command(name="tiktok-login")
def cmd_tiktok_login() -> None:
    """Öffnet ein Browserfenster für den interaktiven TikTok-Login und speichert Cookies."""
    console.rule("[bold cyan]Interaktiver TikTok-Login[/bold cyan]")
    try:
        interactive_tiktok_login()
        console.print("[bold green]TikTok-Session erfolgreich gespeichert![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Login-Fehler:[/bold red] {e}")


@cli.command(name="ui")
def cmd_ui() -> None:
    """Startet das interaktive Streamlit Web-Dashboard im Browser."""
    import subprocess
    console.print("[bold green]Starte Streamlit Web-Dashboard...[/bold green]")
    script_path = Path(__file__).resolve()
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(script_path)])


# Entry point dispatcher
if __name__ == "__main__":
    # Check if executed via `streamlit run app.py`
    try:
        import streamlit as st
        is_streamlit = st.runtime.exists()
    except Exception:
        is_streamlit = False

    if is_streamlit:
        run_streamlit_dashboard()
    else:
        cli()
