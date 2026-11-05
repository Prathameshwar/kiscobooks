"""Fail startup configuration checks without constructing an engine or making I/O."""

import pytest

from vouchers.tasks.execution_worker import Settings as ExecutionSettings
from vouchers.tasks.execution_worker import check_configuration as execution
from vouchers.tasks.source_worker import Settings as SourceSettings
from vouchers.tasks.source_worker import check_configuration as sources


def test_delivery_configuration_requires_owners_and_complete_enrollment_discovery():
    database = "mysql+asyncmy://unused:unused@192.0.2.1/never_connect"
    with pytest.raises(ValueError, match="configured owner"):
        execution(ExecutionSettings(database_url=database))
    with pytest.raises(ValueError, match="configured owner"):
        sources(SourceSettings(database_url=database))
    owner = {
        "owner": "catalog",
        "origin": "http://127.0.0.1:8003",
        "key_id": "current",
        "secret": "ephemeral-delivery-configuration-secret",
        "allow_enrolled_companies": True,
    }
    with pytest.raises(ValueError, match="Identity owner"):
        sources(SourceSettings(database_url=database, snapshot_owners=[owner]))
    sources(
        SourceSettings(
            database_url=database, snapshot_owners=[owner, owner | {"owner": "identity"}]
        )
    )
    execution(
        ExecutionSettings(
            database_url=database,
            stock_execution_owner={"origin": "http://127.0.0.1:8011", "secret": owner["secret"]},
        )
    )
