import argparse
import json
import secrets
import sys
import uuid

import pytest

from billing_platform import publisher_cli
from billing_platform.publisher import PublisherConfig
from billing_platform.service_auth import ServiceKey


def test_recovery_arguments_require_explicit_unique_ids(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["worker", "--apply"])
    with pytest.raises(SystemExit):
        publisher_cli.arguments("test")
    monkeypatch.setattr(sys, "argv", ["worker", "--retry"])
    with pytest.raises(SystemExit):
        publisher_cli.arguments("test")
    mid = uuid.uuid4()
    monkeypatch.setattr(sys, "argv", ["worker", "--retry", str(mid)])
    assert publisher_cli.arguments("test").retry == [mid]


async def test_status_reports_only_the_publishers_rows(tmp_path, capsys):
    from billing_platform.db import Base, create_engine

    url = "sqlite+aiosqlite:///" + str(tmp_path / "ops.db")
    engine = create_engine(url)
    async with engine.begin() as db:
        await db.run_sync(Base.metadata.create_all)
    await engine.dispose()
    config = PublisherConfig(
        database_url=url,
        broker_url="amqp://test.invalid",
        broker_user="test",
        exchange="test.audit",
        key_id="test",
        key=ServiceKey("test", "audit", frozenset({"test.changed"}), secrets.token_bytes(32)),
    )
    await publisher_cli.operate(
        config, argparse.Namespace(dead_letters=None, retry=[], apply=False)
    )
    assert json.loads(capsys.readouterr().out)["pending"] == 0
