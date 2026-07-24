#!/usr/bin/env python3
"""Replay the platform SSO flow end to end (what the colleague's app does).

Does exactly the three documented steps: fetch tokens, upload files in the
user's context, print the ready-to-open redirect URL.

    export SAR_SSO_SECRET=$(ssh jschaef@dus-lab-sar.lab.dus.suse.com \
        'grep ^SAR_SSO_SECRET= ~/.config/sar-analyzer/api.env | cut -d= -f2-')
    export SSL_CERT_FILE=$HOME/certs/premium-support-dus-ca.pem

    ./sso_demo.py --user alice@example.com ~/Downloads/sar/sar20260714.json
    ./sso_demo.py --user alice@example.com --open file1.json file2.json.xz
    ./sso_demo.py --user alice@example.com --cleanup       # nur aufraeumen

VPN muss aktiv sein.
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

try:
    import httpx
except ImportError:
    sys.exit("httpx fehlt: pip install httpx")

DEFAULT_API = "https://dus-lab-sar.lab.dus.suse.com:8443/api/v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="SAR files (sar/sa/json/xz)")
    parser.add_argument("--user", required=True, help="platform username or e-mail")
    parser.add_argument("--api", default=os.getenv("SAR_API_URL", DEFAULT_API))
    parser.add_argument("--secret", default=os.getenv("SAR_SSO_SECRET", ""))
    parser.add_argument("--open", action="store_true", help="open the redirect URL")
    parser.add_argument(
        "--cleanup", action="store_true", help="delete the user's files afterwards"
    )
    args = parser.parse_args()

    if not args.secret:
        return int(bool(sys.stderr.write("SAR_SSO_SECRET fehlt (env oder --secret)\n")))

    api = args.api.rstrip("/")
    client = httpx.Client(timeout=600.0)

    # --- Schritt 1: Tokens holen (Server-zu-Server) ----------------------
    response = client.post(
        f"{api}/sso/token",
        headers={"X-SSO-Secret": args.secret},
        json={"username": args.user},
    )
    if response.status_code != 200:
        print(f"[1] /sso/token fehlgeschlagen: {response.status_code} {response.text}")
        return 1
    sso = response.json()
    api_token = sso["api_token"]["access_token"]
    print(f"[1] Token fuer {sso['username']} (neu angelegt: {sso['provisioned']})")

    auth = {"Authorization": f"Bearer {api_token}"}

    # --- Schritt 2: Upload im Benutzerkontext ---------------------------
    uploaded: list[str] = []
    if args.files:
        payload = []
        handles = []
        for path in args.files:
            handle = open(Path(path).expanduser(), "rb")
            handles.append(handle)
            payload.append(("files", (Path(path).name, handle, "application/octet-stream")))
        response = client.post(f"{api}/files", headers=auth, files=payload)
        for handle in handles:
            handle.close()
        if response.status_code >= 400:
            print(f"[2] Upload fehlgeschlagen: {response.status_code} {response.text}")
            return 1
        body = response.json()
        for entry in body["uploaded"]:
            uploaded.append(entry["name"])
            note = f" ({'; '.join(entry['warnings'])})" if entry["warnings"] else ""
            print(f"[2] hochgeladen: {entry['name']} "
                  f"- {entry['rows']} Zeilen, {entry['headers']} Header{note}")
        for entry in body.get("errors", []):
            print(f"[2] FEHLER {entry['file']}: {entry['detail']}")
    else:
        print("[2] keine Dateien angegeben - Upload uebersprungen")

    # --- Schritt 3: Redirect-URL bauen ----------------------------------
    redirect = sso["ui_redirect_url"]
    if uploaded:
        redirect += f"&file={quote(uploaded[0])}"
    print(f"\n[3] Redirect-URL (einmalig gueltig, 15 min):\n{redirect}\n")
    if args.open:
        webbrowser.open(redirect)
        print("    -> im Browser geoeffnet")

    if args.cleanup:
        for name in uploaded:
            client.delete(f"{api}/files/{quote(name)}", headers=auth)
            print(f"[cleanup] geloescht: {name}")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
