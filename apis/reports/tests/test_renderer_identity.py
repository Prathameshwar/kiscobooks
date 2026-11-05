from pathlib import Path

import pytest

from reports.rendering import presentation


@pytest.mark.parametrize("dependency", ["display.py", "tabular.py", "process_limits.py"])
def test_presentation_identity_covers_formatter_and_isolation_code(monkeypatch, dependency):
    presentation.renderer_identity.cache_clear()
    expected = presentation.renderer_identity()
    original = Path.read_bytes

    def changed(path):
        data = original(path)
        return data + b"\n# changed implementation\n" if path.name == dependency else data

    monkeypatch.setattr(Path, "read_bytes", changed)
    presentation.renderer_identity.cache_clear()
    try:
        assert presentation.renderer_identity() != expected
    finally:
        presentation.renderer_identity.cache_clear()


def test_tabular_identity_tracks_implementation_and_shared_styles(monkeypatch):
    from reports.config import Settings
    from reports.tasks.export_artifacts import definition

    settings = Settings.model_construct(
        export_max_rows=100, export_max_bytes=10000000, export_timeout_seconds=60
    )
    expected = definition("XLSX", settings).identity
    original = Path.read_bytes

    def changed(path):
        data = original(path)
        return data + b"\n" if path.name == "presentation-v1.json" else data

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert definition("XLSX", settings).identity != expected
