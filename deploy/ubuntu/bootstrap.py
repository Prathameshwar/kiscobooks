"""Create private production configuration for a fresh single-VM installation."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote

SERVICES = ("identity", "audit", "catalog", "notification", "accounting", "vouchers", "reports", "design")
PREFIXES = {name: name.upper() for name in SERVICES}
CONFIG = Path("/etc/kiscobooks")
REDIS_CONFIG = Path("/etc/redis/redis.conf")


def token() -> str:
    return secrets.token_urlsafe(48)


def write(name: str, values: dict[str, str]) -> None:
    path = CONFIG / name
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    os.chmod(path, 0o640)
    subprocess.run(["chown", "root:kiscobooks", str(path)], check=True)


CONFIG.mkdir(mode=0o750, parents=True, exist_ok=True)
actor_secret = token()
setup_key = token()
redis_password = secrets.token_hex(32)
broker_password = secrets.token_hex(32)
source_request_secret = token()
source_response_secret = token()
source_event_secret = token()
migrator_password = secrets.token_hex(32)
database_passwords = {service: secrets.token_hex(32) for service in SERVICES}

acl_file = next(
    (
        Path(line.split(maxsplit=1)[1])
        for line in REDIS_CONFIG.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("aclfile ")
    ),
    None,
)
if acl_file is None:
    raise RuntimeError("Redis must configure an aclfile before production bootstrap")
acl_lines = [
    line
    for line in acl_file.read_text(encoding="utf-8").splitlines()
    if not line.startswith("user kiscobooks ")
]
redis_hash = hashlib.sha256(redis_password.encode()).hexdigest()
acl_lines.append(f"user kiscobooks on #{redis_hash} ~* &* +@all -@dangerous")
acl_file.write_text("\n".join(acl_lines) + "\n", encoding="utf-8")
os.chmod(acl_file, 0o640)
subprocess.run(["chown", "redis:redis", str(acl_file)], check=True)
subprocess.run(["systemctl", "restart", "redis-server"], check=True)
subprocess.run(["rabbitmqctl", "add_vhost", "kiscobooks"], check=True, stdout=subprocess.DEVNULL)
subprocess.run(["rabbitmqctl", "add_user", "kisco-source", broker_password], check=True, stdout=subprocess.DEVNULL)
subprocess.run(["rabbitmqctl", "set_permissions", "-p", "kiscobooks", "kisco-source", ".*", ".*", ".*"], check=True, stdout=subprocess.DEVNULL)
source_broker_url = f"amqp://kisco-source:{broker_password}@127.0.0.1:5672/kiscobooks"


def redis_url(database: int) -> str:
    return f"redis://kiscobooks:{redis_password}@127.0.0.1:6379/{database}"

sql = []
for service in SERVICES:
    sql.extend(
        [
            f"CREATE DATABASE IF NOT EXISTS `{service}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;",
            f"CREATE USER IF NOT EXISTS '{service}'@'127.0.0.1' IDENTIFIED BY '{database_passwords[service]}';",
        ]
    )
    privileges = "SELECT, INSERT" if service == "audit" else "SELECT, INSERT, UPDATE, DELETE"
    sql.append(f"GRANT {privileges} ON `{service}`.* TO '{service}'@'127.0.0.1';")
sql.append(f"CREATE USER IF NOT EXISTS 'kisco_migrator'@'127.0.0.1' IDENTIFIED BY '{migrator_password}';")
for service in SERVICES:
    sql.append(f"GRANT ALL PRIVILEGES ON `{service}`.* TO 'kisco_migrator'@'127.0.0.1';")
sql.append("FLUSH PRIVILEGES;")
subprocess.run(["mysql"], input="\n".join(sql), text=True, check=True)


def db_url(user: str, password: str, database: str) -> str:
    return f"mysql+asyncmy://{quote(user)}:{quote(password)}@127.0.0.1:3306/{database}"


for service in SERVICES:
    prefix = PREFIXES[service]
    values = {
        f"{prefix}_DATABASE_URL": db_url(service, database_passwords[service], service),
        f"{prefix}_ACTOR_SIGNING_SECRET": actor_secret,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if service in {"identity", "audit", "notification", "design"}:
        values[f"{prefix}_CURSOR_SIGNING_SECRET"] = token()
    if service in {"vouchers", "reports"}:
        values[f"{prefix}_ARTIFACT_SIGNING_SECRET"] = token()
    if service == "identity":
        client_secret = token()
        bff_secret = token()
        local_auth = {
            "issuer": "https://kisco.cloud/oidc",
            "jwks_url": "http://127.0.0.1:8001/oidc/jwks",
            "audience": "billing-api",
            "auth_ui_url": "https://kisco.cloud",
            "clients": [{
                "client_id": "billing-web",
                "secret_sha256": hashlib.sha256(client_secret.encode()).hexdigest(),
                "redirect_uris": ["https://kisco.cloud/api/auth/callback/local"],
            }],
            "bff_secret": bff_secret,
            "key_encryption_key": base64.b64encode(secrets.token_bytes(32)).decode(),
        }
        values.update({
            "IDENTITY_REDIS_URL": redis_url(0),
            "IDENTITY_COMPANY_SETUP_ORIGINS": json.dumps({
                "catalog": "http://127.0.0.1:8003",
                "accounting": "http://127.0.0.1:8011",
                "vouchers": "http://127.0.0.1:8012",
                "reports": "http://127.0.0.1:8013",
            }, separators=(",", ":")),
            "IDENTITY_CATALOG_SOURCE_CREDENTIALS": json.dumps({"current": {"secret": source_request_secret, "scopes": [], "allow_actor_authorization": True, "allow_enrolled_companies": True}}, separators=(",", ":")),
            "IDENTITY_CATALOG_SOURCE_RESPONSE_SECRET": source_response_secret,
            "IDENTITY_SOURCE_EVENT_SECRET": source_event_secret,
            "IDENTITY_SOURCE_BROKER_URL": source_broker_url,
            "IDENTITY_SOURCE_BROKER_USER": "kisco-source",
            "IDENTITY_PUBLIC_AUTH_URL": "https://kisco.cloud",
            "IDENTITY_AUTH_PROVIDER": "local",
            "IDENTITY_LOCAL_AUTH": json.dumps(local_auth, separators=(",", ":")),
            "IDENTITY_SETUP_KEY": setup_key,
            "IDENTITY_BANK_ACTIVE_KEY_ID": "production-v1",
            "IDENTITY_BANK_ENCRYPTION_KEYS": json.dumps({"production-v1": base64.b64encode(secrets.token_bytes(32)).decode()}, separators=(",", ":")),
        })
        auth_shared = {"client_secret": client_secret, "bff_secret": bff_secret}
    elif service == "accounting":
        values["ACCOUNTING_ENCRYPTION_KEY"] = secrets.token_hex(32)
        values["ACCOUNTING_STOCK_CATALOG_URL"] = "http://127.0.0.1:8090/catalog"
    elif service == "catalog":
        values["CATALOG_SIMPLE_CREATION_ORIGINS"] = json.dumps({"accounting": "http://127.0.0.1:8011", "vouchers": "http://127.0.0.1:8012"}, separators=(",", ":"))
        values["CATALOG_IDENTITY_SOURCE"] = json.dumps({"base_url": "http://127.0.0.1:8001", "request_key_id": "current", "request_secret": source_request_secret, "response_secrets": {"current": source_response_secret}}, separators=(",", ":"))
        values["CATALOG_SOURCE_DISCOVERY"] = "true"
        values["CATALOG_SOURCE_EVENT_SECRET"] = source_event_secret
        values["CATALOG_SOURCE_BROKER_URL"] = source_broker_url
        values["CATALOG_SOURCE_BROKER_USER"] = "kisco-source"
    elif service == "notification":
        values["NOTIFICATION_DATA_ENCRYPTION_KEY"] = token()
    elif service == "reports":
        values["REPORTS_ARTIFACT_ROOT"] = "/var/lib/kiscobooks/reports"
    elif service == "vouchers":
        values.update({"VOUCHERS_PRINT_FILE_ROOT": "/var/lib/kiscobooks/vouchers/prints", "VOUCHERS_SUPPORTING_FILE_ROOT": "/var/lib/kiscobooks/vouchers/supporting"})
    elif service == "design":
        values["DESIGN_ASSET_STORAGE_ROOT"] = "/var/lib/kiscobooks/design/assets"
    write(f"{service}.env", values)

write("migration.env", {
    f"{PREFIXES[service]}_DATABASE_URL": db_url("kisco_migrator", migrator_password, service)
    for service in SERVICES
})

nextauth_secret = token()
write("auth.env", {
    "AUTH_PROVIDER": "local",
    "AUTH_LOCAL_ISSUER": "https://kisco.cloud/oidc",
    "AUTH_LOCAL_CLIENT_ID": "billing-web",
    "AUTH_LOCAL_CLIENT_SECRET": auth_shared["client_secret"],
    "AUTH_LOCAL_BFF_SECRET": auth_shared["bff_secret"],
    "NEXTAUTH_URL": "https://kisco.cloud",
    "NEXTAUTH_SECRET": nextauth_secret,
    "CONSOLE_URL": "https://kisco.cloud",
    "IDENTITY_URL": "http://127.0.0.1:8001",
    "AUTH_REDIS_URL": redis_url(1),
    "NEXT_PUBLIC_CONSOLE_URL": "https://kisco.cloud",
    "NEXT_ASSET_PREFIX": "/auth-static",
    "AUTH_TRUSTED_PROXY_HOPS": "1",
    "AUTH_REGISTRATION_MODE": "manual-review",
    "AUTH_REGISTRATION_WORKSPACE_ENABLED": "true",
    "IDENTITY_SETUP_KEY": setup_key,
    "SETUP_SERVICE_URLS": json.dumps({
        "Audit": "http://127.0.0.1:8002",
        "Catalog": "http://127.0.0.1:8003",
        "Accounting": "http://127.0.0.1:8011",
        "Vouchers": "http://127.0.0.1:8012",
        "Reports": "http://127.0.0.1:8013",
        "Notification": "http://127.0.0.1:8010",
        "Design": "http://127.0.0.1:8014",
    }, separators=(",", ":")),
})
write("console.env", {
    "AUTH_URL": "https://kisco.cloud",
    "NEXTAUTH_SECRET": nextauth_secret,
    "IDENTITY_URL": "http://127.0.0.1:8001",
    "NEXT_PUBLIC_AUTH_URL": "https://kisco.cloud/login",
    "CATALOG_GATEWAY_URL": "http://127.0.0.1:8090/catalog",
    "ACCOUNTING_GATEWAY_URL": "http://127.0.0.1:8090/accounting",
    "VOUCHERS_GATEWAY_URL": "http://127.0.0.1:8090/vouchers",
    "REPORTS_GATEWAY_URL": "http://127.0.0.1:8090/reports",
    "AUDIT_GATEWAY_URL": "http://127.0.0.1:8090",
    "NOTIFICATION_GATEWAY_URL": "http://127.0.0.1:8090/notification",
    "DESIGN_GATEWAY_URL": "http://127.0.0.1:8090/design",
})

for path in ("reports", "vouchers/prints", "vouchers/supporting", "design/assets"):
    target = Path("/var/lib/kiscobooks") / path
    target.mkdir(mode=0o750, parents=True, exist_ok=True)
    subprocess.run(["chown", "-R", "kiscobooks:kiscobooks", str(target)], check=True)

readiness_script = Path("/opt/kiscobooks/current/start/win/configure-company-readiness.py")
spec = importlib.util.spec_from_file_location("company_readiness_configuration", readiness_script)
if spec is None or spec.loader is None:
    raise RuntimeError("company readiness configuration is unavailable")
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)
origins = {"identity": "http://127.0.0.1:8001", "catalog": "http://127.0.0.1:8003", "accounting": "http://127.0.0.1:8011", "vouchers": "http://127.0.0.1:8012", "reports": "http://127.0.0.1:8013"}
for service, updates in readiness.configure(CONFIG, origins).items():
    target = CONFIG / f"{service}.env"
    readiness.write(target, updates)
    os.chmod(target, 0o640)
    subprocess.run(["chown", "root:kiscobooks", str(target)], check=True)

print("Production configuration created without printing secrets.")
