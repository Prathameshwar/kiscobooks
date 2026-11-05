"""Dependency and local-volume checks for advertised export capabilities."""

from billing_platform.errors import PlatformError

from reports.config import Settings
from reports.domain.reporting.contracts import ExportDefinition
from reports.tasks.export_artifacts import definition, store


def available(settings: Settings) -> tuple[ExportDefinition, ...]:
    if not settings.exports_enabled or settings.artifact_root is None:
        return ()
    try:
        store(settings)  # Validates the configured private persistent directory, including links.
        return tuple(definition(name, settings) for name in ("CSV", "XLSX", "HTML", "PDF"))
    except (PlatformError, ValueError, OSError, ImportError):
        return ()
