"""Private connection alignment is repeatable and never overwrites disagreements."""

import importlib.util
import json
import secrets
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "configure-stock-connections.py"
SPEC = importlib.util.spec_from_file_location("stock_connections", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Connections(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bill-stock-connections-")
        self.directory = Path(self.temporary.name)
        self.registry = self.directory / "services.json"
        self.registry.write_text(
            json.dumps(
                {
                    "services": [
                        {"code": code, "port": port}
                        for code, port in (
                            ("identity", 8001),
                            ("catalog", 8003),
                            ("accounting", 8011),
                            ("vouchers", 8012),
                        )
                    ]
                }
            ),
            encoding="utf-8",
        )
        for code in ("identity", "catalog", "accounting", "vouchers"):
            (self.directory / (code + ".env")).write_text(
                "# preserved environment\nEXISTING_VALUE=retained\n", encoding="utf-8"
            )

    def tearDown(self):
        self.temporary.cleanup()

    def values(self, code):
        return MODULE.Environment(self.directory, code).values

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.directory.glob("*.env")}

    def test_paired_secrets_automatic_scopes_no_activation_and_repeatability(self):
        self.assertEqual(MODULE.configure(self.directory, self.registry), 4)
        accounting, catalog, vouchers = (
            self.values(code) for code in ("accounting", "catalog", "vouchers")
        )
        self.assertEqual(
            accounting["ACCOUNTING_STOCK_OWNER_SECRET"],
            catalog["CATALOG_STOCK_OWNER_SECRET"],
        )
        identity = self.values("identity")
        for direction in ("REQUEST", "RESPONSE"):
            self.assertEqual(
                accounting["ACCOUNTING_STOCK_IDENTITY_" + direction + "_SECRET"],
                identity["IDENTITY_STOCK_RESERVATION_" + direction + "_SECRET"],
            )
        self.assertNotIn("IDENTITY_ACCOUNTING_RESERVATION_CREDENTIALS", identity)
        execution = json.loads(vouchers["VOUCHERS_STOCK_EXECUTION_OWNER"])
        self.assertEqual(
            accounting["ACCOUNTING_STOCK_EXECUTION_SECRET"], execution["secret"]
        )
        self.assertEqual(execution["origin"], "http://127.0.0.1:8011")
        for owner in ("accounting", "vouchers"):
            connection = json.loads(catalog["CATALOG_STOCK_RETIREMENT_" + owner.upper()])
            self.assertEqual(connection["secret"], self.values(owner)[owner.upper() + "_STOCK_RETIREMENT_SECRET"])
            self.assertNotEqual(connection["secret"], execution["secret"])
        self.assertNotIn("ACCOUNTING_VOUCHER_STOCK_ENABLED", accounting)
        self.assertNotIn("VOUCHERS_STOCK_EXECUTION_ENABLED", vouchers)
        owners = json.loads(vouchers["VOUCHERS_SNAPSHOT_OWNERS"])
        self.assertEqual(len(owners), 3)
        for owner in owners:
            native = self.values(owner["owner"])
            credential = json.loads(
                native[owner["owner"].upper() + "_VOUCHER_SNAPSHOT_CREDENTIALS"]
            )[owner["key_id"]]
            self.assertEqual(credential["secret"], owner["secret"])
            self.assertTrue(credential["allow_enrolled_companies"])
            self.assertEqual(owner["scopes"], [])
            self.assertEqual(native["EXISTING_VALUE"], "retained")
        before = self.snapshot()
        self.assertEqual(MODULE.configure(self.directory, self.registry), 0)
        self.assertEqual(self.snapshot(), before)

    def test_mismatched_credentials_leave_every_file_unchanged(self):
        MODULE.configure(self.directory, self.registry)
        path = self.directory / "catalog.env"
        text = path.read_text(encoding="utf-8")
        original = self.values("catalog")["CATALOG_STOCK_OWNER_SECRET"]
        path.write_text(
            text.replace(original, secrets.token_urlsafe(48)), encoding="utf-8"
        )
        before = self.snapshot()
        with self.assertRaises(MODULE.ConfigurationError):
            MODULE.configure(self.directory, self.registry)
        self.assertEqual(self.snapshot(), before)

    def test_existing_owners_and_activation_flags_are_preserved(self):
        existing = {
            "owner": "identity",
            "key_id": "old.current",
            "origin": "https://identity.example.test",
            "secret": secrets.token_urlsafe(48),
            "scopes": [],
        }
        path = self.directory / "vouchers.env"
        path.write_text(
            "VOUCHERS_SNAPSHOT_OWNERS="
            + json.dumps([existing])
            + "\nVOUCHERS_STOCK_EXECUTION_ENABLED=true\n",
            encoding="utf-8",
        )
        MODULE.configure(self.directory, self.registry)
        values = self.values("vouchers")
        self.assertEqual(json.loads(values["VOUCHERS_SNAPSHOT_OWNERS"])[0], existing)
        self.assertEqual(values["VOUCHERS_STOCK_EXECUTION_ENABLED"], "true")

    def test_duplicate_variable_and_invalid_origin_fail_before_writing(self):
        path = self.directory / "accounting.env"
        path.write_text(
            "ACCOUNTING_STOCK_OWNER_URL=http://192.0.2.1\n", encoding="utf-8"
        )
        before = self.snapshot()
        with self.assertRaises(MODULE.ConfigurationError):
            MODULE.configure(self.directory, self.registry)
        self.assertEqual(self.snapshot(), before)
        path.write_text("DUPLICATE=first\nDUPLICATE=second\n", encoding="utf-8")
        with self.assertRaises(MODULE.ConfigurationError):
            MODULE.configure(self.directory, self.registry)


if __name__ == "__main__":
    unittest.main()
