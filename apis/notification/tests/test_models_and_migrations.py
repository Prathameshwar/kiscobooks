from __future__ import annotations

import ast
import re
from pathlib import Path

from notification.metadata import TABLES, service_metadata

ROOT = Path(__file__).resolve().parents[3]
VERSIONS = ROOT / "dbs" / "notification" / "versions"


def _literal(module: ast.Module, name: str) -> object:
    for node in module.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == name
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing {name}")


def _modules() -> list[tuple[Path, str, str | None]]:
    found: list[tuple[Path, str, str | None]] = []
    for path in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        down = _literal(tree, "down_revision")
        assert down is None or isinstance(down, str)
        found.append((path, str(_literal(tree, "revision")), down))
    return found


def test_chain_is_gapless_reversible_and_one_create_per_revision() -> None:
    modules = _modules()
    assert len(modules) >= 89
    previous = None
    created = set()
    for number, (path, revision, down_revision) in enumerate(modules, 1):
        assert revision == f"{number:04d}"
        assert down_revision == previous
        previous = revision
        source = path.read_text(encoding="utf-8")
        if revision == "0026":
            assert "ALTER TABLE recipient_endpoint" in source
            assert "DROP COLUMN company_id" in source
            continue
        if int(revision) >= 27:
            tree = ast.parse(source)
            upgrade = next(
                n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
            )
            statements = [
                ast.literal_eval(n.value.args[0])
                for n in upgrade.body
                if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
            ]
            assert sum(bool(re.match(r"\s*(CREATE|ALTER|DROP) ", sql)) for sql in statements) <= 1
            for sql in statements:
                match = re.search(r"CREATE TABLE (\w+)", sql)
                if match:
                    created.add(match.group(1))
            continue
        assert source.count("CREATE TABLE ") == 1
        assert source.count("DROP TABLE ") == 1
        match = re.search(r"CREATE TABLE (\w+)", source)
        assert match
        created.add(match.group(1))
        assert "ENGINE=InnoDB" in source
        ddl = source[source.index('_CREATE = """') : source.index('"""\n\ndef upgrade')]
        assert not re.search(r"\b(?:ENUM|FLOAT|DOUBLE)\b", ddl)
    assert created == TABLES


def test_service_metadata_is_exactly_the_migration_inventory() -> None:
    assert set(service_metadata().tables) == TABLES


def test_delivery_assignment_foreign_keys_match_applied_lineage_migration() -> None:
    table = service_metadata().tables["notification_delivery"]
    keys = {
        tuple(column.name for column in key.columns): key
        for key in table.foreign_key_constraints
        if "use_case_binding_id" in key.columns
    }
    expected = {
        ("use_case_binding_id",): "fk_notification_delivery_assignment",
        (
            "use_case_binding_id",
            "tenant_id",
            "space_id",
        ): "fk_notification_delivery_use_case_binding_id_space",
    }
    assert set(keys) == set(expected)
    migration = (VERSIONS / "0113_delivery_assignment_lineage.py").read_text()
    for columns, name in expected.items():
        key = keys[columns]
        assert key.name == name
        assert f"ADD CONSTRAINT {name}" in migration
        assert key.referred_table.name == "notification_use_case_binding"
        assert tuple(element.column.name for element in key.elements) == ("id", *columns[1:])
        assert key.ondelete in (None, "RESTRICT")


def test_every_migration_column_matches_its_model() -> None:
    metadata = service_metadata()
    for path in sorted(VERSIONS.glob("*.py")):
        if int(path.name[:4]) >= 27:
            continue
        source = path.read_text(encoding="utf-8")
        match = re.search(r"CREATE TABLE (\w+) \((.*?)\) ENGINE", source, re.DOTALL)
        if path.name.startswith("0026_"):
            assert "ADD COLUMN company_id BINARY(16) NULL" in source
            assert "MODIFY COLUMN company_id BINARY(16) NOT NULL" in source
            continue
        assert match
        table_name, body = match.groups()
        columns: set[str] = set()
        nullability: dict[str, bool] = {}
        for line in body.splitlines():
            if (
                line.strip()
                .lower()
                .startswith(("constraint ", "key ", "primary ", "unique ", "foreign ", "check "))
            ):
                continue
            column = re.match(r"\s*`?(\w+)`?\s+[A-Z]", line, re.IGNORECASE)
            if column:
                name = column.group(1)
                columns.add(name)
                nullability[name] = "NOT NULL" not in line.upper()
        model = metadata.tables[table_name]
        if table_name == "provider_event":
            columns.add("attempt_key")
            nullability["attempt_key"] = True
        if table_name == "notification_delivery":
            columns.add("use_case_binding_id")
            nullability["use_case_binding_id"] = True
        if table_name == "recipient_endpoint":
            columns.add("company_id")
            nullability["company_id"] = False
        if table_name == "notification_request":
            columns.add("target_tenant_id")
            nullability["target_tenant_id"] = True
            nullability["context_ciphertext"] = True
        if "space_id" in model.columns:
            columns.add("space_id")
            nullability["space_id"] = False
        assert columns == set(model.columns.keys()), table_name
        for name in columns:
            assert nullability[name] == model.columns[name].nullable, f"{table_name}.{name}"
