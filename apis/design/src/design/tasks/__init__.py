"""Domain rules for the design service. No FastAPI here — routes stay thin (CLAUDE.md §4)."""

from design.tasks.assets import (
    assert_layout_references,
    create_component,
    deactivate_asset,
    fingerprint,
    get_asset,
    get_component,
    list_assets,
    list_components,
    storage_path,
    update_component,
    upload_asset,
)
from design.tasks.resolution import (
    create_assignment,
    get_assignment,
    list_assignments,
    resolve_template,
    update_assignment,
)
from design.tasks.snapshots import artifact_path, list_snapshots, record_snapshot
from design.tasks.templates import (
    archive_template,
    assert_editable,
    assert_layout_fits,
    create_template,
    get_template,
    layout_digest,
    list_templates,
    update_template,
)
from design.tasks.versions import create_version, get_version, list_versions, publish_version

__all__ = [
    "archive_template",
    "artifact_path",
    "assert_editable",
    "assert_layout_fits",
    "assert_layout_references",
    "create_assignment",
    "create_component",
    "create_template",
    "create_version",
    "deactivate_asset",
    "fingerprint",
    "get_asset",
    "get_assignment",
    "get_component",
    "get_template",
    "get_version",
    "layout_digest",
    "list_assets",
    "list_assignments",
    "list_components",
    "list_snapshots",
    "list_templates",
    "list_versions",
    "publish_version",
    "record_snapshot",
    "resolve_template",
    "storage_path",
    "update_assignment",
    "update_component",
    "update_template",
    "upload_asset",
]
