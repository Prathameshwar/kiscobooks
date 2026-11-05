import datetime as dt
import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from billing_platform.actor_authorization import ActorAuthorizationProof, ActorAuthorizationRequest
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS


def proof(**changes: Any) -> dict[str, Any]:
    return {
        "request_id": uuid7(),
        "tenant_id": uuid7(),
        "company_id": uuid7(),
        "user_id": uuid7(),
        "source_version": 1,
        "generated_at": "2026-09-11T12:00:00Z",
        "expires_at": "2026-09-11T12:00:30Z",
        "permissions": ["unit.read"],
        **changes,
    }


def test_authorization_proof_is_bounded_exact_and_known() -> None:
    request = ActorAuthorizationRequest(
        request_id=uuid7(), user_id=uuid7(), permissions=frozenset({"unit.read", "unit.manage"})
    )
    assert request.model_dump(mode="json")["permissions"] == ["unit.manage", "unit.read"]
    result = ActorAuthorizationProof.model_validate(proof())
    assert result.generated_at.tzinfo == dt.UTC
    assert ActorAuthorizationProof.model_validate(result.model_dump()) == result
    assert result.model_dump(mode="json")["permissions"] == ["unit.read"]
    assert ActorAuthorizationProof.model_validate(proof(permissions=[])).permissions == frozenset()
    assert "item_group.move" in CATALOG_PERMISSIONS and "invoice.post" not in CATALOG_PERMISSIONS
    assert "group.manage" not in CATALOG_PERMISSIONS


@pytest.mark.parametrize(
    "changes",
    [
        {"request_id": str(uuid.UUID(int=0))},
        {"tenant_id": str(uuid.UUID(int=0))},
        {"source_version": True},
        {"source_version": 0},
        {"source_version": 2**63},
        {"contract": "forged"},
        {"generated_at": "2026-09-11T12:00:00"},
        {"expires_at": "2026-09-11T12:00:31Z"},
        {"expires_at": "2026-09-11T11:00:00Z"},
        {"permissions": ["invented.permission"]},
        {"unexpected": True},
        {"generated_at": "2026-09-11T23:59:50Z", "expires_at": "2026-09-12T00:00:01Z"},
        {"generated_at": "9999-12-31T12:00:00Z", "expires_at": "9999-12-31T12:00:30Z"},
        {"generated_at": "0001-01-01T00:00:00+01:00"},
    ],
)
def test_authorization_rejects_forged_or_unbounded_proofs(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ActorAuthorizationProof.model_validate(proof(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"request_id": str(uuid.UUID(int=0))},
        {"permissions": []},
        {"permissions": ["not.registered"]},
    ],
)
def test_request_rejects_unknown_or_empty_authority(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ActorAuthorizationRequest.model_validate(
            {"request_id": uuid7(), "user_id": uuid7(), "permissions": ["unit.read"], **changes}
        )
