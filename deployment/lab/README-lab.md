# Lab-Deployment dus-lab-sar — API + MCP (rootless)

Rootless Betrieb von REST-API (uvicorn, `127.0.0.1:8100`), MCP-Server
(Streamable HTTP, `127.0.0.1:8200`) und Caddy-TLS-Proxy (podman quadlet,
`:8443` API / `:9443` MCP) als User `jschaef`. Die Streamlit-UI und der
System-nginx (`:443`) bleiben unangetastet.

## Architektur

```
Client (VPN) ── https://dus-lab-sar.lab.dus.suse.com
   :443  nginx (root, unverändert)  → 127.0.0.1:8501  Streamlit-UI
   :8443 caddy (rootless podman)    → 127.0.0.1:8100  REST-API (eigene Token-Auth)
   :9443 caddy (rootless podman)    → 127.0.0.1:8200  MCP (statisches Bearer-Gate)
```

MCP → API läuft lokal über `127.0.0.1:8100` mit dem Service-Account
`mcp-agent` (admin, wird vom Deploy-Skript angelegt).

### System-nginx (Web-UI, root-verwaltet, unabhängig von diesem Deploy)

Die Streamlit-Web-UI läuft weiter über den System-nginx auf `:443` — separat
vom rootless Caddy (der nur `:8443`/`:9443` bedient). Config:
`/etc/nginx/conf.d/sarfile-analyzer.conf`, Referenzkopie im Repo:
[`nginx-sarfile-analyzer-ui.conf`](nginx-sarfile-analyzer-ui.conf). Ein
`server`-Block, `:443 ssl` → `proxy_pass http://127.0.0.1:8501` mit
WebSocket-Upgrade (für Streamlit nötig) und `client_max_body_size 2048M` (große
SAR-Uploads über die UI). Eigenes nginx-Cert unter `/etc/nginx/ssl/`
(unabhängig vom root-signierten Caddy-Cert). Kein Port-80-Redirect. Änderungen
als root: `sudo nginx -t && sudo systemctl reload nginx`.

## Deployment / Update (rootless, idempotent)

```bash
ssh jschaef@dus-lab-sar.lab.dus.suse.com
~/data1/sarfile_analyzer_ng/deployment/lab/deploy.sh
```

Das Skript: `git pull` → pip-Deps → Secrets/Env-Dateien (nur falls fehlend)
→ `mcp-agent` anlegen → user-Units `sar-api`/`sar-mcp` → Caddy-Quadlet →
Linger → Health-Check. Am Ende gibt es das MCP-Gate-Token aus.

## Einmalige Root-Schritte

Caddy braucht ein eigenes Server-Zertifikat unter
`~/sar-analyzer/certs/server.{crt,key}.pem`. Aktuell liegt dort ein
**direkt von der Root-CA** signiertes Leaf-Zertifikat (SAN
`DNS:dus-lab-sar.lab.dus.suse.com, IP:10.156.60.24`, mit AKI, strict-clean):

- `server.crt.pem` = **nur das Leaf** (keine Fullchain — die Root ist der
  Vertrauensanker beim Client, es gibt keine Zwischen-CA).
- `server.key.pem` = passender Private Key, `chmod 600`.

Da root-signiert und strict-sauber, braucht der stdio-Client **kein**
`SAR_MCP_TLS_RELAX_STRICT`. Client-Trust weiterhin nur die Root-CA
(`premium-support-dus-ca.pem`).

Cert bauen (Extension-Datei mit `subjectAltName = @alt` /
`[alt]\nDNS.1=...\nIP.1=...`, dazu `authorityKeyIdentifier=keyid,issuer`,
`subjectKeyIdentifier=hash`, `basicConstraints=CA:FALSE`,
`extendedKeyUsage=serverAuth`), von der Root-CA signieren, dann nach
`~/sar-analyzer/certs/` kopieren und `systemctl --user restart sar-caddy`.
Prüfen: `openssl verify -x509_strict -verify_hostname dus-lab-sar.lab.dus.suse.com
-CAfile <root-ca> server.crt.pem` muss OK sein.

Frühere Variante (überholt): eine Kopie des nginx-Certs (`/etc/nginx/ssl`,
root-only) — die war von der Sub-CA signiert und **nicht** strict-clean
(basicConstraints nicht critical), daher der Relax-Workaround. Mit dem
root-signierten Cert entfällt das.

## Secrets (alle unter ~/.config/sar-analyzer/, chmod 600)

| Datei | Inhalt |
|---|---|
| `api.env` | `SAR_API_SECRET` (HMAC für API-Tokens), `UPLOAD_DIR` |
| `mcp.env` | API-URL + `mcp-agent`-Credentials, MCP-Host/Port, Output-Dir |
| `caddy.env` | `SAR_MCP_GATE_TOKEN` (statisches Bearer-Gate am :9443) |

Anzeigen: `grep SAR_MCP_GATE_TOKEN ~/.config/sar-analyzer/caddy.env`

## Reboot-Persistenz (was startet nach einem Neustart automatisch)

Zwei Ebenen, beide aktiv:

**System-Units (root, `systemctl is-enabled` = enabled):**

| Unit | Zweck | Repo-Referenz |
|---|---|---|
| `sarfile-analyzer.service` | Streamlit-UI via `screen` → `127.0.0.1:8501`, `Restart=always`, `WantedBy=multi-user.target` | [`sarfile-analyzer.service`](sarfile-analyzer.service) |
| `nginx.service` | Reverse Proxy `:443` → 8501 | [`nginx-sarfile-analyzer-ui.conf`](nginx-sarfile-analyzer-ui.conf) |
| `redis@sar-crafter.service` | Redis-Cache (Parquet), von der App genutzt | — |

**User-Units (rootless `jschaef`, laufen nach Reboot dank `Linger=yes`):**

| Unit | Zustand | Autostart über |
|---|---|---|
| `sar-api.service` | enabled | `WantedBy=default.target` |
| `sar-mcp.service` | enabled | `WantedBy=default.target` |
| `sar-caddy.service` | `generated` (normal für Quadlets) | `[Install] WantedBy=default.target` im `.container` |

Voraussetzung für die User-Ebene: `loginctl show-user jschaef -p Linger` = `yes`
(sonst laufen die User-Units erst beim nächsten Login an, nicht beim Boot).
`deploy.sh` setzt Linger idempotent.

Prüfen nach einem Reboot:
```bash
systemctl is-active sarfile-analyzer nginx redis@sar-crafter
systemctl --user is-active sar-api sar-mcp sar-caddy
```

## Backup (was für einen vollständigen Wiederaufbau gesichert sein muss)

Der Code + `deployment/lab/` liegen in Git. Wichtig zu `data.db`: die im Repo
versionierte `code/data.db` ist ein **Seed** (nur `admin` + 39 Headings + 294
Metrics, keine anderen Benutzer). Auf dem Server enthält `data.db` die **echten
Benutzer** und ist mit `git update-index --skip-worktree code/data.db`
geschützt, damit `git pull` sie nie überschreibt — diese produktive `data.db`
gehört ins Backup (das Repo-Seed reicht dafür nicht).

Was ins Backup gehört (nicht bzw. nur als Seed in Git):

| Pfad | Inhalt | Im DR ohne Backup |
|---|---|---|
| `~/data1/sarfile_analyzer_ng/code/data.db` | **echte Analyzer-Benutzer** (userstable) | Repo-Checkout liefert nur `admin` + Metadaten; `deploy.sh` ergänzt `mcp-agent` — alle anderen Benutzer wären weg |
| `~/.config/sar-analyzer/*.env` | Secrets (API-HMAC, mcp-agent-Pw, Gate-Token) | `deploy.sh` erzeugt neue → alle Client-Tokens neu verteilen |
| `~/sar-analyzer/certs/server.{crt,key}.pem` | TLS-Cert/Key (root-signiert) | neu von der Root-CA ausstellen (Rezept: `sar-cert-root-signiert`) |
| `~/data1/sarfile_analyzer_ng/code/upload/<user>/` | hochgeladene SAR-Dateien + Parquet | Nutzerdaten, erneut hochladbar |

Mindest-Backup für schmerzfreien Wiederaufbau: die produktive **`data.db`** und
**`~/.config/sar-analyzer/`**. (Header-/Metrik-Metadaten kommen notfalls aus dem
Repo-Seed, die echten Benutzer nur aus dem Backup.)

## Client-Zugriff (VPN nötig)

- API: `https://dus-lab-sar.lab.dus.suse.com:8443/api/v1/...`
  (Login `POST /token` mit Analyzer-Benutzer)
- MCP: `https://dus-lab-sar.lab.dus.suse.com:9443/mcp`
  mit Header `Authorization: Bearer <SAR_MCP_GATE_TOKEN>`
- TLS: Server liefert das interne Cert; Clients brauchen die CA
  (`~/certs/premium-support-dus-ca.pem` auf dem Mac):
  Python `SSL_CERT_FILE=...`, Node/Claude `NODE_EXTRA_CA_CERTS=...`

Claude-Code-Beispiel:

```bash
claude mcp add --transport http sar-analyzer https://dus-lab-sar.lab.dus.suse.com:9443/mcp --header "Authorization: Bearer <TOKEN>"
```

## Desaster-Recovery (Neuaufbau von Null)

1. VM mit SLES 15-SP6+, User jschaef, podman, git, python3.12
2. `git clone git@github.com:jschaef/sarfile_analyzer_ng.git ~/data1/sarfile_analyzer_ng`
3. `cd ~/data1/sarfile_analyzer_ng/code && python3.12 -m venv venv && venv/bin/pip install -r requirements.txt`
4. `data.db`: der Checkout bringt den Seed (admin + Headings + Metrics) mit.
   Für die echten Benutzer die produktive `data.db` aus dem Backup einspielen und
   auf dem Server `git update-index --skip-worktree code/data.db` setzen
5. Streamlit-UI (unabhängig von API/MCP): System-Unit + nginx-Vhost als root
   installieren — `sudo cp deployment/lab/sarfile-analyzer.service /etc/systemd/system/`,
   `sudo cp deployment/lab/nginx-sarfile-analyzer-ui.conf /etc/nginx/conf.d/sarfile-analyzer.conf`,
   nginx-Cert unter `/etc/nginx/ssl/` bereitstellen, dann
   `sudo systemctl enable --now sarfile-analyzer`, `sudo nginx -t && sudo systemctl reload nginx`,
   `sudo systemctl enable --now redis@sar-crafter`
6. TLS-Cert für Caddy nach `~/sar-analyzer/certs/server.{crt,key}.pem` (aus Backup
   oder neu von der Root-CA, Rezept: concepts `sar-cert-root-signiert`)
7. `deployment/lab/deploy.sh` ausführen (Secrets aus Backup wiederherstellen ODER
   neu erzeugen lassen → dann neue Tokens an Clients verteilen; setzt Linger, startet
   user-Units + Caddy)
8. Test: `curl https://…:8443/api/v1/health` + MCP-Smoke (`deployment/lab/mcp_smoke_lab.py`)

## Troubleshooting

```bash
systemctl --user status sar-api sar-mcp sar-caddy
journalctl --user -u sar-api -n 50
podman logs systemd-sar-caddy | tail -20
```

- Bokeh-PNG/PDF braucht Firefox auf dem Host (vorhanden) — Fallback Chrome
- `GET /mcp` antwortet absichtlich 405 (kein Idle-SSE-Stream, VPN/NAT)
- MCP-Client-Fehler 401 → Gate-Token prüfen; 502 → `sar-mcp` down
