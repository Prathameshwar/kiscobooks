"""Recheck pinned publication evidence before granting new BOM applicability."""

import hashlib
import json

from billing_platform.errors import ConflictError

from catalog.models.boms import BomRevision
from catalog.schemas.boms import BomDraftInput
from catalog.tasks.bom_dependencies import line_dependency, route_dependency
from catalog.tasks.boms import definition_input
from catalog.tasks.configuration_access import ConfigurationAccess


async def require_current_publication(
    access: ConfigurationAccess, revision: BomRevision
) -> BomDraftInput:
    manifest = revision.dependency_manifest
    if manifest.get("schema") != 1 or manifest.get("source_version") != revision.source_version:
        raise ConflictError("published BOM dependency evidence is incomplete")
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(encoded).hexdigest() != revision.content_sha256:
        raise ConflictError("published BOM dependency evidence cannot be verified")
    definition = await definition_input(access, revision)
    if definition.model_dump(mode="json") != manifest.get("definition"):
        raise ConflictError("published BOM content does not match its retained definition")
    if await route_dependency(access, definition) != manifest.get("route"):
        raise ConflictError("published BOM route evidence has changed")
    retained = manifest.get("dependencies")
    if not isinstance(retained, list) or len(retained) != len(definition.components) + len(
        definition.outputs
    ):
        raise ConflictError("published BOM physical dependency evidence is incomplete")
    for line, previous in zip((*definition.components, *definition.outputs), retained, strict=True):
        current = await line_dependency(access, line, definition.definition_date)
        expected = {"line_key": str(line.line_key), **current.evidence}
        if not isinstance(previous, dict) or {
            key: value for key, value in previous.items() if key != "item_version"
        } != {key: value for key, value in expected.items() if key != "item_version"}:
            raise ConflictError(
                "BOM physical definitions have changed; publish a reviewed replacement"
            )
    return definition
