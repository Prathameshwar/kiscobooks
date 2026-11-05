"""The epoch default must match revision 0028 on every metadata-created schema."""

from sqlalchemy import DefaultClause

from reports.metadata import service_metadata


def test_source_epoch_retains_migrated_query_version_default() -> None:
    default = service_metadata().tables["report_source_epoch"].c.query_version.server_default
    assert isinstance(default, DefaultClause)
    assert str(default.arg) == "0"
