"""Native repaired-behavior probes; run with Catalog's local virtualenv."""
# CLI observation evidence is intentionally written to stdout.
# ruff: noqa: T201

import asyncio
import uuid

from billing_platform.errors import ConflictError, ValidationFailedError
from pydantic import ValidationError
from voucher_execution.identifiers import (
    IdentifierInput,
    IdentifierRequirement,
    validate_identifier_inputs,
)

from catalog.models.profiles import IdentifierProfile
from catalog.schemas.profiles import IdentifierProfileCreate
from catalog.schemas.simple_product_creation import SimpleSerialInput
from catalog.tasks.identifier_policy import validate_identifier_header
from catalog.tasks.inventory_templates import requirements


def rejected(fn, expected):
    try:
        fn()
    except expected:
        return
    raise AssertionError("Native validation unexpectedly accepted the probe")


async def main():
    try:
        await requirements(None, None, {"serial_tracking": True})
    except ValidationFailedError:
        pass
    else:
        raise AssertionError("Incomplete serial policy was accepted")
    print("PASS S01: inventory authoring rejects a missing serial identifier profile.")
    profile = IdentifierProfileCreate.model_validate(
        {
            "code": "OPTIONAL",
            "name": "All optional identifiers",
            "requirements": [
                {
                    "identifier_type": "SERIAL",
                    "namespace_rule": "COMPANY",
                    "min_count": 0,
                    "max_count": 1,
                    "requires_slot": False,
                }
            ],
        }
    )
    assert profile.requirements[0].min_count == 0
    rejected(lambda: SimpleSerialInput.model_validate({"identifiers": []}), ValidationError)
    print("PASS S09: all-optional profile accepted; empty identifiers fail creation schema.")
    serial_rule = IdentifierRequirement(
        identifier_type="SERIAL",
        namespace_rule="COMPANY",
        min_count=1,
        max_count=2,
        requires_slot=True,
    )
    assert (
        len(
            validate_identifier_inputs(
                [serial_rule],
                [IdentifierInput(identifier_type="SERIAL", slot=2, value="SECOND-ONLY")],
            )
        )
        == 1
    )
    print("PASS positive control: native minimum count may be satisfied in slot 2 alone.")
    rejected(
        lambda: validate_identifier_inputs(
            [serial_rule],
            [
                IdentifierInput(identifier_type="SERIAL", slot=1, value="SS"),
                IdentifierInput(identifier_type="SERIAL", slot=2, value="ß"),
            ],
        ),
        ValidationFailedError,
    )
    rejected(
        lambda: validate_identifier_inputs(
            [serial_rule],
            [
                IdentifierInput(identifier_type="SERIAL", slot=1, value=" ABC "),
                IdentifierInput(identifier_type="SERIAL", slot=2, value="abc"),
            ],
        ),
        ValidationFailedError,
    )
    rejected(
        lambda: validate_identifier_inputs(
            [serial_rule], [IdentifierInput(identifier_type="SERIAL", slot=1, value="ﬃ" * 41)]
        ),
        ValidationFailedError,
    )
    print("PASS S03/S04: native rejects casefold/trim duplicates and normalized length overflow.")
    imei_rule = IdentifierRequirement(
        identifier_type="IMEI",
        namespace_rule="COMPANY",
        min_count=1,
        max_count=1,
        requires_slot=False,
    )
    rejected(
        lambda: validate_identifier_inputs(
            [imei_rule], [IdentifierInput(identifier_type="IMEI", value="123456789012345")]
        ),
        ValidationFailedError,
    )
    rejected(
        lambda: validate_identifier_inputs(
            [serial_rule],
            [
                IdentifierInput(identifier_type="SERIAL", slot=1, value="A"),
                IdentifierInput(identifier_type="SERIAL", slot=1, value="B"),
            ],
        ),
        ValidationFailedError,
    )
    print("PASS S02: native rejects invalid IMEI checksum and duplicate slots.")

    class SavedRequirement:
        async def scalar(self, _query):
            return uuid.uuid4()

    header = IdentifierProfile(company_id=uuid.uuid4(), code="CHANGED")
    try:
        await validate_identifier_header(SavedRequirement(), header, {"code": "ORIGINAL"})
    except ConflictError:
        print("PASS S12: native code correction rejects a profile with saved requirements.")
    else:
        raise AssertionError("Identifier profile code unexpectedly mutable")


asyncio.run(main())
