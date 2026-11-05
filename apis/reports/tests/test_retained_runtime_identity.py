from pathlib import Path

import pytest

from reports.runtimes import ledger_v1
from reports.tasks.report_catalog import implementation_hash


@pytest.mark.parametrize("dependency", ["views.py", "bulk_summary.py"])
def test_definition_identity_tracks_presentation_calculation_and_bulk_rules(
    monkeypatch, dependency
):
    implementation_hash.cache_clear()
    expected = implementation_hash()
    original = Path.read_bytes

    def changed(path):
        data = original(path)
        return data + b"\n# deployed calculation rule change\n" if path.name == dependency else data

    monkeypatch.setattr(Path, "read_bytes", changed)
    implementation_hash.cache_clear()
    try:
        assert implementation_hash() != expected
    finally:
        implementation_hash.cache_clear()


def test_retained_runtime_identity_survives_git_line_ending_conversion(monkeypatch):
    expected = ledger_v1.identity()
    original = Path.read_bytes

    def windows_bytes(path):
        return original(path).replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    monkeypatch.setattr(Path, "read_bytes", windows_bytes)
    assert ledger_v1.identity() == expected


def test_definition_identity_survives_git_line_ending_conversion(monkeypatch):
    implementation_hash.cache_clear()
    expected = implementation_hash()
    original = Path.read_bytes

    def windows_bytes(path):
        return original(path).replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    monkeypatch.setattr(Path, "read_bytes", windows_bytes)
    implementation_hash.cache_clear()
    try:
        assert implementation_hash() == expected
    finally:
        implementation_hash.cache_clear()


@pytest.mark.parametrize("identify", [ledger_v1.identity, implementation_hash])
@pytest.mark.parametrize("dependency", ["exact.py", "money.py", "constants.py", "listing.py"])
def test_calculation_identity_tracks_shared_financial_dependencies(
    monkeypatch, identify, dependency
):
    implementation_hash.cache_clear()
    expected = identify()
    original = Path.read_bytes

    def changed_bytes(path):
        content = original(path)
        if path.parent.name == "billing_platform" and path.name == dependency:
            return content + b"\n# Simulate a deployed shared calculation dependency change.\n"
        return content

    monkeypatch.setattr(Path, "read_bytes", changed_bytes)
    implementation_hash.cache_clear()
    try:
        assert identify() != expected
    finally:
        implementation_hash.cache_clear()
