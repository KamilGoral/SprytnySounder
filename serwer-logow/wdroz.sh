#!/usr/bin/env bash
# Wdrozenie skrzynki na logi na Hetznerze. Uruchamiac na serwerze jako root:
#   cd /root/sounder-wdrozenie && ./wdroz.sh
# Idempotentne — mozna puscic ponownie po kazdej zmianie app.py.
set -euo pipefail

KATALOG=/opt/sounder-logi

id -u sounder >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin sounder
mkdir -p "$KATALOG/dane"
install -m 644 app.py "$KATALOG/app.py"

[ -d "$KATALOG/.venv" ] || python3 -m venv "$KATALOG/.venv"
"$KATALOG/.venv/bin/pip" install -q --upgrade pip flask

printf 'SOUNDER_DIR=%s/dane\nSOUNDER_PORT=3401\n' "$KATALOG" > "$KATALOG/.env"
chown -R sounder:sounder "$KATALOG"

cat > /etc/systemd/system/sounder-logi.service <<'UNIT'
[Unit]
Description=SprytnySounder — skrzynka na logi ze sklepow
After=network.target

[Service]
Type=simple
User=sounder
Group=sounder
WorkingDirectory=/opt/sounder-logi
EnvironmentFile=/opt/sounder-logi/.env
ExecStart=/opt/sounder-logi/.venv/bin/python /opt/sounder-logi/app.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/sounder-logi/dane
SyslogIdentifier=sounder-logi

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now sounder-logi
systemctl restart sounder-logi
sleep 2
systemctl is-active --quiet sounder-logi || { journalctl -u sounder-logi -n 20 --no-pager; exit 1; }

python3 nginx-wpis.py

echo "--- test lokalny ---"
curl -s -m 5 http://127.0.0.1:3401/zdrowie; echo
curl -s -m 5 -o /dev/null -w 'POST bez identyfikatora: %{http_code} (oczekiwane 400)\n' \
     -X POST -H 'Content-Type: application/json' -d '{"sklep":"test"}' http://127.0.0.1:3401/raport
echo "OK - skrzynka dziala na 127.0.0.1:3401, publicznie /sounder/ (tylko POST)"
