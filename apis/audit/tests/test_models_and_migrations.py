"""The `audit` migration chain, and its parity with the models.

Two tiers. The **chain-shape** tests need no database and run on every change — a gap or
duplicate revision, a missing ``down_revision``, an empty ``downgrade``, more than one DDL
statement per direction, an ENUM/FLOAT, or smuggled seed data. Because the revisions are
hand-written raw DDL (rule 4.8, no transactional DDL), they also parse each ``CREATE TABLE``
and hold its columns and nullability against the models — the compensating control for
hand-writing SQL.

The **round-trip** tests need real MySQL and carry the ``mysql`` marker: a chain that
passes the shape tests may still fail to run, and only a live server proves the RANGE
partitioning, the composite PK, and the ``BINARY(32)`` hashes are accepted.
"""

from __future__ import annotations

import ast
import asyncio
import configparser
import re
import runpy
from contextlib import nullcontext
from unittest.mock import Mock, patch

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import BINARY, Connection, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from audit.metadata import TABLES, service_metadata
from tests.alembic_support import (
    ALEMBIC_INI,
    VERSIONS_DIR,
    alembic_config,
    revision_source,
    revisions,
)

_ALL = revisions()
_METADATA = service_metadata()


def test_alembic_targets_only_audit_owned_tables() -> None:
    """Imported platform models must not become Audit migration candidates."""
    from alembic import context

    config = alembic_config("mysql+asyncmy://localhost/audit_schema_check")
    configure = Mock()
    with patch.multiple(
        context,
        config=config,
        is_offline_mode=Mock(return_value=True),
        configure=configure,
        begin_transaction=Mock(return_value=nullcontext()),
        run_migrations=Mock(),
        create=True,
    ):
        runpy.run_path(str(ALEMBIC_INI.parent / "env.py"))
    assert set(configure.call_args.kwargs["target_metadata"].tables) == TABLES


_DDL_STATEMENT = re.compile(
    r"\b(CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|CREATE\s+(?:UNIQUE\s+)?INDEX|DROP\s+INDEX)\b",
    re.IGNORECASE,
)
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(\w+)\s*\((.*?)\)\s*ENGINE", re.IGNORECASE | re.DOTALL
)
_COLUMN_LINE = re.compile(r"^(\w+)\s+([A-Za-z]+(?:\(\d+(?:,\d+)?\))?)\s+(.*)$")
_NOT_A_COLUMN = frozenset({"constraint", "primary", "unique", "key", "index", "foreign", "check"})


# --- chain shape --------------------------------------------------------------


def test_versions_directory_exists() -> None:
    assert VERSIONS_DIR.is_dir()


def test_revision_ids_are_zero_padded_and_gapless() -> None:
    ids = [s.revision for s in _ALL]
    assert ids == [f"{n:04d}" for n in range(1, len(ids) + 1)], ids


def test_each_revision_points_at_its_predecessor() -> None:
    expected: str | None = None
    for script in _ALL:
        assert script.down_revision == expected, script.revision
        expected = script.revision


def _sql(source: str) -> str:
    """Every non-docstring string literal in the revision, joined."""
    module = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(module)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return "\n".join(
        node.value
        for node in ast.walk(module)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    )


def _function_body(source: str, name: str) -> list[ast.stmt]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.body
    raise AssertionError(f"no def {name}()")


def _is_empty(body: list[ast.stmt]) -> bool:
    for statement in body:
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue
        return False
    return True


@pytest.mark.parametrize("script", _ALL, ids=lambda s: s.revision)
def test_every_revision_has_a_downgrade_or_says_why_not(script: object) -> None:
    source = revision_source(script)  # type: ignore[arg-type]
    if _is_empty(_function_body(source, "downgrade")):
        assert "no downgrade" in source.lower(), "empty downgrade with no comment"


@pytest.mark.parametrize("script", _ALL, ids=lambda s: s.revision)
def test_one_ddl_statement_per_direction(script: object) -> None:
    sql = _sql(revision_source(script))  # type: ignore[arg-type]
    statements = [m.group(0).upper() for m in _DDL_STATEMENT.finditer(sql)]
    assert len(statements) <= 2, statements  # one upgrade, one downgrade


@pytest.mark.parametrize("script", _ALL, ids=lambda s: s.revision)
def test_ddl_is_a_literal_with_nothing_interpolated(script: object) -> None:
    source = revision_source(script)  # type: ignore[arg-type]
    for node in ast.walk(ast.parse(source)):
        assert not isinstance(node, ast.JoinedStr), "SQL built with an f-string"
    assert ".format(" not in source


@pytest.mark.parametrize("script", _ALL, ids=lambda s: s.revision)
def test_create_table_sets_engine_charset_collate_row_format(script: object) -> None:
    sql = _sql(revision_source(script))  # type: ignore[arg-type]
    if not _CREATE_TABLE.search(sql):
        return
    for expected in (
        "ENGINE=InnoDB",
        "DEFAULT CHARSET=utf8mb4",
        "COLLATE=utf8mb4_unicode_ci",
        "ROW_FORMAT=DYNAMIC",
    ):
        assert expected in sql, expected


@pytest.mark.parametrize("script", _ALL, ids=lambda s: s.revision)
def test_no_enum_float_or_seed_data(script: object) -> None:
    source = revision_source(script)  # type: ignore[arg-type]
    sql = _sql(source)
    assert not re.search(r"\bENUM\s*\(", sql, re.IGNORECASE)
    for forbidden in (r"\bFLOAT\b", r"\bDOUBLE\b", r"\bREAL\b"):
        assert not re.search(forbidden, sql, re.IGNORECASE), forbidden
    assert "op.bulk_insert(" not in source
    assert not re.search(r"\bINSERT\s+INTO\b", sql, re.IGNORECASE)


# --- hand-written DDL against the models --------------------------------------


def _parse_columns(source: str) -> tuple[str, dict[str, tuple[str, bool]]]:
    match = _CREATE_TABLE.search(_sql(source))
    assert match is not None
    table = match.group(1)
    columns: dict[str, tuple[str, bool]] = {}
    for raw in match.group(2).splitlines():
        line = raw.strip().rstrip(",")
        parsed = _COLUMN_LINE.match(line)
        if parsed is None or parsed.group(1).lower() in _NOT_A_COLUMN:
            continue
        columns[parsed.group(1)] = (parsed.group(2).upper(), "NOT NULL" not in line.upper())
    return table, columns


def _revision_tables() -> dict[str, dict[str, tuple[str, bool]]]:
    tables: dict[str, dict[str, tuple[str, bool]]] = {}
    for script in _ALL:
        table, columns = _parse_columns(revision_source(script))
        tables[table] = columns
    return tables


_REVISION_TABLES = _revision_tables()


def test_chain_creates_exactly_the_service_tables() -> None:
    assert set(_REVISION_TABLES) == TABLES
    assert set(service_metadata().tables) == TABLES


@pytest.mark.parametrize("table_name", sorted(_REVISION_TABLES))
def test_ddl_columns_and_nullability_match_the_model(table_name: str) -> None:
    parsed = _REVISION_TABLES[table_name]
    model_columns = _METADATA.tables[table_name].columns
    assert set(parsed) == set(model_columns.keys()), table_name
    for name, (_, nullable) in parsed.items():
        assert nullable == model_columns[name].nullable, f"{table_name}.{name}"


@pytest.mark.parametrize("table_name", sorted(_REVISION_TABLES))
def test_binary_and_datetime_scales_match_the_model(table_name: str) -> None:
    """``BINARY`` ids are 16 bytes and the hash columns 32 — the length is asserted from the
    model, so a drift in either direction is caught. Timestamps are ``DATETIME(6)``."""
    model_columns = _METADATA.tables[table_name].columns
    for name, (sql_type, _) in _REVISION_TABLES[table_name].items():
        impl = getattr(model_columns[name].type, "impl", model_columns[name].type)
        if isinstance(impl, BINARY):
            assert sql_type == f"BINARY({impl.length})", f"{table_name}.{name} is {sql_type}"
        if name.endswith("_at"):
            assert sql_type == "DATETIME(6)", f"{table_name}.{name} is {sql_type}"


# --- configuration ------------------------------------------------------------


def _ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(ALEMBIC_INI, encoding="utf-8")
    return parser


def test_file_template_is_the_sequential_one() -> None:
    assert _ini()["alembic"]["file_template"] == "%(rev)s_%(slug)s"


def test_the_ini_holds_no_database_url() -> None:
    assert "sqlalchemy.url" not in _ini()["alembic"]


# --- against real MySQL -------------------------------------------------------


def _partition_names(url: str) -> set[str]:
    async def run() -> set[str]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT PARTITION_NAME FROM information_schema.PARTITIONS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'audit_event' "
                        "AND PARTITION_NAME IS NOT NULL"
                    )
                )
                return {row[0] for row in result}
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _table_names(url: str) -> set[str]:
    async def run() -> set[str]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return set(await connection.run_sync(lambda c: inspect(c).get_table_names()))
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.mark.mysql
def test_upgrade_creates_monthly_partitions_and_downgrade_is_clean(mysql_url: str) -> None:
    config = alembic_config(mysql_url)

    command.upgrade(config, "head")
    assert TABLES <= _table_names(mysql_url)
    partitions = _partition_names(mysql_url)
    # The monthly partitions plus the permanent catch-all (docs/audit.md §6).
    assert "pmax" in partitions
    assert "p202609" in partitions

    command.downgrade(config, "base")
    remaining = _table_names(mysql_url)
    assert remaining <= {"alembic_version"}, sorted(remaining - {"alembic_version"})


@pytest.mark.mysql
def test_models_and_head_do_not_drift(mysql_url: str) -> None:
    command.upgrade(alembic_config(mysql_url), "head")

    def diff(connection: Connection) -> list[object]:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        return list(compare_metadata(context, _METADATA))

    async def run() -> list[object]:
        engine = create_async_engine(mysql_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(diff)
        finally:
            await engine.dispose()

    assert asyncio.run(run()) == [], "models drifted from head"
