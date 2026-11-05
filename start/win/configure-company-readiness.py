"""Configure local automatic company setup without per-company IDs or printed secrets.

Preview is the default. Run with the Identity interpreter and --apply after migrations.
Existing explicit service scopes and all unrelated environment entries are preserved.
"""

import argparse
import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEY = "company.auto"


def read(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name in values:
            raise ValueError("invalid or duplicate local environment entry")
        values[name] = value
    return values


def configure(directory: Path, origins: dict[str, str]) -> dict[str, dict[str, str]]:
    values = {
        name: read(directory / f"{name}.env")
        for name in ("identity", "accounting", "catalog", "reports")
    }
    updates: dict[str, dict[str, str]] = {name: {} for name in values}

    def mapping(service: str, name: str) -> dict:
        return json.loads(updates[service].get(name, values[service].get(name, "{}")))

    def put(service: str, name: str, value: object) -> None:
        updates[service][name] = json.dumps(value, separators=(",", ":"))

    enrollment = mapping("identity", "IDENTITY_REPORT_ENROLLMENT_CREDENTIALS")
    for requester in ("reports", "accounting", "catalog"):
        key = KEY + "." + requester
        secret = enrollment.get(key, {}).get("secret") or secrets.token_urlsafe(48)
        enrollment[key] = {
            "secret": secret,
            "scopes": [],
            "allow_enrolled_companies": True,
            "requester": requester,
        }
        field = (
            "REPORTS_ENROLLMENT_SOURCE"
            if requester == "reports"
            else requester.upper() + "_REPORT_ENROLLMENT_SOURCE"
        )
        put(
            requester,
            field,
            {"origin": origins["identity"], "key_id": key, **enrollment[key]},
        )
    put("identity", "IDENTITY_REPORT_ENROLLMENT_CREDENTIALS", enrollment)

    def connection(
        owner: str, field: str, consumer: str, consumer_field: str, *, array: bool
    ) -> None:
        credentials = mapping(owner, field)
        secret = credentials.get(KEY, {}).get("secret") or secrets.token_urlsafe(48)
        credentials[KEY] = {
            "secret": secret,
            "scopes": [],
            "allow_enrolled_companies": True,
        }
        put(owner, field, credentials)
        source = {"origin": origins[owner], "key_id": KEY, **credentials[KEY]}
        if array:
            previous = json.loads(values[consumer].get(consumer_field, "[]"))
            put(
                consumer,
                consumer_field,
                [r for r in previous if r.get("key_id") != KEY] + [source],
            )
        else:
            # Preserve explicitly approved legacy scopes on this one owner connection.
            previous = json.loads(values[consumer].get(consumer_field, "null"))
            if previous:
                source["scopes"] = previous.get("scopes", [])
            put(consumer, consumer_field, source)

    connection(
        "accounting",
        "ACCOUNTING_REPORT_CREDENTIALS",
        "reports",
        "REPORTS_OWNERS",
        array=True,
    )
    connection(
        "identity",
        "IDENTITY_REPORT_AUTHORITY_CREDENTIALS",
        "reports",
        "REPORTS_AUTHORITY_SOURCES",
        array=True,
    )
    connection(
        "catalog",
        "CATALOG_STOCK_REPORT_CREDENTIALS",
        "accounting",
        "ACCOUNTING_STOCK_REPORT_CATALOG",
        array=False,
    )
    put(
        "identity",
        "IDENTITY_COMPANY_SETUP_ORIGINS",
        {
            name: origins[name]
            for name in ("accounting", "catalog", "vouchers", "reports")
        },
    )
    for name in (
        "REPORTS_SOURCE_VERSIONS_ENABLED",
        "REPORTS_NATIVE_QUERIES_ENABLED",
        "REPORTS_AUTOMATIC_SOURCES_ENABLED",
    ):
        updates["reports"][name] = "true"
    updates["accounting"]["ACCOUNTING_REPORT_SNAPSHOT_ENABLED"] = "true"
    return updates


def write(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    remaining = dict(updates)
    for index, line in enumerate(lines):
        name = line.partition("=")[0]
        if name in remaining:
            lines[index] = name + "=" + remaining.pop(name)
    lines.extend(name + "=" + value for name, value in remaining.items())
    temporary = path.with_suffix(".env.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    registry = json.loads((ROOT / "conf/services.json").read_text(encoding="utf-8-sig"))
    origins = {s["code"]: f"http://127.0.0.1:{s['port']}" for s in registry["services"]}
    changes = configure(ROOT / "env", origins)
    for service, updates in changes.items():
        print(service + ": " + ", ".join(sorted(updates)))
    if args.apply:
        for service, updates in changes.items():
            write(ROOT / "env" / f"{service}.env", updates)
        print("Configuration saved. Restart affected APIs and managed report workers.")
    else:
        print("Preview only; use --apply after migration checks.")
