#!/usr/bin/env bash
# Rootless deployment of the SAR analyzer REST API + MCP server + Caddy TLS
# proxy on dus-lab-sar (SLES 15-SP6, podman 4.9). Idempotent: re-running
# updates code and restarts services; secrets are only generated when missing.
#
# Run as the app user (jschaef) from anywhere:
#   ~/data1/sarfile_analyzer_ng/deployment/lab/deploy.sh
#
# The ONLY root step (once) is copying the TLS certs, see README-lab.md:
#   sudo install -o jschaef -g users -m 644 \
#     /etc/nginx/ssl/dus-lab-sar.lab.dus.suse.com.crt.pem ~jschaef/sar-analyzer/certs/server.crt.pem
#   sudo install -o jschaef -g users -m 600 \
#     /etc/nginx/ssl/dus-lab-sar.lab.dus.suse.com.key.pem ~jschaef/sar-analyzer/certs/server.key.pem
set -euo pipefail

REPO="$HOME/data1/sarfile_analyzer_ng"
VENV="$REPO/code/venv"
CONF_DIR="$HOME/.config/sar-analyzer"
UNIT_DIR="$HOME/.config/systemd/user"
QUADLET_DIR="$HOME/.config/containers/systemd"
CADDY_DIR="$HOME/sar-analyzer"
MCP_USER="mcp-agent"

echo "== 1. update code =="
git -C "$REPO" pull --ff-only

echo "== 2. python deps =="
"$VENV/bin/pip" install -q -r "$REPO/api/requirements.txt" -r "$REPO/mcp_server/requirements.txt"

echo "== 3. secrets / env files =="
mkdir -p "$CONF_DIR" && chmod 700 "$CONF_DIR"
mkdir -p "$CADDY_DIR/certs"

if [ ! -f "$CONF_DIR/api.env" ]; then
    cat > "$CONF_DIR/api.env" <<EOF
SAR_API_SECRET=$(openssl rand -hex 32)
UPLOAD_DIR=$REPO/code/upload
EOF
    chmod 600 "$CONF_DIR/api.env"
    echo "created api.env"
fi

if [ ! -f "$CONF_DIR/mcp.env" ]; then
    cat > "$CONF_DIR/mcp.env" <<EOF
SAR_API_URL=http://127.0.0.1:8100
SAR_API_USERNAME=$MCP_USER
SAR_API_PASSWORD=$(openssl rand -hex 16)
SAR_MCP_HOST=127.0.0.1
SAR_MCP_PORT=8200
SAR_MCP_OUTPUT_DIR=$HOME/sar-mcp-output
EOF
    chmod 600 "$CONF_DIR/mcp.env"
    echo "created mcp.env"
fi

if [ ! -f "$CONF_DIR/caddy.env" ]; then
    cat > "$CONF_DIR/caddy.env" <<EOF
SAR_MCP_GATE_TOKEN=$(openssl rand -hex 32)
EOF
    chmod 600 "$CONF_DIR/caddy.env"
    echo "created caddy.env (MCP gate token)"
fi

echo "== 4. MCP service account ($MCP_USER, admin) =="
MCP_PASSWORD=$(grep '^SAR_API_PASSWORD=' "$CONF_DIR/mcp.env" | cut -d= -f2-)
(cd "$REPO/code" && "$VENV/bin/python" - "$MCP_USER" "$MCP_PASSWORD" <<'PYEOF'
import sys
import sql_stuff
user, password = sys.argv[1], sys.argv[2]
if user in sql_stuff.view_all_users(kind='x'):
    print(f"{user} exists")
else:
    sql_stuff.add_userdata(user, password, 'admin')
    print(f"{user} created (admin)")
PYEOF
)

echo "== 4b. seed maintenance (headings the server data.db may lack) =="
# Server data.db is skip-worktree-protected, so new seed rows from the repo
# never arrive via git pull - add them idempotently here.
(cd "$REPO/code" && "$VENV/bin/python" - <<'PYEOF'
import sql_stuff
sql_stuff.add_header(
    '%user %nice %system %iowait %steal %idle',
    'CPU utilization (short format, sar -u / sadf without -A)',
    'CPU', keywd='CPU')
print("short CPU header ensured")
PYEOF
)

echo "== 5. API + MCP user units =="
mkdir -p "$UNIT_DIR"
cp "$REPO/deployment/lab/sar-api.service" "$REPO/deployment/lab/sar-mcp.service" "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable sar-api.service sar-mcp.service >/dev/null 2>&1 || true
systemctl --user restart sar-api.service
sleep 2
systemctl --user restart sar-mcp.service

echo "== 6. Caddy (rootless podman quadlet) =="
cp "$REPO/deployment/lab/Caddyfile" "$CADDY_DIR/Caddyfile"
mkdir -p "$QUADLET_DIR"
cp "$REPO/deployment/lab/sar-caddy.container" "$QUADLET_DIR/"
systemctl --user daemon-reload
if [ -f "$CADDY_DIR/certs/server.crt.pem" ] && [ -f "$CADDY_DIR/certs/server.key.pem" ]; then
    systemctl --user restart sar-caddy.service
    echo "caddy restarted"
else
    echo "!! certs missing in $CADDY_DIR/certs - run the sudo install commands"
    echo "!! from README-lab.md once, then: systemctl --user restart sar-caddy"
fi

echo "== 7. linger (boot persistence) =="
loginctl enable-linger "$USER" 2>/dev/null || true
loginctl show-user "$USER" -p Linger

echo "== 8. health check =="
sleep 2
curl -sf http://127.0.0.1:8100/api/v1/health && echo " api OK"
systemctl --user --no-pager status sar-api.service sar-mcp.service sar-caddy.service 2>/dev/null | grep -E "●|Active:" || true

echo
echo "MCP gate token (for clients): $(grep '^SAR_MCP_GATE_TOKEN=' "$CONF_DIR/caddy.env" | cut -d= -f2-)"
echo "Endpoints: https://dus-lab-sar.lab.dus.suse.com:8443/api/v1  |  :9443/mcp"
