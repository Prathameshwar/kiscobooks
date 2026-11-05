import uuid

import pytest
from pydantic import SecretStr, ValidationError

from notification.config import Settings


@pytest.mark.parametrize(
    "owner,space",
    [
        (uuid.uuid4(), None),
        (None, uuid.uuid4()),
        (uuid.UUID(int=0), uuid.uuid4()),
        (uuid.uuid4(), uuid.UUID(int=0)),
        (uuid.UUID(int=1), uuid.UUID(int=1)),
    ],
)
def test_platform_configuration_rejects_partial_reserved_or_collapsed_ownership(owner, space):
    with pytest.raises(ValidationError):
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr("a" * 32),
            cursor_signing_secret=SecretStr("c" * 32),
            data_encryption_key=SecretStr("d" * 32),
            platform_owner_tenant_id=owner,
            platform_space_id=space,
        )
