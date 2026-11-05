import uuid

import pytest

from identity.domain.account_review import Applicant, eligible, fingerprint, transition


def applicant(**changes):
    return Applicant(
        **{
            "provider_id": 42,
            "provider_uuid": uuid.uuid4(),
            "name": "Applicant",
            "username": "applicant",
            "email": "applicant@example.invalid",
            "path": "bill/pending-registration",
            "user_type": "external",
            "is_active": False,
            "verified": False,
            "groups": (),
            "roles": (),
            "country_code": "IN",
            "state_code": "IN-MH",
            "workspace_name": "",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"path": "users"},
        {"user_type": "service_account"},
        {"groups": (1,)},
        {"roles": (str(uuid.uuid4()),)},
        {"email": ""},
    ],
)
def test_scope_excludes_unrelated_or_privileged_accounts(changes):
    assert not eligible(applicant(**changes))


def test_fingerprint_changes_for_identity_and_activation_but_is_stable():
    row = applicant()
    assert eligible(row) and fingerprint(row) == fingerprint(row)
    assert fingerprint(row) != fingerprint(
        applicant(provider_uuid=row.provider_uuid, email="changed@example.invalid")
    )


def test_workspace_request_changes_fingerprint_but_legacy_snapshot_stays_stable():
    row = applicant()
    assert fingerprint(row) != fingerprint(
        applicant(provider_uuid=row.provider_uuid, workspace_name="North Books")
    )
    assert fingerprint(row) != fingerprint(
        applicant(provider_uuid=row.provider_uuid, workspace_name=None)
    )


@pytest.mark.parametrize(
    "status,action,expected",
    [
        ("pending", "approve", "approved"),
        ("pending", "reject", "rejected"),
        ("rejected", "reopen", "pending"),
    ],
)
def test_allowed_transitions(status, action, expected):
    assert transition(status, action) == expected


@pytest.mark.parametrize(
    "status,action", [("approved", "reject"), ("pending", "reopen"), ("rejected", "approve")]
)
def test_refuses_unsafe_transitions(status, action):
    with pytest.raises(ValueError):
        transition(status, action)
