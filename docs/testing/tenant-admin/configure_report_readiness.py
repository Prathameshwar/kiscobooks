"""Configure existing local report contracts for the retained three QA companies.

Credentials stay in ignored environment files. No database or posting flag is changed.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read_environment(path: Path) -> tuple[str, dict[str, str]]:
    content = path.read_text(encoding="utf-8-sig")
    values: dict[str, str] = {}
    for line in content.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key in values:
            raise ValueError("Duplicate private environment key")
        values[key] = value
    return content, values


def main() -> None:
    fixtures = json.loads((ROOT / ".test_artifacts/tenant-admin-20261029/live/resources.json").read_text())
    if fixtures["tenant"] != "01a186e4-81a0-7221-8f57-2404a864ff43":
        raise ValueError("Only the retained QA tenant is supported")
    companies = fixtures["companies"]
    if len(companies) != 3 or {c["key"] for c in companies} != {"retail", "services", "distribution"}:
        raise ValueError("Expected the three retained QA company profiles")
    scopes = [{"tenant_id": fixtures["tenant"], "company_id": c["id"]} for c in companies]
    paths = {service: ROOT / "start/win/env" / (service + ".env") for service in ("accounting", "identity", "reports")}
    originals = {service: read_environment(path) for service, path in paths.items()}
    key_id = "qa-tenant-reports"
    accounting_credentials = json.loads(originals["accounting"][1].get("ACCOUNTING_REPORT_CREDENTIALS", "{}"))
    identity_credentials = json.loads(originals["identity"][1].get("IDENTITY_REPORT_AUTHORITY_CREDENTIALS", "{}"))
    owner_secret = accounting_credentials.get(key_id, {}).get("secret") or secrets.token_hex(32)
    authority_secret = identity_credentials.get(key_id, {}).get("secret") or secrets.token_hex(32)
    accounting_credentials[key_id] = {"secret": owner_secret, "scopes": scopes}
    identity_credentials[key_id] = {"secret": authority_secret, "scopes": scopes}
    broker = json.loads((ROOT / ".tools/rabbitmq-runtime/credentials.json").read_text())
    from urllib.parse import quote

    broker_url = "amqp://" + quote(broker["user"], safe="") + ":" + quote(broker["password"], safe="") + "@127.0.0.1:5672/bill_identity_test"
    artifact_root = ROOT / ".tools/qa-report-artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    updates = {
        "accounting": {"ACCOUNTING_REPORT_CREDENTIALS": json.dumps(accounting_credentials, separators=(",", ":")), "ACCOUNTING_REPORT_SNAPSHOT_ENABLED": "true"},
        "identity": {"IDENTITY_REPORT_AUTHORITY_CREDENTIALS": json.dumps(identity_credentials, separators=(",", ":"))},
        "reports": {
            "REPORTS_OWNERS": json.dumps([{**accounting_credentials[key_id], "key_id": key_id, "origin": "http://127.0.0.1:8011"}], separators=(",", ":")),
            "REPORTS_AUTHORITY_SOURCES": json.dumps([{**identity_credentials[key_id], "key_id": key_id, "origin": "http://127.0.0.1:8001"}], separators=(",", ":")),
            "REPORTS_FRAMEWORK_ENABLED": "true", "REPORTS_SOURCE_VERSIONS_ENABLED": "true",
            "REPORTS_NATIVE_QUERIES_ENABLED": "true", "REPORTS_EXPORTS_ENABLED": "true",
            "REPORTS_ARTIFACT_ROOT": str(artifact_root), "REPORTS_JOB_BROKER_URL": broker_url,
            "REPORTS_JOB_QUEUE_NAMESPACE": "reports.qa.tenant",
        },
    }
    for service, path in paths.items():
        content, _ = originals[service]
        if path.read_text(encoding="utf-8-sig") != content:
            raise ValueError("Private configuration changed during preparation; no update authorized")
    for service, path in paths.items():
        content, _ = originals[service]
        backup = path.with_suffix(".env.qa-reports-before")
        if not backup.exists():
            backup.write_text(content, encoding="utf-8")
        changed = updates[service]
        lines = [line for line in content.splitlines() if line.split("=", 1)[0] not in changed]
        lines.extend(key + "=" + value for key, value in changed.items())
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Configured existing report source/authority contracts for exactly three QA companies.")
    print("Private environment credentials retained; money/invoice/stock admission unchanged.")


if __name__ == "__main__":
    main()
