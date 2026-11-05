"""Location input, lean list projections and the company configuration projection."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.pricing import PricingInput, PublicationInput
from catalog.schemas.units import UnitCreate

#: `INTERNAL_TRANSIT` is deliberately absent: only the bootstrap creates that kind
#: (docs/catalog-warehouses.md §4), so a client naming it is a 422 at the edge.
SelectableKind = Literal["STORE", "GODOWN"]


class LocationFacts(BaseModel):
    """Where a location physically is. Ship-from tax resolution stays with the document."""

    model_config = ConfigDict(extra="forbid")
    department_id: uuid.UUID | None = None
    tax_registration_id: uuid.UUID | None = None
    timezone: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_+/-]*$"
    )
    address_line1: str | None = Field(default=None, min_length=1, max_length=120)
    address_line2: str | None = Field(default=None, min_length=1, max_length=120)
    city: str | None = Field(default=None, min_length=1, max_length=60)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    state_code: str | None = Field(default=None, pattern=r"^[A-Z0-9-]{1,6}$")

    @field_validator("address_line1", "address_line2", "city", "postal_code")
    @classmethod
    def printable(cls, value: str | None) -> str | None:
        return None if value is None else UnitCreate.meaningful_label(value)


class LocatedFacts(LocationFacts):
    """The country/state pairing rule, on the models that hold the whole picture.

    Deliberately not on ``WarehouseUpdate``: a patch naming only a state says nothing about the
    country, and enforcing the pair there would make "move this godown to the next subdivision"
    unrepresentable. ``command`` rebuilds ``WarehouseMerge`` from stored values plus the patch,
    so an update is still held to the rule — including clearing a country while a state
    remains — once, with the stored values in hand.
    """

    @model_validator(mode="after")
    def located(self) -> "LocatedFacts":
        if self.state_code is not None and self.country_code is None:
            raise ValueError("a state belongs to a named country")
        return self


class WarehouseCreate(MasterInput, LocatedFacts):
    kind: SelectableKind


class WarehouseUpdate(MasterUpdate, LocationFacts):
    """Identity and location facts. `kind` and `is_system` are not editable here.

    A store that became a godown would silently change which operations a document may
    perform against stock already recorded under it; that is a new location, not an edit.
    """


class WarehouseMerge(MasterInput, LocatedFacts):
    """The updatable surface: stored values merged with the patch, revalidated as a whole.

    `WarehouseCreate` cannot serve here — it constrains `kind` to what a client may name,
    and the built-in transit row is a stored value this must be able to represent.
    """


class WarehouseListItem(MasterListItem):
    kind: str | None = None
    is_system: bool | None = None
    city: str | None = None
    country_code: str | None = None
    state_code: str | None = None
    tax_registration_id: uuid.UUID | None = None


class WarehouseDetail(WarehouseListItem, DetailFields):
    department_id: uuid.UUID | None = None
    tax_registration_id: uuid.UUID | None = None
    timezone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    postal_code: str | None = None


class WarehouseQuery(MasterQuery):
    kind: SelectableKind | Literal["INTERNAL_TRANSIT"] | None = None
    is_system: bool | None = None


class ConfigurationBootstrap(BaseModel):
    """No input: the built-in location set is derived, never chosen by the caller."""

    model_config = ConfigDict(extra="forbid")


class WarehouseConfigurationDetail(BaseModel):
    """The company's location configuration, and the expectations a defaults change echoes.

    `source_version` is the live Identity checkpoint, as it is on every other Catalog read:
    a defaults change is refused unless it echoes this one back, so the read a reviewer
    made and the write they submit describe the same company.
    """

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    company_id: uuid.UUID
    main_warehouse_id: uuid.UUID | None = None
    transit_warehouse_id: uuid.UUID | None = None
    default_sale_warehouse_id: uuid.UUID | None = None
    default_purchase_warehouse_id: uuid.UUID | None = None
    default_customer_return_warehouse_id: uuid.UUID | None = None
    default_opening_warehouse_id: uuid.UUID | None = None
    #: The checkpoint the built-in set was derived from. It stays where it was when Identity
    #: advances, so it is history rather than an expectation — hence the separate name.
    provisioned_source_version: int | None = None
    row_version: int | None = None
    location_mode: str
    policy_generation: int
    source_version: int


class OperationFlagsInput(PricingInput):
    """The eight typed permissions, all required.

    Every flag is mandatory on purpose. A publish states the whole policy, so an omitted
    flag cannot quietly keep — or quietly drop — the value it replaces, and the reviewer
    approving the change sees all eight together (docs/catalog-warehouses.md §2).

    There is no validity window here. The window is server-assigned at publish: these are
    live controls resolved at operation time, and a caller-supplied start would be a
    backdated permission change (§5).
    """

    allow_sale_issue: StrictBool
    allow_purchase_receipt: StrictBool
    allow_transfer_in: StrictBool
    allow_transfer_out: StrictBool
    allow_customer_return_receipt: StrictBool
    allow_supplier_return_issue: StrictBool
    allow_opening_stock: StrictBool
    allow_adjustment: StrictBool


class OperationPolicyInput(PublicationInput, OperationFlagsInput):
    """The publish body: the flags, plus the expectations the preview handed back."""


class OperationPolicyRevisionDetail(BaseModel):
    """One published revision. `effective_to` is set when a successor supersedes it.

    Everything but the identity and the delivery state is optional and unset when a field
    policy denies reading it: a read deny holds in projections, not only in forms
    (docs/field-permissions.md §6).
    """

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    delivery_state: str
    warehouse_id: uuid.UUID | None = None
    revision: int | None = None
    effective_from: dt.datetime | None = None
    effective_to: dt.datetime | None = None
    allow_sale_issue: bool | None = None
    allow_purchase_receipt: bool | None = None
    allow_transfer_in: bool | None = None
    allow_transfer_out: bool | None = None
    allow_customer_return_receipt: bool | None = None
    allow_supplier_return_issue: bool | None = None
    allow_opening_stock: bool | None = None
    allow_adjustment: bool | None = None


class OperationPolicyView(BaseModel):
    """What a location may do now, and what it was allowed to do before.

    History is returned rather than summarized: a reader auditing a movement needs the
    revision that was in force then, not today's flags.
    """

    model_config = ConfigDict(extra="forbid")
    warehouse_id: uuid.UUID
    policy_generation: int
    source_version: int
    current: OperationPolicyRevisionDetail | None = None
    history: list[OperationPolicyRevisionDetail] = Field(default_factory=list)


class PolicyIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class OperationPolicyPreview(BaseModel):
    """A dry run. Writes nothing, allocates nothing, and is not a reservation.

    `expected_generation` and `expected_source_version` are what a publish must echo back;
    if anything changed in between, the publish is refused rather than applied to a picture
    the reviewer never saw.
    """

    model_config = ConfigDict(extra="forbid")
    warehouse_id: uuid.UUID
    #: The number the publish would return. Advisory: a concurrent publish takes it, and
    #: the generation check is what makes that a refusal rather than a silent renumber.
    revision: int
    expected_generation: int
    expected_source_version: int
    delivery_state: str
    #: Whether the *change* would be accepted. It says nothing about the caller's rights:
    #: previewing needs read access, publishing needs `warehouse.publish`.
    publishable: bool
    #: Which flags differ from the revision in force, restricted to the flags this caller
    #: may read — a diff is a disclosure of the current value.
    changed: list[str] = Field(default_factory=list)
    issues: list[PolicyIssue] = Field(default_factory=list)


class ActivityDefaultsInput(PublicationInput):
    """A typed audited action, not a bare PATCH of pointer columns.

    All four pointers are required, and `null` is a real value meaning *no default
    configured* — resolution then reaches the built-in Main (§3). Requiring them stops an
    omitted field from clearing a default the caller never mentioned.

    Changing a default moves no stock and touches no quantity: it changes which location a
    later operation resolves to, and only for operations that location is allowed to do.
    """

    default_sale_warehouse_id: uuid.UUID | None
    default_purchase_warehouse_id: uuid.UUID | None
    default_customer_return_warehouse_id: uuid.UUID | None
    default_opening_warehouse_id: uuid.UUID | None
