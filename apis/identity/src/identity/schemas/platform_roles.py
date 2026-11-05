"""Reviewed fixed-catalogue reconciliation; no caller-supplied role grants."""

from pydantic import Field, field_validator

from identity.schemas.base import StrictModel
from identity.schemas.platform_access import clean_text


class RoleSeedChange(StrictModel):
    key: str
    added: list[str]
    removed: list[str]
    metadata_changed: bool
    deactivate: bool = False


class RoleSeedPlan(StrictModel):
    current_digest: str
    catalogue_digest: str
    changes: list[RoleSeedChange]


class RoleSeedCommand(StrictModel):
    expected_current_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_catalogue_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=3, max_length=500)
    _reason = field_validator("reason", mode="before")(clean_text)


class RoleSeedResult(StrictModel):
    changed: bool
    current_digest: str
    catalogue_digest: str
    inserted_roles: int
    updated_roles: int
    deactivated_roles: int
    added_grants: int
    removed_grants: int
