"""Explicit native QA admission must never accept an application database."""

import pytest

from tests.alembic_support import native_mysql_server


def test_native_mysql_admits_only_the_dedicated_loopback_server() -> None:
    url = native_mysql_server("mysql+asyncmy://root@127.0.0.1:13396")
    assert url.host == "127.0.0.1" and url.port == 13396 and url.database is None


@pytest.mark.parametrize(
    "value",
    [
        "mysql+asyncmy://root@127.0.0.1:3306",
        "mysql+asyncmy://root@127.0.0.1:13396/accounting",
        "mysql+asyncmy://root@remote.invalid:13396",
        "sqlite+aiosqlite:///:memory:",
        "not a database URL",
    ],
)
def test_native_mysql_refuses_application_or_unapproved_targets(value: str) -> None:
    with pytest.raises(ValueError, match="dedicated loopback"):
        native_mysql_server(value)
