"""Align private development stock/source connections without activating posting.

Only named environment files beneath --env-dir are changed. All connections are
validated before writing; existing credentials, other connections and settings
are preserved. Output never includes environment values or credentials.
"""

import argparse
import json
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    pass


class Environment:
    def __init__(self, directory: Path, service: str):
        self.path = directory / (service + ".env")
        if self.path.resolve().parent != directory.resolve():
            raise ConfigurationError(
                "Environment paths must stay inside their selected directory"
            )
        self.lines = self.path.read_text(encoding="utf-8-sig").splitlines()
        self.values: dict[str, str] = {}
        for line in self.lines:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, separator, value = line.partition("=")
            name, value = name.strip(), value.strip()
            if not separator or not name:
                raise ConfigurationError("Environment contains an unsupported line")
            if name in self.values:
                raise ConfigurationError("Environment contains a duplicate variable")
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            self.values[name] = value
        self.changed = False

    def set(self, name: str, value: str) -> None:
        if self.values.get(name) == value:
            return
        if name in self.values:
            self.lines = [
                name + "=" + value if line.partition("=")[0].strip() == name else line
                for line in self.lines
            ]
        else:
            self.lines.append(name + "=" + value)
        self.values[name] = value
        self.changed = True

    def document(self, name: str, expected: type) -> Any:
        try:
            value = json.loads(
                self.values.get(name, "[]" if expected is list else "{}")
            )
            if not isinstance(value, expected):
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise ConfigurationError(
                "Existing connection JSON requires review"
            ) from exc
        return value


def matching_secret(first: str | None, second: str | None) -> str:
    values = [value for value in (first, second) if value is not None]
    if any(
        not isinstance(value, str) or len(value) < 32 or "\n" in value or "\r" in value
        for value in values
    ):
        raise ConfigurationError("An existing connection credential is invalid")
    if len(set(values)) > 1:
        raise ConfigurationError(
            "Paired connection credentials differ; existing values were preserved"
        )
    return values[0] if values else secrets.token_urlsafe(48)


def validate_origin(value: str) -> None:
    url = urlsplit(value)
    if (
        not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or (
            url.scheme != "https"
            and not (
                url.scheme == "http"
                and url.hostname in {"127.0.0.1", "localhost", "::1"}
            )
        )
    ):
        raise ConfigurationError("A source connection origin is invalid")


def configure(directory: Path, registry: Path) -> int:
    env = {
        service: Environment(directory, service)
        for service in ("identity", "catalog", "accounting", "vouchers")
    }
    services = json.loads(registry.read_text(encoding="utf-8-sig"))["services"]
    ports = {service["code"]: service["port"] for service in services}
    origins = {}
    for service in ("identity", "catalog", "accounting", "vouchers"):
        port = ports[service]
        if type(port) is not int or not 1 <= port <= 65535:
            raise ConfigurationError("The service registry has an invalid local port")
        origins[service] = f"http://127.0.0.1:{port}"
    accounting, catalog, vouchers = env["accounting"], env["catalog"], env["vouchers"]
    source_secret = matching_secret(
        accounting.values.get("ACCOUNTING_STOCK_OWNER_SECRET"),
        catalog.values.get("CATALOG_STOCK_OWNER_SECRET"),
    )
    accounting.set("ACCOUNTING_STOCK_OWNER_SECRET", source_secret)
    catalog.set("CATALOG_STOCK_OWNER_SECRET", source_secret)
    if "ACCOUNTING_STOCK_OWNER_URL" not in accounting.values:
        accounting.set("ACCOUNTING_STOCK_OWNER_URL", origins["catalog"])
    validate_origin(accounting.values["ACCOUNTING_STOCK_OWNER_URL"])
    # Stock first use is a separate delegated channel. Ordinary financial
    # reservation credentials keep their explicitly configured company grants.
    for direction in ("REQUEST", "RESPONSE"):
        native_name = "ACCOUNTING_STOCK_IDENTITY_" + direction + "_SECRET"
        owner_name = "IDENTITY_STOCK_RESERVATION_" + direction + "_SECRET"
        paired = matching_secret(
            accounting.values.get(native_name), env["identity"].values.get(owner_name)
        )
        accounting.set(native_name, paired)
        env["identity"].set(owner_name, paired)
    if "ACCOUNTING_STOCK_IDENTITY_URL" not in accounting.values:
        accounting.set("ACCOUNTING_STOCK_IDENTITY_URL", origins["identity"])
    validate_origin(accounting.values["ACCOUNTING_STOCK_IDENTITY_URL"])
    execution_name = "VOUCHERS_STOCK_EXECUTION_OWNER"
    execution = vouchers.document(execution_name, dict)
    if (
        set(execution) - {"origin", "key_id", "secret"}
        or execution.get("key_id", "stock.current") != "stock.current"
    ):
        raise ConfigurationError("Existing stock execution connection requires review")
    execution_secret = matching_secret(
        accounting.values.get("ACCOUNTING_STOCK_EXECUTION_SECRET"),
        execution.get("secret"),
    )
    accounting.set("ACCOUNTING_STOCK_EXECUTION_SECRET", execution_secret)
    execution.update(
        origin=execution.get("origin", origins["accounting"]),
        key_id="stock.current",
        secret=execution_secret,
    )
    validate_origin(execution["origin"])
    vouchers.set(execution_name, json.dumps(execution, separators=(",", ":")))

    for owner in ("accounting", "vouchers"):
        variable = "CATALOG_STOCK_RETIREMENT_" + owner.upper()
        connection = catalog.document(variable, dict)
        if set(connection) - {"origin", "secret"}:
            raise ConfigurationError("Existing retirement connection requires review")
        owner_secret = owner.upper() + "_STOCK_RETIREMENT_SECRET"
        credential = matching_secret(connection.get("secret"), env[owner].values.get(owner_secret))
        env[owner].set(owner_secret, credential)
        connection.update(origin=connection.get("origin", origins[owner]), secret=credential)
        validate_origin(connection["origin"])
        catalog.set(variable, json.dumps(connection, separators=(",", ":")))

    variable = "CATALOG_STOCK_POLICY_ACCOUNTING"
    connection = catalog.document(variable, dict)
    if set(connection) - {"origin", "secret"}:
        raise ConfigurationError("Existing native policy connection requires review")
    credential = matching_secret(
        connection.get("secret"), accounting.values.get("ACCOUNTING_STOCK_POLICY_SECRET")
    )
    accounting.set("ACCOUNTING_STOCK_POLICY_SECRET", credential)
    connection.update(origin=connection.get("origin", origins["accounting"]), secret=credential)
    validate_origin(connection["origin"])
    catalog.set(variable, json.dumps(connection, separators=(",", ":")))

    # A distinct, explicitly enabled installation capability. Ordinary scoped
    # money execution/import/report credentials remain untouched.
    owners = vouchers.document("VOUCHERS_SNAPSHOT_OWNERS", list)
    if any(not isinstance(owner, dict) for owner in owners):
        raise ConfigurationError("Existing source owner connections require review")
    for service in ("identity", "catalog", "accounting"):
        key_id = "vouchers.enrolled.current"
        candidates = [
            owner
            for owner in owners
            if isinstance(owner, dict)
            and owner.get("owner") == service
            and owner.get("key_id") == key_id
        ]
        if len(candidates) > 1:
            raise ConfigurationError(
                "Duplicate enrolled-company source connections require review"
            )
        owner = candidates[0] if candidates else {}
        variable = service.upper() + "_VOUCHER_SNAPSHOT_CREDENTIALS"
        credentials = env[service].document(variable, dict)
        credential = credentials.get(key_id, {})
        if not isinstance(credential, dict) or any(
            value and value.get("allow_enrolled_companies") is not True
            for value in (owner, credential)
        ):
            raise ConfigurationError(
                "An existing source capability requires explicit enrollment configuration"
            )
        secret = matching_secret(owner.get("secret"), credential.get("secret"))
        credential.update(
            secret=secret,
            scopes=credential.get("scopes", []),
            allow_enrolled_companies=True,
        )
        credentials[key_id] = credential
        if len(credentials) > 12:
            raise ConfigurationError(
                "Source credential count exceeds its supported bound"
            )
        env[service].set(variable, json.dumps(credentials, separators=(",", ":")))
        owner.update(
            owner=service,
            origin=owner.get("origin", origins[service]),
            key_id=key_id,
            secret=secret,
            scopes=owner.get("scopes", []),
            allow_enrolled_companies=True,
        )
        validate_origin(owner["origin"])
        if not candidates:
            owners.append(owner)
    if len(owners) > 12:
        raise ConfigurationError("Source owner count exceeds its supported bound")
    vouchers.set("VOUCHERS_SNAPSHOT_OWNERS", json.dumps(owners, separators=(",", ":")))
    # No activation flag is enabled by connection setup.
    for environment in env.values():
        if environment.changed:
            environment.path.write_text(
                "\n".join(environment.lines) + "\n", encoding="utf-8"
            )
    return sum(environment.changed for environment in env.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-dir", type=Path, required=True)
    parser.add_argument(
        "--registry", type=Path, default=Path(__file__).parent / "conf/services.json"
    )
    arguments = parser.parse_args()
    try:
        changed = configure(arguments.env_dir, arguments.registry)
    except (ConfigurationError, OSError, KeyError, TypeError, ValueError):
        print(
            "Stock connection setup failed validation; existing credentials require review."
        )
        return 1
    print(
        f"Stock development connections aligned in {changed} environment files; activation unchanged."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
