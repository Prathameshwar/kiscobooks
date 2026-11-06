#!/usr/bin/env bash
set -euo pipefail

root=/opt/kiscobooks/current


install -d -m 755 /usr/local/libexec
cat >/usr/local/libexec/kiscobooks-api <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  identity) port=8001; module=identity.main:create_app ;;
  audit) port=8002; module=audit.main:create_app ;;
  catalog) port=8003; module=catalog.main:create_app ;;
  notification) port=8010; module=notification.main:create_app ;;
  accounting) port=8011; module=accounting.main:create_app ;;
  vouchers) port=8012; module=vouchers.main:create_app ;;
  reports) port=8013; module=reports.main:create_app ;;
  design) port=8014; module=design.main:create_app ;;
  *) exit 64 ;;
esac
cd /opt/kiscobooks/current
exec "apis/$1/.venv/bin/uvicorn" "$module" --factory --host 127.0.0.1 --port "$port" --proxy-headers --forwarded-allow-ips 127.0.0.1
EOF
chmod 755 /usr/local/libexec/kiscobooks-api

cat >/etc/systemd/system/kiscobooks-api@.service <<'EOF'
[Unit]
Description=KiscoBooks %i API
After=network-online.target mysql.service redis-server.service rabbitmq-server.service
Wants=network-online.target

[Service]
Type=simple
User=kiscobooks
Group=kiscobooks
WorkingDirectory=/opt/kiscobooks/current
EnvironmentFile=/etc/kiscobooks/%i.env
ExecStart=/usr/local/libexec/kiscobooks-api %i
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
LimitNOFILE=32768
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/kiscobooks /var/log/kiscobooks

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/kiscobooks-company-setup.service <<'EOF'
[Unit]
Description=KiscoBooks automatic company setup worker
After=network-online.target mysql.service kiscobooks-api@identity.service kiscobooks-api@catalog.service kiscobooks-api@accounting.service kiscobooks-api@vouchers.service kiscobooks-api@reports.service
Wants=network-online.target

[Service]
Type=simple
User=kiscobooks
Group=kiscobooks
WorkingDirectory=/opt/kiscobooks/current
EnvironmentFile=/etc/kiscobooks/identity.env
ExecStart=/opt/kiscobooks/current/apis/identity/.venv/bin/python -m identity.tasks.company_setup
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/kiscobooks /var/log/kiscobooks

[Install]
WantedBy=multi-user.target
EOF

for worker in identity-catalog-publisher catalog-source-worker; do
  service=identity
  module=identity.tasks.catalog_publisher
  if [ "$worker" = catalog-source-worker ]; then
    service=catalog
    module=catalog.tasks.source_worker
  fi
  cat >"/etc/systemd/system/kiscobooks-${worker}.service" <<EOF
[Unit]
Description=KiscoBooks ${worker}
After=network-online.target mysql.service rabbitmq-server.service kiscobooks-api@${service}.service
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

for worker in accounting-report-snapshots reports-sources; do
  service=accounting
  module=accounting.tasks.reporting_snapshot
  if [ "$worker" = reports-sources ]; then
    service=reports
    module=reports.tasks.source_worker
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

for worker in catalog-accounting-publisher accounting-catalog-tax-worker; do
  service=catalog
  module=catalog.tasks.accounting_publisher
  if [ "$worker" = accounting-catalog-tax-worker ]; then
    service=accounting
    module=accounting.tasks.catalog_tax_worker
  fi
  cat >"/etc/systemd/system/kiscobooks-${worker}.service" <<EOF
[Unit]
Description=KiscoBooks ${worker}
After=network-online.target mysql.service rabbitmq-server.service kiscobooks-api@${service}.service
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

for app in auth console; do
  port=4310
  [ "$app" = console ] && port=4320
  cat >"/etc/systemd/system/kiscobooks-${app}.service" <<EOF
[Unit]
Description=KiscoBooks ${app} web application
After=network-online.target redis-server.service kiscobooks-api@identity.service
Wants=network-online.target

[Service]
Type=simple
User=kiscobooks
Group=kiscobooks
WorkingDirectory=/opt/kiscobooks/current/mfes/apps/${app}
EnvironmentFile=/etc/kiscobooks/${app}.env
Environment=NODE_ENV=production
ExecStart=/usr/bin/node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port ${port}
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
LimitNOFILE=32768
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/kiscobooks/current/mfes/apps/${app}/.next /var/log/kiscobooks

[Install]
WantedBy=multi-user.target
EOF
done

chown -R kiscobooks:kiscobooks "$root/mfes/apps/auth/.next" "$root/mfes/apps/console/.next"

install -m 644 "$root/start/win/conf/proxy.include" /etc/nginx/conf.d/proxy.include
{
  cat <<'EOF'
map $http_x_trace_id $bill_trace_id {
    "~^[0-9a-fA-F]{32}$" $http_x_trace_id;
    default $request_id;
}
EOF
  sed '/server_name  localhost;/a\    set_real_ip_from 127.0.0.1;\n    real_ip_header X-Forwarded-For;\n    real_ip_recursive on;' "$root/start/win/conf/bill.conf"
} >/etc/nginx/conf.d/kiscobooks-gateway.conf

cp -a /etc/nginx/sites-available/kisco.cloud "/root/kiscobooks-backups/kisco.cloud.before-runtime"
cat >/etc/nginx/sites-available/kisco.cloud <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name kisco.cloud;
    location ^~ /.well-known/acme-challenge/ { root /var/lib/letsencrypt; default_type text/plain; try_files $uri =404; }
    location / { return 301 https://kisco.cloud$request_uri; }
}
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name kisco.cloud;
    ssl_certificate /etc/letsencrypt/live/kisco.cloud/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kisco.cloud/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:kiscoTLS:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    server_tokens off;
    client_max_body_size 150m;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    location = /nginx-health { access_log off; default_type text/plain; return 200 'ok\n'; }
    location /oidc/ {
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:8001;
    }
    # Service API versions share these prefixes with Console pages such as
    # /accounting/suppliers and /reports/workspace. Route only actual API paths.
    location ~ ^/(identity|audit|catalog|notification|accounting|vouchers|reports|design)/v[12]/ {
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:8090;
    }
    location /auth-static/ {
        rewrite ^/auth-static(/.*)$ $1 break;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:4310;
    }
    location ~ ^/(accept|change-password|login|logout|onboarding|recover|refresh|reset|setup|signin|signup|step-up)(/|$) {
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:4310;
    }
    location ~ ^/api/(auth|change-password|invitations|local|onboarding|provider|registration|session|setup|step-up)(/|$) {
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:4310;
    }
    location / {
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:4320;
    }
}
EOF

systemctl daemon-reload
systemctl enable kiscobooks-api@{identity,audit,catalog,notification,accounting,vouchers,reports,design}.service
systemctl enable kiscobooks-auth.service kiscobooks-console.service kiscobooks-company-setup.service kiscobooks-identity-catalog-publisher.service kiscobooks-catalog-source-worker.service kiscobooks-catalog-accounting-publisher.service kiscobooks-accounting-catalog-tax-worker.service kiscobooks-accounting-report-snapshots.service kiscobooks-reports-sources.service
nginx -t
systemctl start kiscobooks-api@{identity,audit,catalog,notification,accounting,vouchers,reports,design}.service
systemctl start kiscobooks-auth.service kiscobooks-console.service kiscobooks-company-setup.service kiscobooks-identity-catalog-publisher.service kiscobooks-catalog-source-worker.service kiscobooks-catalog-accounting-publisher.service kiscobooks-accounting-catalog-tax-worker.service kiscobooks-accounting-report-snapshots.service kiscobooks-reports-sources.service
bash "$root/deploy/ubuntu/install-stock-runtime.sh"
bash "$root/deploy/ubuntu/install-print-runtime.sh"
systemctl reload nginx
