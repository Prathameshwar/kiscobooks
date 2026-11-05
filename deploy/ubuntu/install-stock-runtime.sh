#!/usr/bin/env bash
set -euo pipefail

root=/opt/kiscobooks/current
# Run on fresh installations and upgrades. Preserve existing paired secrets and
# explicit activation choices while enabling posting for new installations.
python3 "$root/deploy/ubuntu/enable-stock-posting.py"

for worker in vouchers-sources vouchers-executions accounting-posting-delivery; do
  service=vouchers
  module=vouchers.tasks.source_worker
  if [ "$worker" = vouchers-executions ]; then
    module=vouchers.tasks.execution_worker
  elif [ "$worker" = accounting-posting-delivery ]; then
    service=accounting
    module=accounting.tasks.posting_delivery
  fi
  cat >"/etc/systemd/system/kiscobooks-${worker}.service" <<EOF
[Unit]
Description=KiscoBooks ${worker}
After=network-online.target mysql.service kiscobooks-api@${service}.service
Wants=network-online.target

[Service]
Type=simple
User=kiscobooks
Group=kiscobooks
WorkingDirectory=/opt/kiscobooks/current
EnvironmentFile=/etc/kiscobooks/${service}.env
ExecStart=/opt/kiscobooks/current/apis/${service}/.venv/bin/python -m ${module}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/kiscobooks /var/log/kiscobooks

[Install]
WantedBy=multi-user.target
EOF
done

systemctl daemon-reload
systemctl enable kiscobooks-vouchers-sources.service kiscobooks-vouchers-executions.service kiscobooks-accounting-posting-delivery.service
systemctl restart kiscobooks-api@identity.service kiscobooks-api@catalog.service kiscobooks-api@accounting.service kiscobooks-api@vouchers.service
systemctl restart kiscobooks-vouchers-sources.service kiscobooks-vouchers-executions.service kiscobooks-accounting-posting-delivery.service
