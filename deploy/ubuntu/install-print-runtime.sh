#!/usr/bin/env bash
set -euo pipefail

root=/opt/kiscobooks/current

# A renderer never receives the interactive API's environment or OS identity.
if ! id -u kisco-print >/dev/null 2>&1; then
  getent group kisco-print >/dev/null || groupadd --system kisco-print
  useradd --system --no-create-home --home-dir /var/lib/kiscobooks-print \
    --shell /usr/sbin/nologin --gid kisco-print kisco-print
fi
# Only directory traversal is needed to read the deployed code. Do not add the
# renderer to the kiscobooks group, which can read interactive API env files.
chmod o+x /opt/kiscobooks

"$root/apis/vouchers/.venv/bin/python" "$root/deploy/ubuntu/configure-purchase-print.py" --repair-storage

# Default ACLs survive newly created tenant/company/voucher directories. The
# renderer stays outside the API group and cannot read the API's env files.
DEBIAN_FRONTEND=noninteractive apt-get install -y acl >/dev/null
find /var/lib/kiscobooks-print/pdfs -type d -exec setfacl -m g:kiscobooks:rx -m d:g:kiscobooks:rx {} +
find /var/lib/kiscobooks-print/pdfs -type f -exec setfacl -m g:kiscobooks:r-- {} +

# The browser and its Linux dependencies are part of the deployed runtime. Keep
# Playwright's versioned browser cache outside a login home and the public tree.
PLAYWRIGHT_BROWSERS_PATH=/var/lib/kiscobooks-print/browsers \
  "$root/apis/vouchers/.venv/bin/python" -m playwright install --with-deps chromium
chown -R root:kisco-print /var/lib/kiscobooks-print/browsers
chmod -R o-rwx /var/lib/kiscobooks-print/browsers

# Ubuntu 24.04 restricts unprivileged user namespaces. Permit only the
# root-owned Playwright binaries to start Chromium's own sandbox; keep the
# browser cache unwritable by the worker so this allowance cannot be replaced.
cat >/etc/apparmor.d/kiscobooks-purchase-print-chromium <<'EOF'
abi <abi/4.0>,
include <tunables/global>

profile kiscobooks-print-headless /var/lib/kiscobooks-print/browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell flags=(unconfined) {
  userns,
}

profile kiscobooks-print-chromium /var/lib/kiscobooks-print/browsers/chromium-*/chrome-linux64/chrome flags=(unconfined) {
  userns,
}
EOF
apparmor_parser -r /etc/apparmor.d/kiscobooks-purchase-print-chromium

for role in dispatcher worker; do
  argument=
  [ "$role" = worker ] && argument=--worker
  cat >"/etc/systemd/system/kiscobooks-vouchers-print-${role}.service" <<EOF
[Unit]
Description=KiscoBooks Purchase PDF ${role}
After=network-online.target mysql.service rabbitmq-server.service
Wants=network-online.target mysql.service rabbitmq-server.service

[Service]
Type=simple
User=kisco-print
Group=kisco-print
WorkingDirectory=/opt/kiscobooks/current
EnvironmentFile=/etc/kiscobooks/vouchers-print.env
ExecStart=/opt/kiscobooks/current/apis/vouchers/.venv/bin/python -m vouchers.tasks.print_dispatcher ${argument}
Restart=on-failure
RestartSec=5
TimeoutStopSec=35
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/kiscobooks-print/pdfs
LimitNOFILE=32768

[Install]
WantedBy=multi-user.target
EOF
done

cat >/etc/systemd/system/kiscobooks-vouchers-print-enrollment.service <<'EOF'
[Unit]
Description=Enroll newly provisioned companies for Purchase printing
After=mysql.service rabbitmq-server.service
Wants=mysql.service rabbitmq-server.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/kiscobooks/current
ExecStart=/opt/kiscobooks/current/apis/vouchers/.venv/bin/python /opt/kiscobooks/current/deploy/ubuntu/configure-purchase-print.py --restart
TimeoutStartSec=90
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/etc/kiscobooks /var/lib/kiscobooks-print
EOF

cat >/etc/systemd/system/kiscobooks-vouchers-print-enrollment.timer <<'EOF'
[Unit]
Description=Keep Purchase print scopes aligned with enrolled companies

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
Persistent=true
Unit=kiscobooks-vouchers-print-enrollment.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable kiscobooks-vouchers-print-dispatcher.service kiscobooks-vouchers-print-worker.service kiscobooks-vouchers-print-enrollment.timer
systemctl restart kiscobooks-api@design.service kiscobooks-api@vouchers.service
systemctl restart kiscobooks-vouchers-print-dispatcher.service kiscobooks-vouchers-print-worker.service
systemctl start kiscobooks-vouchers-print-enrollment.timer
systemctl is-active --quiet kiscobooks-vouchers-print-dispatcher.service
systemctl is-active --quiet kiscobooks-vouchers-print-worker.service
