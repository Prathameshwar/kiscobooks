"""The migration chain itself.

Two tiers, deliberately.

The **chain-shape** tests need no database and run on every change. They catch the
mistakes that actually happen: a duplicated revision id, a missing
``down_revision``, an empty ``downgrade``, a second DDL statement in one revision,
seed data smuggled into DDL. Because the revisions are hand-written raw DDL (see
``0001``'s docstring for why), they also parse each ``CREATE TABLE`` and hold its
columns against the SQLAlchemy models — a typo or a dropped column in hand-written
DDL is otherwise invisible until a query fails in production.

The **round-trip** and **autogenerate-drift** tests need real MySQL and carry the
``mysql`` marker. A chain-shape test passing does *not* mean the migration runs;
that is what the round-trip test is for, and it is the D0 exit criterion
(docs/identity-db-plan.md §3).
"""

from __future__ import annotations

import ast
import asyncio
import configparser
import re

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import Script, ScriptDirectory
from billing_platform.db import Base
from sqlalchemy import BINARY, CheckConstraint, Connection, DateTime, Numeric, inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.alembic_support import (
    ALEMBIC_INI,
    VERSIONS_DIR,
    alembic_config,
    revision_source,
    revisions,
)

_REVISION_ID = re.compile(r"^\d{4}$")

#: Every DDL verb a revision may issue. Rule 4.8 allows one per direction.
_DDL_STATEMENT = re.compile(
    r"\b(CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|CREATE\s+(?:UNIQUE\s+)?INDEX|DROP\s+INDEX(?=\s+\w+\s+ON\b))\b",
    re.IGNORECASE,
)

#: The table name may be backticked: ``user`` reads as a system table and ``role`` is a
#: MySQL reserved word, so revisions 0014 and 0016 quote them.
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+`?(\w+)`?\s*\((.*)\)\s*ENGINE", re.IGNORECASE | re.DOTALL
)

#: A column line: an identifier, optionally backticked, followed by a type. Constraint
#: and key lines start with a reserved word, so they are excluded by name rather than by
#: shape — which is why the quoting is captured. ``role.key`` is a reserved word *as a
#: column*, so `` `key` VARCHAR(60) `` and ``KEY ix_role_tenant_id (tenant_id)`` differ
#: only by the backticks, and reading the first as a key clause would drop the column
#: silently.
_COLUMN_LINE = re.compile(r"^(`?)(\w+)\1\s+([A-Za-z]+(?:\([^)]*\))?)\s*(.*)$")
_NOT_A_COLUMN = frozenset(
    {"constraint", "primary", "unique", "key", "index", "foreign", "check", "references"}
)

_ALL_REVISIONS = revisions()


@pytest.mark.parametrize("table_name", ("local_identity", "local_signing_key"))
def test_local_auth_check_names_match_create_migrations(table_name: str) -> None:
    """MySQL rollout parity includes the emitted names, not just expressions."""
    table = Base.metadata.tables[table_name]
    source = next(
        revision_source(script)
        for script in _ALL_REVISIONS
        if re.search(rf"CREATE\s+TABLE\s+{table_name}\s*\(", revision_source(script))
    )
    actual = set(re.findall(r"CONSTRAINT\s+(\w+)\s+CHECK", source))
    expected = {
        str(constraint.name)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert actual == expected


# --- chain shape --------------------------------------------------------------


def test_versions_directory_exists() -> None:
    assert VERSIONS_DIR.is_dir(), f"{VERSIONS_DIR} is missing"


def test_the_chain_is_linear_with_a_single_head() -> None:
    """One linear chain per service, no branching (§1.2).

    A second head is what silently happens when two revisions are written against
    the same parent, and Alembic then refuses to upgrade at all.
    """
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert len(heads) <= 1, f"the chain has branched: heads={heads}"


def test_revision_ids_are_zero_padded_and_gapless() -> None:
    """Sequential ids exist so a gap or a duplicate is visible in a listing (§1.2)."""
    ids = [script.revision for script in _ALL_REVISIONS]

    for revision in ids:
        assert _REVISION_ID.match(revision), f"revision {revision!r} is not a 4-digit counter"
    assert len(set(ids)) == len(ids), f"duplicate revision id in {ids}"
    assert ids == [f"{n:04d}" for n in range(1, len(ids) + 1)], f"gap in the chain: {ids}"


def test_each_revision_points_at_its_predecessor() -> None:
    expected: str | None = None
    for script in _ALL_REVISIONS:
        assert (
            script.down_revision == expected
        ), f"{script.revision} has down_revision={script.down_revision!r}, expected {expected!r}"
        expected = script.revision


def _function_body(source: str, name: str) -> list[ast.stmt]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.body
    raise AssertionError(f"no `def {name}()` in the revision")


def _is_effectively_empty(body: list[ast.stmt]) -> bool:
    for statement in body:
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue
        return False
    return True


@pytest.mark.parametrize("script", _ALL_REVISIONS, ids=lambda s: s.revision)
def test_every_revision_has_a_working_downgrade_or_says_why_not(script: Script) -> None:
    """CLAUDE.md §2. An empty ``downgrade`` is how a chain becomes one-way without
    anyone deciding that it should be."""
    source = revision_source(script)

    if _is_effectively_empty(_function_body(source, "downgrade")):
        assert (
            "no downgrade" in source.lower()
        ), f"{script.revision}: empty downgrade with no comment saying why not"


def _sql(source: str) -> str:
    """Every string literal in the revision that is not a docstring, joined.

    Docstrings are excluded deliberately: each revision's docstring states its
    checklist in prose — "no ENUM · no FLOAT" — and scanning that as if it were DDL
    fails every revision for saying what it does not do.
    """
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


def _ddl_statements(source: str) -> list[str]:
    """DDL verbs found in the revision's SQL, both directions."""
    statements = [match.group(0).upper() for match in _DDL_STATEMENT.finditer(_sql(source))]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "op":
                if node.func.attr in {"create_index", "drop_index"}:
                    statements.append(node.func.attr.upper())
    return statements


@pytest.mark.parametrize("script", _ALL_REVISIONS, ids=lambda s: s.revision)
def test_each_revision_issues_one_ddl_statement_per_direction(script: Script) -> None:
    """Rule 4.8 via §1.1.

    MySQL DDL is atomic per statement but not transactional across them, so a
    revision whose second statement fails
    leaves the schema changed and ``alembic_version`` unstamped — and re-running it
    then fails on the first statement. One statement per direction is what makes the
    version table trustworthy. Secondary indexes may be declared inline in table
    creation or added in a separate revision, never appended as a second DDL.
    """
    source = revision_source(script)
    for direction in ("upgrade", "downgrade"):
        body = ast.unparse(ast.Module(body=_function_body(source, direction), type_ignores=[]))
        statements = _ddl_statements(body)
        assert (
            len(statements) <= 1
        ), f"{script.revision} {direction} issues multiple DDL: {statements}"


def test_ddl_counter_includes_index_helpers_and_raw_sql() -> None:
    assert _ddl_statements('op.create_index("ix", "tenant", ["id"])') == ["CREATE_INDEX"]
    assert (
        len(
            _ddl_statements(
                'op.execute("ALTER TABLE tenant ADD COLUMN test INT"); '
                'op.create_index("ix", "tenant", ["test"])'
            )
        )
        == 2
    )


@pytest.mark.parametrize("script", _ALL_REVISIONS, ids=lambda s: s.revision)
def test_ddl_is_a_literal_with_nothing_interpolated(script: Script) -> None:
    """§5.7. DDL carries no values, so there is nothing to parameterize — which is
    exactly why an f-string or a ``.format`` here is worth catching before someone
    adds the first value."""
    source = revision_source(script)

    for node in ast.walk(ast.parse(source)):
        assert not isinstance(node, ast.JoinedStr), f"{script.revision} builds SQL with an f-string"
    assert ".format(" not in source, f"{script.revision} interpolates into SQL"


@pytest.mark.parametrize("script", _ALL_REVISIONS, ids=lambda s: s.revision)
def test_every_create_table_sets_engine_charset_collate_and_row_format(script: Script) -> None:
    """§1.6: never inherited from the server default. A server rebuilt with a
    different default silently changes collation, and collation changes comparison
    semantics on every VARCHAR key."""
    sql = _sql(revision_source(script))
    if not _CREATE_TABLE.search(sql):
        return

    for expected in (
        "ENGINE=InnoDB",
        "DEFAULT CHARSET=utf8mb4",
        "COLLATE=utf8mb4_unicode_ci",
        "ROW_FORMAT=DYNAMIC",
    ):
        assert expected in sql, f"{script.revision}: CREATE TABLE without {expected}"


@pytest.mark.parametrize("script", _ALL_REVISIONS, ids=lambda s: s.revision)
def test_no_revision_carries_seed_data(script: Script) -> None:
    """Seeds live in ``seeds/`` and are re-runnable (CLAUDE.md §2). Seed data in a
    revision runs once, in one environment, and cannot be corrected."""
    source = revision_source(script)
    assert "op.bulk_insert(" not in source, f"{script.revision} contains seed data"
    assert not re.search(
        r"\bINSERT\s+INTO\b", _sql(source), re.IGNORECASE
    ), f"{script.revision} contains seed data"


@pytest.mark.parametrize("script", _ALL_REVISIONS, ids=lambda s: s.revision)
def test_no_revision_declares_an_enum_or_a_float(script: Script) -> None:
    """Enums are VARCHAR + app validation: altering a MySQL ENUM rebuilds the table.
    Money and quantities are DECIMAL(19,4); a FLOAT column is a rounding bug with a
    schema (CLAUDE.md §4)."""
    sql = _sql(revision_source(script))

    assert not re.search(
        r"\bENUM\s*\(", sql, re.IGNORECASE
    ), f"{script.revision} declares an ENUM column"
    for forbidden in (r"\bFLOAT\b", r"\bDOUBLE\b", r"\bREAL\b"):
        assert not re.search(
            forbidden, sql, re.IGNORECASE
        ), f"{script.revision} declares a {forbidden.strip('\\b')} column"


# --- the hand-written DDL against the models ----------------------------------


def _ddl_parts(body: str) -> list[str]:
    """DDL columns can share a line; commas inside types/constraints are not separators."""
    parts: list[str] = []
    depth, start = 0, 0
    quote: str | None = None
    for position, char in enumerate(body):
        if quote is not None:
            if char == quote:
                quote = None
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(body[start:position])
            start = position + 1
    parts.append(body[start:])
    return parts


def test_ddl_column_parser_handles_shared_lines_and_decimal_commas() -> None:
    sql = """CREATE TABLE example (
      id BINARY(16) NOT NULL, amount DECIMAL(19,4) NULL,
      label VARCHAR(30) DEFAULT 'a,b', PRIMARY KEY(id)
    ) ENGINE=InnoDB"""
    assert set(_parse_columns("op.execute(" + repr(sql) + ")")) == {"id", "amount", "label"}


def _parse_columns(source: str) -> dict[str, tuple[str, str, bool]]:
    """``{column: (table, sql_type, nullable)}`` for a revision's ``CREATE TABLE``.

    Constraint and key lines are skipped, including ones wrapped across lines.
    """
    match = _CREATE_TABLE.search(_sql(source))
    if match is None:
        return {}

    table = match.group(1)
    columns: dict[str, tuple[str, str, bool]] = {}
    continuing = False
    for raw in _ddl_parts(re.sub(r"--[^\n]*", "", match.group(2))):
        line = " ".join(raw.split()).rstrip(",")
        if not line:
            continue
        if continuing:
            # A constraint wrapped onto this line must not be read as a column.
            continuing = not line.endswith((")", "),"))
            continue

        parsed = _COLUMN_LINE.match(line)
        quoted = parsed is not None and bool(parsed.group(1))
        if parsed is None or (not quoted and parsed.group(2).lower() in _NOT_A_COLUMN):
            continuing = parsed is not None and line.count("(") > line.count(")")
            continue
        rest = parsed.group(4).upper()
        columns[parsed.group(2)] = (table, parsed.group(3).upper(), "NOT NULL" not in rest)
    return columns


def _revision_tables() -> dict[str, dict[str, tuple[str, str, bool]]]:
    """Every table the chain creates, keyed by table name."""
    tables: dict[str, dict[str, tuple[str, str, bool]]] = {}
    for script in _ALL_REVISIONS:
        parsed = _parse_columns(revision_source(script))
        if parsed:
            tables[next(iter(parsed.values()))[0]] = parsed
        source = revision_source(script)
        upgrade_sql = _sql(
            ast.unparse(ast.Module(body=_function_body(source, "upgrade"), type_ignores=[]))
        )
        alter = re.search(r"ALTER\s+TABLE\s+(\w+)", upgrade_sql, re.IGNORECASE)
        # Later revisions use Alembic's typed helper rather than raw SQL.
        # Account for additions without modifying already published migrations.
        for node in _function_body(source, "upgrade"):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            if (
                not isinstance(call.func, ast.Attribute)
                or call.func.attr != "add_column"
                or len(call.args) < 2
                or not isinstance(call.args[0], ast.Constant)
                or not isinstance(call.args[1], ast.Call)
            ):
                continue
            table_name = call.args[0].value
            column_call = call.args[1]
            column_name = ast.literal_eval(column_call.args[0])
            if not isinstance(table_name, str) or not isinstance(column_name, str):
                raise AssertionError("migration table and column names must be strings")
            type_node = column_call.args[1]
            type_name = ast.unparse(type_node).removeprefix("sa.").upper()
            nullable = next(
                (ast.literal_eval(kw.value) for kw in column_call.keywords if kw.arg == "nullable"),
                True,
            )
            tables[table_name][column_name] = (table_name, type_name, nullable)
        if alter:
            table = alter.group(1)
            for line in upgrade_sql.splitlines():
                addition = re.search(r"\bADD\s+COLUMN\s+(.+)", line, re.IGNORECASE)
                column = _COLUMN_LINE.match(addition.group(1)) if addition else None
                if column:
                    tables[table][column.group(2)] = (
                        table,
                        column.group(3).upper(),
                        "NOT NULL" not in column.group(4).upper(),
                    )
    return tables


_REVISION_TABLES = _revision_tables()


def test_the_chain_creates_every_model_table() -> None:
    """A model with no revision is a table that exists in tests and not in
    production — the failure mode of keeping models and migrations in two trees
    (CLAUDE.md §4)."""
    assert set(_REVISION_TABLES) == set(Base.metadata.tables), (
        f"models only: {sorted(set(Base.metadata.tables) - set(_REVISION_TABLES))}; "
        f"revisions only: {sorted(set(_REVISION_TABLES) - set(Base.metadata.tables))}"
    )


@pytest.mark.parametrize("table_name", sorted(_REVISION_TABLES))
def test_ddl_columns_match_the_model(table_name: str) -> None:
    """Names and nullability, parsed out of the raw DDL.

    This is the compensating control for hand-writing the DDL: a typo, a dropped
    column or a flipped nullability is caught here rather than by a failing query.
    Types are checked exhaustively against a real server by
    ``test_models_and_head_do_not_drift``.
    """
    parsed = _REVISION_TABLES[table_name]
    model_columns = Base.metadata.tables[table_name].columns

    assert set(parsed) == set(model_columns.keys()), (
        f"{table_name}: DDL only={sorted(set(parsed) - set(model_columns.keys()))}, "
        f"model only={sorted(set(model_columns.keys()) - set(parsed))}"
    )
    for name, (_, _, nullable) in parsed.items():
        assert (
            nullable == model_columns[name].nullable
        ), f"{table_name}.{name}: DDL nullable={nullable}, model={model_columns[name].nullable}"


def _impl_of(column_type: object) -> object:
    """The dialect-independent implementation behind a ``TypeDecorator``."""
    return getattr(column_type, "impl", column_type)


@pytest.mark.parametrize("table_name", sorted(_REVISION_TABLES))
def test_ddl_column_types_follow_the_platform_scales(table_name: str) -> None:
    """The three scales that corrupt data silently when they drift.

    ``BINARY(16)`` for ids, ``DATETIME(6)`` for timestamps, ``DECIMAL(19,4)`` for
    every amount and quantity. Second-granularity timestamps cannot order two writes
    in one request, and MySQL narrows to a narrower DECIMAL scale without
    raising.
    """
    model_columns = Base.metadata.tables[table_name].columns

    for name, (_, sql_type, _) in _REVISION_TABLES[table_name].items():
        impl = _impl_of(model_columns[name].type)

        if isinstance(impl, BINARY):
            assert sql_type == "BINARY(16)", f"{table_name}.{name} is {sql_type}, not BINARY(16)"
        if name.endswith("_at"):
            assert sql_type == "DATETIME(6)", f"{table_name}.{name} is {sql_type}, not DATETIME(6)"
            assert isinstance(impl, DateTime), f"{table_name}.{name} is not a datetime in the model"
        if sql_type.startswith(("DECIMAL", "NUMERIC")):
            assert (
                sql_type.replace(" ", "") == "DECIMAL(19,4)"
            ), f"{table_name}.{name} is {sql_type}; the storage scale is fixed at (19,4)"
            assert isinstance(impl, Numeric)


#: The one table whose ``value_*`` columns are polymorphic *value* stores, not business
#: dates or timestamps: ``custom_field_value_index.value_date`` is a DATETIME(6) holding
#: both `date` and `datetime` custom-field values (docs/identity-schema.md §6.3). The
#: ``_date``→DATE / DATETIME→``_at`` naming convention is about posting/document dates and
#: does not apply here, so this table is exempt from that one check.
_VALUE_STORE_TABLES = frozenset({"custom_field_value_index"})


@pytest.mark.parametrize("table_name", sorted(_REVISION_TABLES))
def test_business_dates_are_dates_and_datetimes_end_in_at(table_name: str) -> None:
    """CLAUDE.md §4. A datetime for a posting or document date makes the period it
    falls in depend on a timezone."""
    if table_name in _VALUE_STORE_TABLES:
        return
    for name, (_, sql_type, _) in _REVISION_TABLES[table_name].items():
        if name.endswith("_date"):
            assert sql_type == "DATE", f"{table_name}.{name} is {sql_type}, not DATE"
        if sql_type.startswith("DATETIME"):
            assert name.endswith("_at"), f"{table_name}.{name} is a DATETIME not suffixed _at"


# --- configuration ------------------------------------------------------------


def _ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(ALEMBIC_INI, encoding="utf-8")
    return parser


def test_file_template_is_the_sequential_one() -> None:
    # configparser resolves alembic's `%%` escaping to a single `%`.
    assert _ini()["alembic"]["file_template"] == "%(rev)s_%(slug)s"


def test_the_ini_holds_no_database_url() -> None:
    """CLAUDE.md §5.9: no secrets in the repo. env.py reads the URL from the
    environment, so the key must be absent here — not present and blank, which a
    later edit would quietly fill in."""
    assert "sqlalchemy.url" not in _ini()["alembic"]


# --- against real MySQL -------------------------------------------------------


def _table_names(url: str) -> set[str]:
    """Table names currently in the schema, via a throwaway async connection."""

    async def run() -> set[str]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return set(await connection.run_sync(lambda c: inspect(c).get_table_names()))
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.mark.mysql
def test_upgrade_head_then_downgrade_base_leaves_a_clean_schema(mysql_url: str) -> None:
    """The D0 exit criterion (docs/identity-db-plan.md §3).

    Asserted in both directions on purpose: a ``downgrade`` that leaves a table, an
    index or an orphaned FK behind is the failure mode, and it is invisible from the
    upgrade side.
    """
    config = alembic_config(mysql_url)

    command.upgrade(config, "head")
    after_upgrade = _table_names(mysql_url)
    assert "alembic_version" in after_upgrade
    assert set(Base.metadata.tables) <= after_upgrade

    command.downgrade(config, "base")
    after_downgrade = _table_names(mysql_url)

    assert after_downgrade <= {
        "alembic_version"
    }, f"downgrade left tables behind: {sorted(after_downgrade - {'alembic_version'})}"


@pytest.mark.mysql
def test_models_and_head_do_not_drift(mysql_url: str) -> None:
    """The models are the source of truth; the chain must reproduce them exactly.

    This is the test that catches what a hand-written revision gets wrong on
    MySQL — VARCHAR length, index name, DECIMAL scale, collation — because it
    compares the *applied* schema against the metadata rather than trusting the
    author.
    """
    command.upgrade(alembic_config(mysql_url), "head")

    def diff(connection: Connection) -> list[object]:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        return list(compare_metadata(context, Base.metadata))

    async def run() -> list[object]:
        engine = create_async_engine(mysql_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(diff)
        finally:
            await engine.dispose()

    assert asyncio.run(run()) == [], "models drifted from head"


@pytest.mark.mysql
def test_account_review_migrations_round_trip(mysql_url: str) -> None:
    config = alembic_config(mysql_url)
    command.upgrade(config, "head")
    assert {"account_review", "account_review_command"} <= _table_names(mysql_url)
    command.downgrade(config, "0080")
    assert not {"account_review", "account_review_command"} & _table_names(mysql_url)
    command.upgrade(config, "head")
    assert {"account_review", "account_review_command"} <= _table_names(mysql_url)


@pytest.mark.mysql
def test_classification_upgrade_preserves_existing_company(mysql_url: str) -> None:
    """Upgrade a populated pre-classification database and exercise its new bindings."""
    from billing_platform.db import create_session_factory
    from billing_platform.db.tenant_context import tenant_scope, unfiltered
    from billing_platform.ids import uuid7
    from sqlalchemy import insert, select

    from identity.models import Company, CompanyBusinessRole
    from identity.seeds.business_classifications import seed_business_classifications
    from tests.factories import build_company, build_tenant, seed_jurisdiction

    config = alembic_config(mysql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "0037")
    tenant_id, company_id = uuid7(), uuid7()

    async def old_company() -> None:
        engine = create_async_engine(mysql_url, poolclass=NullPool)
        try:
            async with create_session_factory(engine)() as session:
                with unfiltered():
                    await seed_jurisdiction(session)
                    session.add(build_tenant(tenant_id=tenant_id))
                    await session.flush()
                    row = build_company(tenant_id=tenant_id, company_id=company_id)
                    values = {
                        c.key: getattr(row, c.key)
                        for c in Company.__table__.columns
                        if c.key not in {"business_category_code", "store_format_code"}
                        and getattr(row, c.key) is not None
                    }
                    await session.execute(insert(Company).values(**values))
                    await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(old_company())
    command.upgrade(config, "head")

    async def check_upgraded() -> None:
        engine = create_async_engine(mysql_url, poolclass=NullPool)
        try:
            async with create_session_factory(engine)() as session:
                await seed_business_classifications(session)
                with tenant_scope(tenant_id):
                    row = await session.get(Company, company_id)
                    assert row is not None and row.code == "MAIN"
                    assert row.business_category_code is None
                    assert row.store_format_code is None
                    assert row.business_roles == []
                    row.business_category_code = "pharmaceutical"
                    row.business_roles = ["distributor", "wholesaler"]
                    await session.commit()
                    session.expire_all()
                    row = await session.get(Company, company_id)
                    assert row is not None and row.business_roles == ["distributor", "wholesaler"]
                    assert len(list(await session.scalars(select(CompanyBusinessRole)))) == 2
        finally:
            await engine.dispose()

    asyncio.run(check_upgraded())
    command.downgrade(config, "0037")

    # All new tables/columns can be removed while preserving the original company.
    async def check_downgraded() -> None:
        engine = create_async_engine(mysql_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                assert await connection.scalar(select(Company.id)) == company_id
        finally:
            await engine.dispose()

    asyncio.run(check_downgraded())
    command.downgrade(config, "base")
