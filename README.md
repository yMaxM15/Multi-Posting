# 🚀 Multi-Posting Automation Tool

Ein modulares, hochperformantes Python-Tool zur **gleichzeitigen, parallelen Veröffentlichung** von vertikalen Kurzvideos (9:16) auf:
- 🎬 **YouTube Shorts** (Google Data API v3 mit OAuth 2.0 & Resumable Upload)
- 📸 **Instagram Reels** (Meta Graph API v19+ mit automatischem S3/R2 Cloud-Hosting)
- 🎵 **TikTok** (Playwright Browser-Automation mit persistenten Login-Sessions)

Bietet sowohl ein modernes **Streamlit Web-Dashboard** als auch ein vollwertiges **Typer CLI**.

---

## 📁 Projektstruktur

```text
├── app.py                  # Entry Point (CLI und Streamlit Dashboard)
├── config.py               # Lädt und validiert Umgebungsvariablen (.env)
├── uploader/
│   ├── __init__.py
│   ├── base.py             # Abstrakte Base-Klasse & UploadResult Dataclass
│   ├── youtube.py          # YouTube API Integration (Resumable Upload)
│   ├── instagram.py        # Meta Graph API + S3/R2 Video-Hosting
│   └── tiktok.py           # Playwright Headless Browser-Automation
├── utils/
│   ├── __init__.py
│   ├── storage.py          # S3 / Cloudflare R2 Upload- & Lifecycle-Helfer
│   ├── auth.py             # Token-Handling, Refresh & TikTok-Login
│   └── validator.py        # Video-Validierung (MP4, 9:16 Hochformat, Metadaten)
├── .env.example            # Konfigurationsvorlage für alle API-Keys & Tokens
├── requirements.txt        # Alle Python-Abhängigkeiten
└── README.md               # Setup-Anleitung & Dokumentation
```

---

## ⚡ Schnellstart & Installation

### 1. Repository vorbereiten & Abhängigkeiten installieren
```bash
# Virtuelle Umgebung (optional, empfohlen)
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Playwright Browser herunterladen (für TikTok)
python -m playwright install chromium
```

### 2. Konfiguration anlegen
Kopiere die Vorlage `.env.example` nach `.env`:
```bash
cp .env.example .env
```

---

## ⚙️ Plattform-Setup & Zugangsdaten

### A. YouTube Shorts (Google Cloud Console)
1. Gehe zur [Google Cloud Console](https://console.cloud.google.com/).
2. Erstelle ein neues Projekt (z.B. `Multi-Posting-Bot`).
3. Aktiviere die **YouTube Data API v3** unter *APIs und Dienste > Bibliothek*.
4. Konfiguriere den **OAuth-Zustimmungsbildschirm** (OAuth consent screen):
   - Wähle *Extern*.
   - Füge deine eigene E-Mail als Testnutzer hinzu.
   - Füge den Scope `https://www.googleapis.com/auth/youtube.upload` hinzu.
5. Erstelle Anmeldedaten:
   - Klicke auf *Anmeldedaten erstellen > OAuth-Client-ID*.
   - Anwendungstyp: **Desktop-App**.
   - Lade die JSON-Datei herunter und speichere sie im Projektverzeichnis als **`client_secrets.json`**.
6. Beim ersten Upload öffnet sich automatisch ein Browserfenster zur Autorisierung. Das Token wird danach lokal in `token.json` gespeichert und automatisch erneuert.

---

### B. Instagram Reels (Meta Graph API)
Meta verlangt für den Reels-Upload einen Instagram Business/Creator Account und eine temporäre, öffentlich erreichbare HTTPS-URL (S3 oder Cloudflare R2).

#### 1. Meta App & Access Token
1. Gehe zum [Meta for Developers Portal](https://developers.facebook.com/).
2. Erstelle eine App vom Typ **Business**.
3. Verknüpfe dein Instagram Creator/Business-Konto mit einer Facebook-Seite.
4. Füge die Produkt-API **Instagram Graph API** hinzu.
5. Generiere im Graph API Explorer ein User Access Token mit folgenden Rechten:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
6. Tausche dieses bei Bedarf in ein langlebiges Token um (Long-Lived Token, 60 Tage gültig).
7. Ermittle deine numerische `INSTAGRAM_ACCOUNT_ID` über `GET /me/accounts` gefolgt von `GET /{page-id}?fields=instagram_business_account`.
8. Trage Token und Account-ID in die `.env` ein:
   ```env
   INSTAGRAM_ACCESS_TOKEN=EAAG...
   INSTAGRAM_ACCOUNT_ID=17841400000000000
   ```

#### 2. Cloud Storage (AWS S3 oder Cloudflare R2)
Für den Container-Upload bei Meta wird das Video temporär hochgeladen und nach erfolgreicher Veröffentlichung sofort automatisch wieder gelöscht:
- **AWS S3**:
  ```env
  STORAGE_PROVIDER=s3
  S3_BUCKET_NAME=mein-reels-bucket
  S3_ACCESS_KEY_ID=AKIA...
  S3_SECRET_ACCESS_KEY=...
  S3_REGION_NAME=eu-central-1
  ```
- **Cloudflare R2**:
  ```env
  STORAGE_PROVIDER=r2
  S3_BUCKET_NAME=mein-r2-bucket
  S3_ACCESS_KEY_ID=...
  S3_SECRET_ACCESS_KEY=...
  S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
  S3_PUBLIC_BASE_URL=https://pub-<hash>.r2.dev
  ```

---

### C. TikTok (Playwright Automation)
Für TikTok ist kein komplexer App-Review nötig. Das Tool nutzt einen automatisierten Chromium-Browser mit persistentem Profil (`./tiktok_session`), um Cookies dauerhaft zu speichern.

1. **Einmaliger interaktiver Login:**
   Führe folgenden Befehl aus:
   ```bash
   python app.py tiktok-login
   ```
2. Es öffnet sich ein reguläres Browserfenster. Melde dich bei deinem TikTok-Konto an (2FA, Captchas oder QR-Code).
3. Bestätige den Login im Terminal mit `[ENTER]`.
4. Die Session-Cookies bleiben im Ordner `tiktok_session` gespeichert. Alle künftigen Uploads erfolgen vollautomatisch!

---

## 🖥️ Verwendung & Bedienung

### 1. Interaktives Web-Dashboard (Streamlit)
Das grafische Dashboard bietet Drag-and-Drop Video-Upload, Live-Vorschau, Validierungsmetriken und parallelen Upload:

```bash
# Dashboard starten:
python app.py ui
# ODER direkt via Streamlit:
streamlit run app.py
```

### 2. Kommandozeile (Typer CLI)

#### System- & API-Status prüfen
```bash
python app.py status
```

#### Video validieren (Format, Dimensionen, 9:16 Aspect Ratio)
```bash
python app.py validate ./mein_short.mp4
```

#### Paralleler Multi-Plattform-Upload
```bash
python app.py upload ./mein_short.mp4 \
  --title "5 KI-Tricks für Entwickler 2026" \
  --description "Schau dir diese neuen Automationen an! Mehr im Profil." \
  --tags "ki,coding,python,automation" \
  --privacy public
```

#### Einzelne Plattformen gezielt ansteuern
```bash
# Nur YouTube Shorts und Instagram Reels:
python app.py upload ./mein_short.mp4 -t "Mein Video" -p youtube,instagram

# Nur TikTok:
python app.py upload ./mein_short.mp4 -t "Mein Video" -p tiktok
```

---

## 🛡️ Technische Highlights & Best Practices

- **Resilienz & Fehlerisolierung:** Alle Uploads laufen in einem parallelen `ThreadPoolExecutor`. Schlägt eine Plattform fehl (z.B. temporärer API-Fehler), wird der Prozess für die anderen Plattformen **nicht** abgebrochen.
- **Resumable Uploads:** YouTube-Uploads nutzen chunks (4 MB) mit exponentiellem Backoff bei Netzwerkstörungen.
- **Sichere Cloud-Lifecycle:** Temporäre S3/R2-Dateien für Instagram Reels werden in einem `finally`-Block garantiert nach Veröffentlichung gelöscht.
- **9:16-Validierung:** Prüft Auflösung, Bildrate und berechnet das Seitenverhältnis vor dem Upload, um fehlerhafte Posts zu verhindern.
- **Strukturiertes Logging:** Ausführliche Logs mit Rotation werden automatisch in `logs/multi_posting_YYYY-MM-DD.log` archiviert.
