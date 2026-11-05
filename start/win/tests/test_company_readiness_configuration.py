"""Automatic setup installation preserves existing scopes, secrets and release gates."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "company_readiness", Path(__file__).resolve().parents[1] / "configure-company-readiness.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Configuration(unittest.TestCase):
    def test_preview_repeatability_and_preserved_release_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            services = ("identity", "accounting", "catalog", "reports")
            for service in services:
                (directory / f"{service}.env").write_text(
                    "# retained comment\nEXISTING_VALUE=keep\nMONEY_ADMISSION=false\n",
                    encoding="utf-8",
                )
            origins = {name: "http://127.0.0.1" for name in (*services, "vouchers")}
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            preview = MODULE.configure(directory, origins)
            self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})
            for service, changes in preview.items():
                MODULE.write(directory / f"{service}.env", changes)
            repeated = MODULE.configure(directory, origins)
            self.assertEqual(preview, repeated)
            for service in services:
                values = MODULE.read(directory / f"{service}.env")
                self.assertEqual(values["EXISTING_VALUE"], "keep")
                self.assertEqual(values["MONEY_ADMISSION"], "false")
            credential = json.loads(preview["identity"]["IDENTITY_REPORT_ENROLLMENT_CREDENTIALS"])
            source = json.loads(preview["reports"]["REPORTS_ENROLLMENT_SOURCE"])
            self.assertEqual(source["secret"], credential[source["key_id"]]["secret"])
            self.assertEqual(source["scopes"], [])
            self.assertTrue(source["allow_enrolled_companies"])


if __name__ == "__main__":
    unittest.main()
