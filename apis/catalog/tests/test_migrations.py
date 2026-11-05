import ast
import io
import re
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import mysql

from catalog.metadata import MIGRATION_HEAD, TABLES, service_metadata

ROOT = Path(__file__).resolve().parents[3]


def config() -> Config:
    return Config(str(ROOT / "dbs/catalog/alembic.ini"))


def test_literal_single_ddl_revisions_match_shared_models() -> None:
    scripts = list(reversed(list(ScriptDirectory.from_config(config()).walk_revisions())))
    assert [script.revision for script in scripts] == [
        f"{n:04d}" for n in range(1, int(MIGRATION_HEAD) + 1)
    ]
    metadata = service_metadata()
    assert set(metadata.tables) == TABLES
    additions: dict[str, dict[str, tuple[str, bool]]] = {}
    removals: dict[str, set[str]] = {}
    for script in scripts:
        module = ast.parse(Path(script.path).read_text(encoding="utf-8"))
        for node in module.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "_ALTER" for target in node.targets
            ):
                alteration = ast.literal_eval(node.value)
                target_table = re.search(r"ALTER TABLE (\w+)", alteration)
                assert target_table is not None
                added = additions.setdefault(target_table.group(1), {})
                removals.setdefault(target_table.group(1), set()).update(
                    re.findall(r"DROP COLUMN (\w+)", alteration)
                )
                for added_match in re.finditer(
                    r"ADD COLUMN (\w+) ([A-Z]+(?:\(\d+(?:,\d+)?\))?) "
                    r"(?:GENERATED ALWAYS AS .+? STORED )?(NULL|NOT NULL)",
                    alteration,
                ):
                    added[added_match.group(1)] = (
                        added_match.group(2),
                        added_match.group(3) == "NULL",
                    )
    predecessor = None
    seen = set()
    for script in scripts:
        assert script.down_revision == predecessor
        predecessor = script.revision
        module = ast.parse(Path(script.path).read_text(encoding="utf-8"))
        literals = [
            ast.literal_eval(node.value)
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in {"_CREATE", "_ALTER"} for t in node.targets)
        ]
        if not literals:
            upgrade = next(
                node
                for node in module.body
                if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
            )
            literals = [
                ast.literal_eval(node.value.args[0])
                for node in upgrade.body
                if isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "execute"
            ]
        assert len(literals) == 1, script.revision
        ddl = literals[0]
        if ddl.lstrip().startswith("ALTER TABLE"):
            ddl = " ".join(ddl.split())
            local_additions = set(re.findall(r"ADD COLUMN (\w+)", ddl))
            assert len(re.findall(r"\bALTER TABLE\b", ddl)) == 1
            assert not re.search(r"\b(CREATE|INSERT|UPDATE|DELETE|FLOAT|DOUBLE|ENUM)\b|;", ddl)
            if re.search(r"\bDROP\b", ddl):
                allowed = {
                    "0131": "DROP CHECK ck_item_attribute_value_p76_scalar_type",
                    "0127": "DROP INDEX uq_p72_1",
                    "0128": "DROP INDEX uq_p72_2",
                    "0120": "DROP INDEX uq_tax_classification_start",
                    "0121": "DROP INDEX uq_tax_rate_start",
                    "0122": "DROP INDEX uq_catalog_tax_binding_start",
                    "0123": "DROP CHECK ck_master_alias_master_alias_entity",
                    "0124": "DROP CHECK ck_master_external_key_master_external_key_entity",
                    "0172": "DROP INDEX uq_v88_1",
                    "0174": "DROP CHECK ck_item_regulatory_kind",
                    "0175": "DROP CHECK ck_item_regulatory_class_shape",
                    "0211": "DROP COLUMN source_reference",
                    "0212": "DROP COLUMN source_reference",
                    "0213": "DROP COLUMN source_reference",
                    "0219": "DROP CHECK ck_import_job_import_job_state",
                    "0221": "DROP INDEX uq_v86_1",
                }
                assert script.revision in allowed and allowed[script.revision] in ddl
                assert len(re.findall(r"\bDROP\b", ddl)) == (2 if script.revision == "0221" else 1)
                if script.revision == "0221":
                    assert "DROP CHECK ck_item_price_scope_v86_1" in ddl
                    assert "UNIQUE (tenant_id, company_id, item_id, lot_key)" in ddl
            table_name = re.search(r"ALTER TABLE (\w+)", ddl)
            assert table_name is not None
            assert table_name.group(1) in seen
            table = metadata.tables[table_name.group(1)]
            for foreign in table.foreign_key_constraints:
                if any(column.name in local_additions for column in foreign.columns):
                    assert f"ADD CONSTRAINT {foreign.name}" in ddl
                    target = foreign.elements[0].column.table.name
                    reference = (
                        "(" + ", ".join(element.column.name for element in foreign.elements) + ")"
                    )
                    assert f"REFERENCES {target} {reference}" in ddl
                    assert "(" + ", ".join(column.name for column in foreign.columns) + ")" in ddl
            for index in table.indexes:
                if any(column.name in local_additions for column in index.columns):
                    assert f"ADD INDEX {index.name}" in ddl
                    assert "(" + ", ".join(column.name for column in index.columns) + ")" in ddl
            functions = {n.name: n for n in module.body if isinstance(n, ast.FunctionDef)}
            assert set(functions) == {"upgrade", "downgrade"}
            assert len(functions["upgrade"].body) == 1
            if script.revision in {"0214", "0215", "0216", "0217"}:
                # Additive markers keep one DDL plus a read-only rollback guard;
                # removing them would change retained policy/pin semantics.
                rollback = functions["downgrade"].body
                assert len(rollback) == 4
                assert isinstance(rollback[0], ast.If)
                assert "is_offline_mode" in ast.unparse(rollback[0])
                assert isinstance(rollback[1], ast.Assign)
                assert isinstance(rollback[2], ast.If)
                assert len(rollback[2].body) == 1 and isinstance(rollback[2].body[0], ast.Raise)
                assert isinstance(rollback[3], ast.Expr)
                query, removal = {
                    "0214": (
                        "SELECT 1 FROM product_configuration_adoption",
                        "DROP COLUMN resolution_version",
                    ),
                    "0215": ("SELECT 1 FROM tax_rule", "DROP COLUMN classification_scope"),
                    "0216": (
                        "SELECT 1 FROM product_pricing_policy",
                        "DROP COLUMN unit_prices_mode",
                    ),
                    "0217": (
                        "SELECT 1 FROM product_entry_option_policy",
                        "DROP COLUMN model_mode",
                    ),
                }[script.revision]
                assert query in ast.unparse(rollback[1])
                assert removal in ast.unparse(rollback[3])
            elif script.revision == "0221":
                rollback = functions["downgrade"].body
                assert len(rollback) == 2 and isinstance(rollback[0], ast.If)
                assert "WHERE lot_id IS NOT NULL" in ast.unparse(rollback[0])
                assert "DROP COLUMN lot_key" in ast.unparse(rollback[1])
            elif script.revision == "0219":
                rollback = functions["downgrade"].body
                assert len(rollback) == 2 and isinstance(rollback[0], ast.If)
                assert "SELECT COUNT(*) FROM import_job" in ast.unparse(rollback[0])
                assert "VALIDATING" in ddl and "IMPORTING" in ddl
                assert "ADD CONSTRAINT ck_import_job_import_job_state" in ddl
            else:
                assert len(functions["downgrade"].body) == 1
            continue
        assert len(re.findall(r"\bCREATE TABLE\b", ddl)) == 1
        assert not re.search(r"\b(ALTER|INSERT|FLOAT|DOUBLE|ENUM)\b|;", ddl)
        name = re.search(r"CREATE TABLE (\w+)", ddl)
        assert name is not None
        table = metadata.tables[name.group(1)]
        seen.add(table.name)
        columns = {}
        for line in ddl.splitlines():
            # The literal CREATE convention lists columns before table constraints.
            # Constraint continuation lines may contain "value_number IS NOT NULL";
            # they are expressions, never column declarations.
            if line.lstrip().startswith(("CONSTRAINT ", "KEY ", "PRIMARY KEY ")):
                break
            match = re.match(
                r"\s*`?(\w+)`? ([A-Z]+(?:\(\d+(?:,\d+)?\))?) (?:COLLATE \w+ )?"
                r"(?:GENERATED ALWAYS AS .+? (?:STORED|VIRTUAL) )?(NULL|NOT NULL)",
                line,
            )
            if match:
                columns[match.group(1)] = (match.group(2), match.group(3) == "NULL")
            else:
                # MySQL permits nullable column declarations without an explicit NULL.
                implicit = re.fullmatch(r"\s*`?(\w+)`? ([A-Z]+(?:\(\d+(?:,\d+)?\))?)\s*,?\s*", line)
                if implicit:
                    columns[implicit.group(1)] = (implicit.group(2), True)
        columns.update(additions.get(table.name, {}))
        for removed in removals.get(table.name, set()):
            assert removed in columns
            del columns[removed]
        assert set(columns) == set(table.columns.keys()), table.name
        for column in table.columns:
            ddl_type, nullable = columns[column.name]
            model_type = (
                column.type.compile(dialect=mysql.dialect())
                .upper()
                .split(" COLLATE ")[0]
                .replace(", ", ",")
            )
            canonical = {"TINYINT(1)": "BOOL", "BOOLEAN": "BOOL", "INT": "INTEGER"}
            assert canonical.get(ddl_type, ddl_type) == model_type
            assert nullable == column.nullable
        functions = {n.name: n for n in module.body if isinstance(n, ast.FunctionDef)}
        assert set(functions) == {"upgrade", "downgrade"}
        if script.revision in {"0218", "0220", "0222", "0223"}:
            assert len(functions["upgrade"].body) == 1
            rollback = functions["downgrade"].body
            assert len(rollback) == 2 and isinstance(rollback[0], ast.If)
            name = {
                "0218": "simple_product_creation",
                "0220": "item_stock_choice",
                "0222": "advanced_product_draft",
                "0223": "advanced_product_creation",
            }[script.revision]
            # This name comes only from the literal revision allowlist above.
            assert "SELECT COUNT(*) FROM " + name in ast.unparse(rollback[0])  # noqa: S608
            assert "DROP TABLE " + name in ast.unparse(rollback[1])
        else:
            assert all(len(n.body) == 1 for n in functions.values())
    assert seen == TABLES and predecessor == MIGRATION_HEAD


def test_promotion_create_constraints_match_scoped_models() -> None:
    """The CREATE parser above checks columns; publication FKs/checks must match too."""
    from sqlalchemy import CheckConstraint

    metadata = service_metadata()

    def compact(value: object) -> str:
        return re.sub(r"\s+", "", str(value))

    sources = (
        (161, "promotion", "0161_create_promotion.py"),
        (162, "promotion_revision", "0162_create_promotion_revision.py"),
        (163, "promotion_benefit", "0163_create_promotion_benefit.py"),
        (164, "promotion_sku_target", "0164_create_promotion_sku_target.py"),
        (165, "promotion_price_level_target", "0165_create_promotion_price_level_target.py"),
        (166, "promotion_stack_policy", "0166_promotion_stack_policy.py"),
        (167, "promotion_stack_group", "0167_promotion_stack_group.py"),
        (168, "promotion_stack_permission", "0168_promotion_stack_permission.py"),
    )
    for _revision, name, filename in sources:
        source = (ROOT / "dbs/catalog/versions" / filename).read_text()
        module = ast.parse(source)
        ddl = next(
            ast.literal_eval(node.value)
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_CREATE" for target in node.targets
            )
        )
        if name == "promotion_revision":
            for extra_name in (
                "0169_promotion_revision_stack_policy_fk.py",
                "0170_promotion_revision_stack_group_fk.py",
            ):
                extra = ast.parse((ROOT / "dbs/catalog/versions" / extra_name).read_text())
                ddl += "\n" + next(
                    ast.literal_eval(node.value)
                    for node in extra.body
                    if isinstance(node, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "_ALTER"
                        for target in node.targets
                    )
                )
        table = metadata.tables[name]
        normalized = compact(ddl)
        for foreign in table.foreign_key_constraints:
            columns = ",".join(column.name for column in foreign.columns)
            target = foreign.elements[0].column.table.name
            target_columns = ",".join(element.column.name for element in foreign.elements)
            assert (
                compact(
                    f"CONSTRAINT {foreign.name} FOREIGN KEY ({columns}) "
                    f"REFERENCES {target} ({target_columns})"
                )
                in normalized
            )
        for check in table.constraints:
            if isinstance(check, CheckConstraint):
                assert compact(f"CONSTRAINT {check.name} CHECK ({check.sqltext})") in normalized


def test_offline_mysql_upgrade_and_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALOG_DATABASE_URL", "mysql+asyncmy://localhost/catalog")
    output = io.StringIO()
    cfg = config()
    cfg.output_buffer = output
    command.upgrade(cfg, "head", sql=True)
    assert (
        output.getvalue().count("CREATE TABLE") == len(TABLES) + 1
    )  # includes Alembic's version table
    output.seek(0)
    output.truncate()
    with pytest.raises(RuntimeError, match="retain batch price scopes"):
        command.downgrade(cfg, "0221:0219", sql=True)
    with pytest.raises(RuntimeError, match="advanced product drafts"):
        command.downgrade(cfg, "0222:0221", sql=True)
        with pytest.raises(RuntimeError, match="advanced product creation receipts"):
            command.downgrade(cfg, "0223:0222", sql=True)
    with pytest.raises(RuntimeError, match="retain product tracking choices"):
        command.downgrade(cfg, "0220:0219", sql=True)
    with pytest.raises(RuntimeError, match="Import continuation rollback"):
        command.downgrade(cfg, "0219:0213", sql=True)
    with pytest.raises(RuntimeError, match="retain simple product"):
        command.downgrade(cfg, "0218:0213", sql=True)
    with pytest.raises(RuntimeError, match="online validation"):
        command.downgrade(cfg, "0217:0213", sql=True)
    with pytest.raises(RuntimeError, match="measured integer"):
        command.downgrade(cfg, "0213:0130", sql=True)
    with pytest.raises(RuntimeError, match="must be retained"):
        command.downgrade(cfg, "0130:0129", sql=True)
    with pytest.raises(RuntimeError, match="adoption gates"):
        command.downgrade(cfg, "0129:0128", sql=True)
    command.downgrade(cfg, "0128:0126", sql=True)
    with pytest.raises(NotImplementedError, match="retained history"):
        command.downgrade(cfg, "0126:0125", sql=True)
    command.downgrade(cfg, "0125:base", sql=True)
    # Creation receipts, tracking choices and user drafts are retained.
    assert output.getvalue().count("DROP TABLE") == len(TABLES) - 4


@pytest.mark.mysql
@pytest.mark.skipif(shutil.which("docker") is None, reason="live MySQL roundtrip requires Docker")
def test_live_mysql_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import Connection
    from sqlalchemy.ext.asyncio import create_async_engine
    from testcontainers.mysql import MySqlContainer

    async def differences(url: str) -> list[object]:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:

                def compare(sync: Connection) -> list[object]:
                    return list(
                        compare_metadata(MigrationContext.configure(sync), service_metadata())
                    )

                return await connection.run_sync(compare)
        finally:
            await engine.dispose()

    # Ephemeral container; no existing database is upgraded or dropped by this test.
    with MySqlContainer("mysql:9.6") as container:
        url = container.get_connection_url().replace("mysql+pymysql", "mysql+asyncmy")
        monkeypatch.setenv("CATALOG_DATABASE_URL", url)
        command.upgrade(config(), "head")
        assert asyncio.run(differences(url)) == []
        with pytest.raises(RuntimeError, match="measured integer"):
            command.downgrade(config(), "0129")
        command.upgrade(config(), "head")
        assert asyncio.run(differences(url)) == []


def test_measured_integer_check_migration_matches_current_model() -> None:
    from sqlalchemy import CheckConstraint

    table = service_metadata().tables["item_attribute_value"]
    check = next(
        c
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_item_attribute_value_p76_scalar_type"
    )
    module = ast.parse(
        (ROOT / "dbs/catalog/versions/0131_measured_integer_attributes.py").read_text()
    )
    ddl = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_ALTER" for t in node.targets)
    )

    def normalize(value: object) -> str:
        return re.sub(r"\s+", "", str(value))

    assert normalize(check.sqltext) in normalize(ddl)
    assert ddl.count("ALTER TABLE") == 1 and "DROP CHECK" in ddl
