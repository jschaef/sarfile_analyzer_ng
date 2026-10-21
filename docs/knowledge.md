# Wissen zu sarfile_analyzer_ng

Gesammelte Erkenntnisse (Stand 21.10.2026), entstanden beim Bau des
Web-Frontends sarfile_analyzer_web und beim Lab-Deployment. Jeder
`##`-Abschnitt steht für sich und kann einzeln in eine Wissens-Collection
(z. B. cloud-memory) übernommen werden. Kurzfassung für Agenten:
[`../CLAUDE.md`](../CLAUDE.md). Gegenstück im Web-Repo:
`sarfile_analyzer_web/docs/knowledge.md`.

---

## 1. Überblick und Repos

- **sarfile_analyzer_ng** (`github.com/jschaef/sarfile_analyzer_ng`): Analyse
  von Linux-sar-Dateien. Fork von `jschaef/sar_file_analyzer`, rechnet mit
  polars statt pandas (pandas noch für die Darstellung).
- Teile:
  - `code/` – die klassische **Streamlit-App** (Einstieg
    `start_sar_analyzer.py`)
  - `api/` – **REST-API** `/api/v1` (FastAPI)
  - `mcp_server/` – **MCP-Server** für KI-Agenten, spricht nur mit der API
  - `deployment/lab/` – Lab-Server dus-lab-sar; `deployment/sarfile-analyzer.yml`
    – Kubernetes-Beispiel; `docker/` – Image nur mit der Streamlit-App (SLE
    15.6, python312); `.devcontainer/` – Codespaces
- **sarfile_analyzer_web** (eigenes Repo): neues Web-Frontend (Next.js) mit
  eigenem Backend sar-web-api (`/api/v2`), das `code/` und `api/` dieses
  Repos **importiert**. Änderungen hier können es brechen – siehe Abschnitt 8.
- Alle Oberflächen teilen `code/data.db` (Benutzer, Headings, Metriken) und
  `$UPLOAD_DIR` (Dateien, gemeinsamer Zustand).

## 2. Arbeitsregeln von Jochen

- Mit Jochen **Deutsch** sprechen; Code, Kommentare und Commit-Nachrichten
  **Englisch**; PR-Beschreibungen und Lab-Doku **Deutsch**.
- Änderungen an diesem Repo nur auf **ausdrücklichen Wunsch**, auf einem
  Session-Branch, mit **Jochen als Author**:
  `--author="Jochen Schäfer <jochen.schaefer@suse.com>"`. Kein
  `Co-Authored-By`; letzte Zeile `Claude-Session: <url>`.
- **Nie nach `main` pushen, nie mergen.** Jochen mergt selbst, meist lokal:
  `git merge --ff-only origin/<branch> && git push origin main`, danach den
  Branch löschen.
- Kleine Commits, ein Thema, erst nach erfolgreicher Prüfung.
- **`code/data.db` im Repo ist der Seed** – nur `admin`/`password`, Rollen,
  Headings, Metriken. Nie echte Benutzer committen; Tests und Experimente
  auf einer Kopie. **Keine echten sar-Dateien** ins Repo.
- Jochen ist SUSE-Support-Engineer, programmiert vor allem Python; Linux-
  und SLES-Wissen darf vorausgesetzt werden.

## 3. Streamlit-App (code/)

- `start_sar_analyzer.py`: Sidebar-Menü Login / Signup / Help / Logout
  (`streamlit_option_menu`), bei gesetztem `web_frontend_url` darunter der
  Button „New web frontend“. Nach dem Login Aufgaben-Menü:
  - Admin: Analyze Data, Manage Sar Files, DB Management, Redis Management,
    TODO, Self Service, User Management, Info
  - User: Analyze Data, Manage Sar Files, Self Service, Info
  - Programmatische Navigation über die Session-Keys `nav_top`/`nav_analysis`.
- Seiten → Module:
  - `analyze_pl.py` – Analyze Data mit Graphical Overview
    (`dia_overview_pl.py`), Detailed Metrics View (`single_file_pl.py`),
    Multiple Sar Files (`multi_files_pl.py`), Metrics on many devices
    (`display_multi.py`), Compare Metrics (`handle_metrics_pl.py`,
    `metric_page_helpers_pl.py`)
  - `mng_sar.py` – Manage Sar Files (Show/Add/Delete)
  - `db_mng.py` – Metriken und Headings pflegen
  - `redis_mng.py` – Redis-Client und „Delete Redis Keys“
  - `self_service.py` – Passwort ändern; `admin_service()` = User Management
    (Benutzer, Passwörter, Rollen, Löschen, Login-Historie)
  - `info.py`, `help.py`, `todo.py` (statisch)
- Diagramme: `bokeh_charts.py` (Bokeh, Restart-Marker), `alt.py` (Altair),
  `streamlit_bokeh_component.py` (registriert streamlit-bokeh als
  Components-**v1**-Komponente, weil streamlit-bokeh ab Streamlit 1.51 sonst
  Components v2 nutzt), `multi_pdf.py` (paralleler PDF-Export),
  `driver_pool.py` (Pool headless Firefox/geckodriver für PNG/PDF,
  `min(CPUs/2, 4)`).
- Hilfsmodule: `helpers_pl.py`, `pl_helpers2.py`, `dataframe_funcs_pl.py`,
  `dia_compute_pl.py` (auch von `api/services.py` genutzt), `layout_helper_pl.py`,
  `visual_funcs.py`.
- Vermutlich ungenutzt/Altlast: `tmpapp.py`, `user_info.py` (laut Docstring
  deprecated), `import_metrics.py` (Einmal-Skript), `requirements.txt-org`.
- Streamlit führt das Hauptskript bei jedem Rerun neu aus → „einmal pro
  Prozess“-Logik gehört in importierte Module (z. B.
  `sqlite2_polars.refresh_all_tables_once`).

## 4. Upload, Parsing und Speicherung

- Vorverarbeitung (`sar_ingest.preprocess_upload`, in `mng_sar` und
  `api/services.upload_sar_file`): xz entpacken, sadf-JSON zurück in Text;
  Binärdateien (libmagic) per `unset LANG; sar -A -t -f …` umwandeln.
  Ergebnis muss „ASCII text“ sein.
- Ablage in `$UPLOAD_DIR/<user>/` (Default `upload` relativ zum
  Arbeitsverzeichnis; die API setzt es absolut auf `code/upload`), Name
  `<upload-datum>_<hostname>_<sar-datum>` (`helpers_pl.rename_sar_file`).
- `parse_into_polars.parse_sar_file` schreibt `<datei>.parquet` (Spalten
  header, data, os_details, ggf. restart) und **löscht die Textdatei**. Die
  UI parst beim ersten Analysieren, die API sofort beim Upload.
- **„LINUX RESTART“**-Zeilen landen in der Spalte `restart`; daraus werden
  die gestrichelten Restart-Linien.
- **Dezimaltrenner muss `.` sein** (LC_NUMERIC en_US). Komma wird nur
  umgewandelt, wenn schon die erste Datenzeile `\d+,\d+` enthält – nicht
  verlassen. AM/PM-Zeiten werden ähnlich erkannt.
- **Redis** (`redis_mng`): Hash `<RKEY_PREF>:<user>` (Default `user:<user>`),
  Feld `<datei>_parquet` mit den Parquet-Bytes. Upload/Delete löschen das
  Feld. `get_redis_conn` pingt mit 1 s Timeout; schlägt das fehl, wird Redis
  für genau diese Verbindungsdaten abgeschaltet und auf Parquet bzw. Neu-
  Parsen zurückgefallen. Geänderte Verbindungsdaten (Settings) werden neu
  geprüft. Die API nutzt zusätzlich `sar:sso:ui:<nonce>` für SSO-Tokens.

## 5. data.db und gemeinsamer Zustand

- SQLite über SQLAlchemy (`sql_stuff.py`), Tabellen `userstable`
  (username, password, role_id), `role` (user, admin), `headingstable`
  (header, alias, description, keywd), `metric` (metric, description).
  `find_db()` sucht `code/data.db`, dann Repo-Wurzel, dann Arbeitsverzeichnis.
- Seed im Repo: 1 Benutzer (`admin`), 2 Rollen, 40 Headings, 294 Metriken
  (`.gitignore`/README-lab sprechen von 39 – `deploy.sh` Schritt 4b ergänzt
  das „short CPU header“).
- Passwörter (`hashing.py`): PBKDF2-HMAC-SHA512, 100 000 Iterationen,
  Salt 64 Hex-Zeichen, gespeichert als Salt+Hash.
- Die modulweite Session in `sql_stuff` ist nicht threadsicher;
  sarfile_analyzer_web serialisiert seine Zugriffe darauf mit einem Lock.
- `$UPLOAD_DIR/config/` = gemeinsamer Zustand aller Prozesse:
  `settings.json` (Laufzeit-Settings, 0600), `user_df.parquet`
  (Login-Historie), `login_counter.parquet`, `headingstable.parquet` und
  `metric.parquet` (Tabellen-Cache von `sqlite2_polars`, per mtime; nach
  Schreibzugriffen `invalidate_table_cache()`), `sar-web-api/` (Zustand des
  Web-Backends). Deshalb ist der Benutzername **`config` reserviert**
  (`validation.RESERVED_USERNAMES`, Prüfung case-insensitiv in
  `is_valid_username`).
- Schreiben immer atomar (temp-Datei + `os.replace`), z. B.
  `handle_user_status.atomic_write_parquet`.
- Der Login-Zähler zählt den Benutzer `jschaef` bewusst nicht
  (`COUNTER_EXCLUDED_USER`).

## 6. Laufzeit-Einstellungen (config.py)

- `code/config.py`: `Config` mit Env-Defaults; `EDITABLE_SETTINGS`
  (Name → Typ, Env-Variable, min, max), `SECRET_SETTINGS`
  (`redis_password`), `URL_SETTINGS`.
- Editierbar: `admin_email`, `admin_communication`, `max_header_count`
  (1–12), `cols_per_line` (1–8), `redis_enabled/host/port/user/password`,
  `web_frontend_url` (Streamlit-Sidebar-Button), `streamlit_url` (Link
  „Classic app“ im Web-Frontend). URLs nur `http(s)://`, leer = kein Link.
- Gespeichert in `$UPLOAD_DIR/config/settings.json`, Vorrang vor Env und
  Default. Die Metaklasse `_ConfigMeta` liefert bei `Config.<name>` den
  gespeicherten Wert; `stored_settings()` liest neu, wenn sich mtime/Größe
  ändern → wirkt **ohne Neustart** in Streamlit, API und sar-web-api.
- `update_settings({...})` validiert alles vor dem Schreiben (ValueError),
  schreibt atomar mit 0600; `None` entfernt einen Wert.
- Setzen ohne Web-Frontend (in `code/`):
  `UPLOAD_DIR=$PWD/upload venv/bin/python -c 'import config; print(config.update_settings({"admin_email": "…"}))'`
- **`config.py` nicht für Einstellungen patchen** – dafür gibt es diese
  Settings (früher war auf dem Lab-Server ein Patch nötig, seit 21.10.2026
  nicht mehr).

## 7. REST-API (api/) und MCP-Server (mcp_server/)

- `api/bootstrap.py` legt `code/` auf `sys.path` und setzt `UPLOAD_DIR`
  absolut auf `code/upload`.
- Endpunkte `/api/v1`: `/token`, `/sso/token`, `/sso/validate`, `/users/me`,
  `/users` (admin), `/admin/disk-usage`, `/admin/cleanup` (Default dry-run),
  `/files` (CRUD), `/files/{name}/headers/{header}`, `.../data` (JSON/CSV),
  `.../statistics`, `/charts/single|overview|multi`, `/health`.
- Auth (`api/auth.py`): zustandslose HMAC-SHA256-Tokens, Secret
  `SAR_API_SECRET` (sonst zufällig pro Prozess), TTL `SAR_API_TOKEN_TTL`
  (86400 s). Zweck `api` oder `ui`; `ui`-Tokens sind einmalig.
- Rendering: Bokeh-PNG über einen Driver-Pool (Firefox, Fallback Chrome),
  PDF aus PNG (pypdf); Altair über vl-convert.
- SSO für die Support-Plattform (`api/PLATFORM-INTEGRATION.md`, deutsch):
  `POST /sso/token` mit `X-SSO-Secret` → `api_token` (24 h) und
  `ui_redirect_url`; unbekannte Benutzer werden mit Rolle `user` angelegt;
  Streamlit löst `?sso_token=` über `/sso/validate` ein (`sso_login.py`).
  UI-Token-TTL `SAR_SSO_UI_TTL` (Code-Default 180 s, Lab 900 s).
- Weitere Env: `SAR_SSO_SECRET` (ohne → 503), `SAR_SSO_DEFAULT_PASSWORD`,
  `SAR_UI_BASE_URL`, `SAR_MAX_DECOMPRESSED_BYTES` (512 MiB), `REDIS_*`.
- MCP-Server (`mcp_server/server.py`, FastMCP): Streamable HTTP auf
  `127.0.0.1:8200/mcp` (oder `SAR_MCP_TRANSPORT=stdio`); Tools u. a.
  login, whoami, list/upload/delete_sar_file, get_file_info,
  get_header_details, get_statistics, get_data, generate_chart,
  generate_overview, compare_files, create_user, list_users, disk_usage,
  cleanup_old_files. Meldet sich mit `SAR_API_USERNAME/PASSWORD` an der API
  an (Lab: Service-Account `mcp-agent`, admin).
- `mcp_server/requirements.txt`: **`mcp>=1.26,<2`** – 2.x hat
  `mcp.server.fastmcp` entfernt; ein ungepinntes 2.1.0 hat das Lab gebrochen.

## 8. Abhängigkeit von sarfile_analyzer_web

sar-web-api importiert aus diesem Repo und verlässt sich auf:

- `sql_stuff` (Modelle, `data_db/engine/Session/session` – wird für Tests
  umgebunden), `hashing`, `handle_user_status`, `sqlite2_polars`
  (`get_table_df`, `invalidate_table_cache`, `refresh_all_tables`),
  `redis_mng`, `validation`, `pl_helpers2`, `parse_into_polars`, `config`
  (`Config`, `EDITABLE_SETTINGS`, `SECRET_SETTINGS`, `stored_settings`,
  `update_settings`), `api.bootstrap` und `api/services.py`
  (`upload_sar_file`, `delete_sar_file`, `list_sar_files`, `file_info`,
  `load_df`, `resolve_header`, `user_dir`, `EXCLUDED_UPLOAD_DIRS`,
  `DEFAULT_OVERVIEW_ALIASES`, `ServiceError` – und die **privaten**
  `_parse_bound`, `_validate_file_name`, `_CPU_LIKE`). Umbenennen oder
  Signaturen ändern bricht das Web-Backend.
- Neue Settings in `EDITABLE_SETTINGS` erscheinen im Web-Frontend erst, wenn
  dessen Settings-Seite sie einer Gruppe zuordnet.
- Nach einem Update dieses Repos auf dem Lab-Server startet
  `deployment/lab/deploy.sh` sar-web-api mit neu (`try-restart`).
- Die Tests von sarfile_analyzer_web (`backend/`, pytest) laufen gegen den
  Checkout dieses Repos und prüfen, dass die Seed-`data.db` unverändert
  bleibt – ein guter Gegencheck nach Änderungen hier.

## 9. Lab-Deployment dus-lab-sar

- Server `dus-lab-sar.lab.dus.suse.com` (SLES 15, nur VPN), User `jschaef`,
  Checkout `~/data1/sarfile_analyzer_ng`, venv `code/venv` (Python 3.12).
- Dienste:
  - `:443` System-nginx → `127.0.0.1:8501` Streamlit
    (`sarfile-analyzer.service`, root-Unit mit `User=jschaef`, in `screen`,
    `PrivateTmp=true`)
  - `:8443` Caddy (rootless Podman-Quadlet) → `127.0.0.1:8100` API
    (`sar-api.service`, User-Unit, `PrivateTmp=true`)
  - `:9443` Caddy → `127.0.0.1:8200` MCP (`sar-mcp.service`), statisches
    Bearer-Gate `SAR_MCP_GATE_TOKEN`
  - `:8444` nginx → Web-Frontend (Repo sarfile_analyzer_web, eigenes
    `deployment/lab/`)
  - `redis@sar-crafter.service`
- Update: `~/data1/sarfile_analyzer_ng/deployment/lab/deploy.sh` (pull, pip,
  Env-Dateien falls fehlend, `mcp-agent`, Seed-Pflege, Units, Caddy, Linger,
  Health-Check). Streamlit startet es **nicht** neu: nach Code-Änderungen in
  `code/` → `sudo systemctl restart sarfile-analyzer`.
- **`code/data.db` ist skip-worktree-geschützt** (echte Benutzer). Vor einem
  Pull prüfen, ob neue Commits sie berühren
  (`git fetch && git diff --name-only HEAD origin/main`); nie
  `git checkout code/data.db` ohne Sicherung. `config.py` ist seit
  21.10.2026 ungeschützt.
- Gesetzte Settings: `admin_email` = `jochen.schaefer@suse.com`,
  `web_frontend_url` = `https://dus-lab-sar.lab.dus.suse.com:8444`,
  `streamlit_url` = `https://dus-lab-sar.lab.dus.suse.com`.
- Secrets unter `~/.config/sar-analyzer/` (`api.env`, `mcp.env`,
  `caddy.env`, `web.env`), alle 0600. Backup: produktive `data.db`, diese
  Env-Dateien, Caddy-Zertifikat, `code/upload/config/settings.json`.
- **Firefox-Profile**: der Driver-Pool beendet seine Treiber nie;
  `PrivateTmp=true` verhindert, dass pro Neustart ~80 MB
  `/tmp/rust_mozprofile*` liegen bleiben.
- `deploy.sh` gibt am Ende das MCP-Gate-Token aus – es landet leicht in
  Logs oder Chats.
- Vollständig: `deployment/lab/README-lab.md`.

## 10. Prüfen und Testen

- Es gibt **keine Tests, keine CI und keine Lint-Konfiguration** in diesem
  Repo (nur `vulture` in den requirements, ohne Config). Manuelle Smoke-
  Skripte: `deployment/lab/mcp_smoke_lab.py`, `deployment/lab/sso_demo.py`.
- Praktische Prüfung nach Änderungen:
  - Python-Syntax/Import: `python -c 'import config'` usw. im venv aus `code/`
  - Streamlit aus einer **Kopie** von `code/` starten (dann findet `find_db`
    die kopierte `data.db`), z. B. mit eigenem `UPLOAD_DIR` und
    `REDIS_ENABLED=false`, und im Browser bzw. mit Playwright prüfen
  - die pytest-Suite von sarfile_analyzer_web (`backend/`) gegen diesen
    Checkout laufen lassen
  - hinterher `git diff --quiet HEAD -- code/data.db` (Seed unverändert)
- Testdaten erzeugt `scripts/generate_sar.py` im Web-Repo.

## 11. Abhängigkeiten und Versionen

- `code/requirements.txt`: gepinnt altair 6.0.0, bokeh 3.8.2, connectorx
  0.4.5, redis 7.1.0, geckodriver-autoinstaller 0.1.0; **ungepinnt**
  streamlit, polars, pandas, selenium, SQLAlchemy, streamlit-bokeh,
  streamlit-option-menu, vl-convert-python, pypdf, python-magic u. a.
- Python ≥ 3.10 (`X | None`); Lab 3.12, Docker 3.12, Devcontainer 3.11.
- Streamlit-Updates brechen gern Styling/Komponenten: `style.css` enthält
  Kommentare zu 1.62/1.63, Multiselects nutzen `wrap=True`; nach einem Pull
  ggf. `pip install -U streamlit`.
- `code/.streamlit/config.toml`: u. a. `maxUploadSize 600`; hinter einem
  Proxy WebSocket-Upgrade und großes `client_max_body_size` nötig.

## 12. Verlauf (Auszug Oktober 2026)

- `7886b88` Benutzername `config` reserviert.
- `a5775fd` Laufzeit-Settings (`settings.json`, Metaklasse, Redis-Reconnect).
- `7752ac2` Lab-Doku: Kontaktadresse über `settings.json`, `config.py` nicht
  mehr geschützt.
- `5c5d1ca` Sidebar-Link zum Web-Frontend; `b89b968` `deploy.sh` startet
  sar-web-api mit; `036efd8` `streamlit_url`.
- `.mcp.json` mit cloud-memory wurde wieder entfernt – die Cloud-Umgebung
  stellt den Server selbst bereit.
