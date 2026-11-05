"""Authenticated self-service contracts; no provider tokens are returned."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import ConfigDict, Field

from identity.schemas.base import PageMeta, StrictModel
from identity.schemas.company import sparse_company_schema
from identity.schemas.user import UserDetail


class SessionTenant(StrictModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    #: Editable starting suggestions for company creation, from this tenant only.
    default_country_code: str
    default_state_code: str | None = None
    suspended_reason: str | None = None


class SessionCompany(StrictModel):
    id: uuid.UUID
    display_name: str | None = None
    code: str | None = None
    status: str | None = None


class SessionGrant(StrictModel):
    permissions: list[str]
    scope_type: str
    scope_id: uuid.UUID | None
    valid_from: dt.date
    valid_to: dt.date | None


class SessionDetail(StrictModel):
    user: UserDetail
    tenant: SessionTenant
    company: SessionCompany | None
    #: Which rule of the resolution chain chose the open company
    #: (``identity.services.session_context``). A client that showed a stored default and
    #: a first-readable fallback the same way would be claiming a preference nobody set.
    selected_source: Literal["explicit", "default", "membership", "first", "none"]
    #: The chosen company even where ``company`` is withheld pending a proof — the
    #: caller's own default or workplace, so naming it back discloses nothing new.
    selected_company_id: uuid.UUID | None = None
    #: The selection needs fresh company authentication (``company.requires_step_up``).
    #: Distinguishes "verify to continue" from "you have no company", which the console
    #: could not tell apart while the chain lived there.
    step_up_required: bool = False
    permissions: list[str]
    grants: list[SessionGrant]


class SessionCompanyChoice(StrictModel):
    """One switcher row from the actor's own authority — not a company read.

    Deliberately four fields. This is the one company list an actor without
    ``company.read`` can see (docs/company-context-ui-todo.md D2), so it carries what it
    takes to *choose* a company and nothing that describes one: no legal name, no
    jurisdiction, no statutory identifier, no currency. Field-policy read denies still
    apply on top, which is why the two text fields are not required in the schema.
    """

    model_config = ConfigDict(json_schema_extra=sparse_company_schema)

    id: uuid.UUID
    code: str
    display_name: str
    #: Opening this one needs fresh company authentication, so the switcher can say so
    #: before it is chosen rather than after the switch appears to have failed.
    requires_step_up: bool
    #: The company stored on this user as the one to open.
    is_default: bool


class SessionCompanyPage(StrictModel):
    items: list[SessionCompanyChoice]
    page: PageMeta


class ReasonRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")


class PreferenceUpdate(StrictModel):
    #: "Set as my default" — the company this user opens when they do not say which
    #: (``session_context.resolve_company`` step 2). A self-write, because it decides
    #: nothing but where this one person lands: it confers no access, and the company
    #: must already be one they can open. ``None`` clears it.
    default_company_id: uuid.UUID | None = None
    locale: str | None = Field(default=None, max_length=8)
    timezone: str | None = Field(default=None, max_length=64)
    date_format: str | None = Field(default=None, max_length=20)
    datetime_format: str | None = Field(default=None, max_length=30)
    digit_grouping: Literal["indian", "western", "none"] | None = None
    currency_display: Literal["symbol", "code", "none"] | None = None
    theme: Literal["light", "dark", "system"] | None = None
    landing_page: str | None = Field(default=None, max_length=100)
