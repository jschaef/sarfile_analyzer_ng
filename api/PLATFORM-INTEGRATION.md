# SAR Analyzer — Integration für externe Plattformen

Diese Anleitung beschreibt, wie eine Anwendung, die ihre Benutzer **selbst**
authentifiziert, SAR-Dateien im Kontext dieser Benutzer in den SAR Analyzer
hochlädt und den Benutzer anschließend **bereits eingeloggt** in die
Analyzer-Weboberfläche weiterleitet.

- **API-Basis:** `https://dus-lab-sar.lab.dus.suse.com:8443/api/v1`
- **Web-UI:** `https://dus-lab-sar.lab.dus.suse.com`
- **Netz:** nur über das Firmen-VPN erreichbar
- **TLS:** internes Zertifikat der „Premium Support DUS CA". Die CA-Datei
  `premium-support-dus-ca.pem` muss dem HTTP-Client bekannt sein
  (Python: `SSL_CERT_FILE`, Node: `NODE_EXTRA_CA_CERTS`, curl: `--cacert`).
- **Secret:** Der Wert für `X-SSO-Secret` wird separat übergeben. Er ist ein
  reines Server-zu-Server-Geheimnis und darf **nie** in einen Browser,
  JavaScript-Code oder Logs gelangen.

---

## Ablauf in drei Schritten

```
1. POST /sso/token   {username}        →  api_token (24 h)  +  ui_redirect_url
2. POST /files       mit api_token     →  name der gespeicherten Datei
3. Browser-Redirect auf ui_redirect_url + "&file=" + name
```

---

## Schritt 1 — Token holen (Server-zu-Server)

```http
POST /api/v1/sso/token
X-SSO-Secret: <geheim>
Content-Type: application/json

{"username": "alice@example.com"}
```

Antwort `200`:

```json
{
  "username": "alice@example.com",
  "provisioned": true,
  "api_token": {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_at": 1784964790
  },
  "ui_redirect_url": "https://dus-lab-sar.lab.dus.suse.com/?sso_token=...",
  "ui_token_expires_at": 1784878570
}
```

**Benutzernamen** dürfen einfache Logins oder E-Mail-Adressen sein. Erlaubt
sind `A-Z a-z 0-9 . _ @ + -`, das erste Zeichen muss alphanumerisch sein,
Mindestlänge 2.

**Es gibt keinen Fehlerfall „Benutzer unbekannt".** Existiert der Benutzer im
Analyzer noch nicht, wird er automatisch angelegt (Rolle `user`) — erkennbar
an `"provisioned": true`. Er kann sich später auch klassisch über das
Login-Formular anmelden (Default-Passwort auf Anfrage).

| Fehler | HTTP | Bedeutung |
|---|---|---|
| `Invalid SSO secret` | 401 | `X-SSO-Secret` fehlt oder falsch |
| Validierungsfehler | 422 | Benutzername verletzt das erlaubte Format |
| `SSO is not configured` | 503 | Serverseitig kein Secret gesetzt |

Die beiden Tokens haben unterschiedliche Zwecke und sind **nicht**
austauschbar:

| Token | Gültigkeit | Verwendung |
|---|---|---|
| `api_token` | 24 h | alle API-Aufrufe (`Authorization: Bearer …`) |
| `sso_token` in der Redirect-URL | 15 min, **einmalig** | nur der Browser-Redirect |

---

## Schritt 2 — Dateien hochladen

**Kein base64.** Ganz normaler `multipart/form-data`-Upload mit Rohbytes.
Das Formularfeld heißt **`files`** und darf für Bulk-Uploads mehrfach
vorkommen.

```http
POST /api/v1/files
Authorization: Bearer <api_token>
Content-Type: multipart/form-data
```

Akzeptierte Formate — die Erkennung erfolgt über den **Dateiinhalt**, nicht
über die Endung:

| Format | Beispiel | Behandlung |
|---|---|---|
| SAR-ASCII (`sar -A -t`) | `sar20260714` | direkt |
| SAR-Binär | `sa20260714` | serverseitig via `sar -A -t -f` konvertiert |
| sadf-JSON | `sar20260714.json` | in SAR-Text konvertiert |
| alle obigen als xz | `sar20260714.json.xz` | entpackt, dann wie oben |

### Wichtig: JSON richtig exportieren

```bash
sadf -j <sa-datei> -- -A > report.json
```

**`-- -A`** reicht „alle Aktivitäten" an sar durch. Fehlt es, exportiert
`sadf -j` **nur die CPU-Auslastung** — im Analyzer taucht dann bloß eine
einzige Sektion auf. Das ist der häufigste Grund für einen scheinbar leeren
Report.

**Zeitzone:** Die Zeitstempel werden genommen, wie sie im JSON stehen. Ohne
`-t` schreibt sadf UTC — für Hosts, die in UTC laufen, ist das genau richtig.
`-t` ist nur nötig, wenn der Quell-Host eine lokale Zeitzone verwendet und
diese Wanduhrzeit auf der Achse erscheinen soll.

Antwort `201`:

```json
{
  "uploaded": [
    {
      "name": "2026-07-24_hec45v197914_2026-07-14",
      "rows": 134,
      "headers": 1,
      "warnings": ["sar20260714: converted from sadf JSON"]
    }
  ],
  "errors": []
}
```

**`name` ist der wichtigste Rückgabewert.** Jede Datei wird nach dem Muster
`<Upload-Datum>_<Hostname>_<SAR-Datum>` umbenannt (Hostname und Datum stammen
aus dem Dateiinhalt). Genau dieser Name wird in Schritt 3 gebraucht.

Schlägt bei einem Bulk-Upload nur ein Teil fehl, kommt trotzdem `201` und die
fehlgeschlagenen Dateien stehen in `errors`. Scheitern **alle**, ist der
Status `400`.

### Beispiel: Bulk-Upload mehrerer Dateien

curl:

```bash
curl -X POST https://dus-lab-sar.lab.dus.suse.com:8443/api/v1/files \
  --cacert premium-support-dus-ca.pem \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "files=@sar20260714.json.xz" \
  -F "files=@sar20260715.json" \
  -F "files=@sa20260716"
```

Python (`requests`) — mehrere Einträge mit demselben Feldnamen `files`:

```python
import requests

files = [
    ("files", ("sar20260714.json.xz", open("sar20260714.json.xz", "rb"),
               "application/octet-stream")),
    ("files", ("sar20260715.json", open("sar20260715.json", "rb"),
               "application/json")),
    ("files", ("sa20260716", open("sa20260716", "rb"),
               "application/octet-stream")),
]
response = requests.post(
    "https://dus-lab-sar.lab.dus.suse.com:8443/api/v1/files",
    headers={"Authorization": f"Bearer {api_token}"},
    files=files,
    verify="premium-support-dus-ca.pem",
    timeout=600,
)
names = [entry["name"] for entry in response.json()["uploaded"]]
```

Java / Spring (`WebClient`), zur Orientierung:

```java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("files", new FileSystemResource("sar20260714.json.xz"));
builder.part("files", new FileSystemResource("sar20260715.json"));
```

---

## Schritt 3 — Benutzer weiterleiten (mit vorausgewählter Datei)

Die `ui_redirect_url` aus Schritt 1 wird um den Dateinamen ergänzt:

```
<ui_redirect_url>&file=2026-07-24_hec45v197914_2026-07-14
```

Der `file`-Parameter ist **nicht** Teil des signierten Tokens und darf deshalb
nachträglich angehängt werden (URL-kodieren nicht vergessen). Wirkung im
Analyzer: Der Benutzer ist eingeloggt, landet direkt in **„Analyze Data →
Graphical Overview"**, und unter **„Choose your Sar File"** ist die
übergebene Datei bereits ausgewählt. Existiert die Datei für diesen Benutzer
nicht, wird der Parameter ignoriert und die Standardauswahl gezeigt.

Der Analyzer entfernt das Token sofort aus der Adresszeile. Ein zweiter
Aufruf desselben Links zeigt „SSO token already used" und das normale
Login-Formular — das ist beabsichtigt.

### Timing

Das `sso_token` lebt **15 Minuten** und ist einmalig. Liegt zwischen Schritt 1
und Schritt 3 ein sehr langer Upload, ruft die Plattform `/sso/token` einfach
**direkt vor dem Redirect** noch einmal auf (dann gleich mit `"file": "<name>"`
im Body, dann muss nichts angehängt werden). Der `api_token` bleibt davon
unberührt und kann 24 h lang für alle Uploads wiederverwendet werden.

---

## Was die Plattform sonst noch abfragen kann

Mit dem `api_token` stehen alle regulären Endpunkte im Kontext des Benutzers
offen, unter anderem:

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/files` | Dateien des Benutzers auflisten |
| GET | `/files/{name}` | OS-Details, Zeitraum, Header und Metriken |
| GET | `/files/{name}/statistics?header=CPU` | Statistiken als JSON/CSV |
| POST | `/charts/single` | Diagramm als PNG/PDF |
| DELETE | `/files/{name}` | Datei löschen |

Vollständige, interaktive Referenz: `https://dus-lab-sar.lab.dus.suse.com:8443/docs`
