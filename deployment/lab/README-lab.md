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

## Deployment / Update (rootless, idempotent)

```bash
ssh jschaef@dus-lab-sar.lab.dus.suse.com
~/data1/sarfile_analyzer_ng/deployment/lab/deploy.sh
```

Das Skript: `git pull` → pip-Deps → Secrets/Env-Dateien (nur falls fehlend)
→ `mcp-agent` anlegen → user-Units `sar-api`/`sar-mcp` → Caddy-Quadlet →
Linger → Health-Check. Am Ende gibt es das MCP-Gate-Token aus.

## Einmalige Root-Schritte

Nur die TLS-Zertifikate (Key unter `/etc/nginx/ssl` ist root-only):

```bash
sudo install -o jschaef -g users -m 644 /etc/nginx/ssl/dus-lab-sar.lab.dus.suse.com.crt.pem /home/jschaef/sar-analyzer/certs/server.crt.pem
sudo install -o jschaef -g users -m 600 /etc/nginx/ssl/dus-lab-sar.lab.dus.suse.com.key.pem /home/jschaef/sar-analyzer/certs/server.key.pem
```

Danach `systemctl --user restart sar-caddy` (bzw. `deploy.sh` erneut).
Bei Cert-Erneuerung des nginx-Certs die Kopie manuell nachziehen — sie
wird NICHT automatisch aktualisiert.

## Secrets (alle unter ~/.config/sar-analyzer/, chmod 600)

| Datei | Inhalt |
|---|---|
| `api.env` | `SAR_API_SECRET` (HMAC für API-Tokens), `UPLOAD_DIR` |
| `mcp.env` | API-URL + `mcp-agent`-Credentials, MCP-Host/Port, Output-Dir |
| `caddy.env` | `SAR_MCP_GATE_TOKEN` (statisches Bearer-Gate am :9443) |

Anzeigen: `grep SAR_MCP_GATE_TOKEN ~/.config/sar-analyzer/caddy.env`

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
4. Streamlit-UI wie gehabt (System-Unit `sarfile-analyzer.service` + nginx-Vhost, siehe Repo-README) — unabhängig von API/MCP
5. `deployment/lab/deploy.sh` ausführen (erzeugt alle Secrets neu → neue Tokens an Clients verteilen; `data.db` mit Benutzern ggf. aus Backup, sonst legt das Skript `mcp-agent` neu an)
6. Root: Cert-Kopie (oben), dann `systemctl --user restart sar-caddy`
7. Test: `curl https://.../8443/api/v1/health` + MCP-Smoke (unten)

## Troubleshooting

```bash
systemctl --user status sar-api sar-mcp sar-caddy
journalctl --user -u sar-api -n 50
podman logs systemd-sar-caddy | tail -20
```

- Bokeh-PNG/PDF braucht Firefox auf dem Host (vorhanden) — Fallback Chrome
- `GET /mcp` antwortet absichtlich 405 (kein Idle-SSE-Stream, VPN/NAT)
- MCP-Client-Fehler 401 → Gate-Token prüfen; 502 → `sar-mcp` down
