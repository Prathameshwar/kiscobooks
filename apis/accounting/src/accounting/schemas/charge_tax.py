"""Catalog tax computation evidence; Accounting owns the account assignments."""

import uuid
from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, Tag, TypeAdapter, model_validator

from accounting.schemas.ledger import Amount, BusinessDate
from accounting.schemas.masters import DecimalInput, Detail, Input

GstComponentCode = Literal["CGST", "SGST", "UTGST", "IGST", "CESS"]

#: The only component combinations a GST supply can carry: intra-state (CGST+SGST),
#: intra-UT (CGST+UTGST) or inter-state (IGST), each optionally with compensation cess.
#: Empty is an untaxed (nil/exempt/non-GST) statement.
GST_COMPONENT_SETS: frozenset[frozenset[str]] = frozenset(
    frozenset(base | extra)
    for base in ({"CGST", "SGST"}, {"CGST", "UTGST"}, {"IGST"})
    for extra in (set(), {"CESS"})
) | {frozenset()}


# Version-one component. Free text, retained only to read stored version-one evidence;
# version one cannot identify a company registration, so ingestion refuses it with
# components. No docstring: it would change the published version-one schema.
class TaxComponent(Input):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z][A-Z0-9_]*$")
    amount: Amount


class GstTaxComponent(Input):
    code: GstComponentCode
    amount: Amount


# Version-one Catalog statement. Unchanged, so version-one signatures still verify and the
# published version-one schema stays byte-identical.
class TaxComputation(Input):
    version: Literal[1] = 1
    provider_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    assessment_id: uuid.UUID
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    posting_date: BusinessDate
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    net_amount: Amount
    gross_amount: Amount
    components: list[TaxComponent] = Field(max_length=20)


class TaxComputationV2(Input):
    """Version-two Catalog statement: names the company registration the supply is made
    under, so Accounting can apply the regime valid on ``posting_date``. The key is
    required (null only for an untaxed statement) so the signed body is unambiguous."""

    version: Literal[2]
    provider_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    assessment_id: uuid.UUID
    company_registration_id: uuid.UUID | None
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    posting_date: BusinessDate
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    net_amount: Amount
    gross_amount: Amount
    components: list[GstTaxComponent] = Field(max_length=5)

    @model_validator(mode="after")
    def component_set(self) -> "TaxComputationV2":
        codes = [component.code for component in self.components]
        if len(set(codes)) != len(codes) or frozenset(codes) not in GST_COMPONENT_SETS:
            raise ValueError(
                "components must be CGST+SGST, CGST+UTGST or IGST, each optionally with CESS"
            )
        if codes and self.company_registration_id is None:
            raise ValueError("taxed statements must name the company registration")
        return self


def _version(value: Any) -> int:
    if isinstance(value, dict):
        return 2 if value.get("version") == 2 else 1
    return int(getattr(value, "version", 1))


AnyTaxComputation = Annotated[
    Annotated[TaxComputation, Tag("1")] | Annotated[TaxComputationV2, Tag("2")],
    Discriminator(lambda value: str(_version(value))),
]
TAX_COMPUTATION: TypeAdapter[TaxComputation | TaxComputationV2] = TypeAdapter(AnyTaxComputation)


class TaxEvidence(Input):
    key_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    timestamp: int = Field(strict=True, ge=0)
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    computation: AnyTaxComputation
    accounts: dict[str, uuid.UUID] = Field(max_length=20)


class ChargeTaxSnapshotDetail(Detail):
    assessment_id: uuid.UUID | None = None
    provider_id: uuid.UUID | None = None
    currency: str | None = None
    net_amount: DecimalInput | None = None
    gross_amount: DecimalInput | None = None
    input_hash: str | None = None
    key_id: str | None = None
    snapshot: dict[str, Any] | None = None


class ChargeTaxSnapshotListItem(Detail):
    assessment_id: uuid.UUID | None = None
    provider_id: uuid.UUID | None = None
    currency: str | None = None
    net_amount: DecimalInput | None = None
    gross_amount: DecimalInput | None = None
