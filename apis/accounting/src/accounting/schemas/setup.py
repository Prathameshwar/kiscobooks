import uuid
from typing import Literal, Self

from pydantic import Field, model_validator

from accounting.schemas.masters import Input


class TemplateSelection(Input):
    business_accounts: bool = True
    gst_registration_id: uuid.UUID | None = None
    local_component: Literal["SGST", "UTGST"] | None = None

    @model_validator(mode="after")
    def component_pair(self) -> Self:
        if (self.gst_registration_id is None) != (self.local_component is None):
            raise ValueError("GST template requires both registration and local component")
        return self


class TemplateChange(Input):
    resource: Literal["account_group", "account"]
    code: str
    action: Literal["create", "update"]
    fields: list[str] = Field(default_factory=list)


class TemplatePreview(Input):
    template_key: str
    version: str
    content_hash: str
    groups: list[str]
    accounts: list[str]
    installed: bool
    changes: list[TemplateChange] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class TemplateResult(Input):
    installation_id: uuid.UUID
    groups_created: int
    accounts_created: int
    groups_updated: int = 0
