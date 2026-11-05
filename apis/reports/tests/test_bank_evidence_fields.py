"""Bank evidence exports fail closed under source-field read denials."""

from types import SimpleNamespace
from typing import cast

import pytest
from billing_platform.errors import PermissionDeniedError

from reports.api.auth import Access
from reports.api.routes import bank_evidence_fields


def test_bank_statement_field_deny_blocks_evidence_export() -> None:
    current = cast(
        Access,
        SimpleNamespace(
            context=SimpleNamespace(
                policies=[
                    {
                        "entity_type": "accounting.bank_statement_entry",
                        "field_key": "amount",
                        "access": "read",
                        "effect": "deny",
                    }
                ]
            )
        ),
    )
    with pytest.raises(PermissionDeniedError):
        bank_evidence_fields(current)


def test_unrelated_write_policy_does_not_block_bank_evidence() -> None:
    current = cast(
        Access,
        SimpleNamespace(
            context=SimpleNamespace(
                policies=[
                    {
                        "entity_type": "accounting.bank_statement_entry",
                        "field_key": "amount",
                        "access": "write",
                        "effect": "deny",
                    }
                ]
            )
        ),
    )
    bank_evidence_fields(current)
