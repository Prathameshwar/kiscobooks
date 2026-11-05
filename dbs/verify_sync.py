"""Read-only model/migration/MySQL verification, isolated per service interpreter.

Run from the repository: python dbs/verify_sync.py [--service design] [--output-dir PATH].
Database credentials come from private service environment files, never arguments.
This command does not create, upgrade, stamp, repair or drop database objects.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import Connection, MetaData

ROOT = Path(__file__).resolve().parents[1]
SERVICES = (
    "identity",
    "audit",
    "catalog",
    "notification",
    "accounting",
    "vouchers",
    "reports",
    "design",
)


def database_environment(path: Path, key: str) -> str:
    """Reject ambiguous configuration without including values in errors."""
    values = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(key + "="):
            values.append(line.partition("=")[2])
    if len(values) != 1 or not values[0].strip():
        raise ValueError("Missing or duplicate database environment key")
    return values[0]


SQLNode = str | tuple["SQLNode", ...]


class SQLExpression:
    """Compare common check/generated expressions without discarding precedence.

    Unknown syntax falls back to exact normalized tokens in canonical_sql.
    This intentionally favors a reviewable difference over guessing equivalence.
    """

    PRECEDENCE = {
        "or": 10,
        "xor": 15,
        "and": 20,
        "=": 40,
        "<>": 40,
        "<": 40,
        ">": 40,
        "<=": 40,
        ">=": 40,
        "is": 40,
        "in": 40,
        "between": 40,
        "not in": 40,
        "not between": 40,
        "+": 50,
        "-": 50,
        "*": 60,
        "/": 60,
        "%": 60,
        "div": 60,
        "mod": 60,
    }

    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.index = 0

    def peek(self) -> str:
        return self.tokens[self.index] if self.index < len(self.tokens) else ""

    def take(self, expected: str | None = None) -> str:
        token = self.peek()
        if not token or (expected is not None and token != expected):
            raise ValueError("Unsupported SQL expression")
        self.index += 1
        return token

    def expression(self, minimum: int = 0) -> SQLNode:
        token = self.take()
        if token in ("not", "+", "-"):
            left: SQLNode = (
                "unary",
                token,
                self.expression(30 if token == "not" else 70),
            )
        elif token == "(":
            members = [self.expression()]
            while self.peek() == ",":
                self.take(",")
                members.append(self.expression())
            self.take(")")
            left = members[0] if len(members) == 1 else ("list", *members)
        elif token == "case":
            parts: list[SQLNode] = []
            if self.peek() != "when":
                parts.append(("base", self.expression()))
            while self.peek() == "when":
                self.take("when")
                condition = self.expression()
                self.take("then")
                parts.append(("when", condition, self.expression()))
            if self.peek() == "else":
                self.take("else")
                parts.append(("else", self.expression()))
            self.take("end")
            left = ("case", *parts)
        elif token == "cast" and self.peek() == "(":
            self.take("(")
            operand = self.expression()
            self.take("as")
            target = self.take()
            if target in ("signed", "unsigned") and self.peek() == "integer":
                self.take("integer")
            self.take(")")
            left = ("cast", operand, target)
        elif re.fullmatch(r"\w+", token) and self.peek() == "(":
            self.take("(")
            arguments: list[SQLNode] = []
            if self.peek() != ")":
                arguments.append(self.expression())
                while self.peek() == ",":
                    self.take(",")
                    arguments.append(self.expression())
            self.take(")")
            left = ("call", token, *arguments)
        elif re.fullmatch(r"\w+(?:\.\w+)*|\d+\.\d+|'(?:''|\\.|[^'])*'", token):
            left = token
        else:
            raise ValueError("Unsupported SQL expression")
        while True:
            operator = self.peek()
            if operator == "not" and self.index + 1 < len(self.tokens):
                operator += " " + self.tokens[self.index + 1]
            priority = self.PRECEDENCE.get(operator, -1)
            if priority < minimum:
                return left
            self.take()
            if operator.startswith("not "):
                self.take()
            if operator.endswith("between"):
                lower = self.expression(priority + 1)
                self.take("and")
                left = (operator, left, lower, self.expression(priority + 1))
                continue
            if operator == "is" and self.peek() == "not":
                self.take("not")
                operator = "is not"
            right = self.expression(priority + 1)
            if operator in ("in", "not in"):
                in_members = (
                    right[1:]
                    if isinstance(right, tuple) and right[0] == "list"
                    else (right,)
                )
                if all(
                    isinstance(member, str)
                    and re.fullmatch(
                        r"'(?:''|\\.|[^'])*'|\d+(?:\.\d+)?|0x[0-9a-f]+", member
                    )
                    for member in in_members
                ):
                    in_members = tuple(sorted(set(in_members)))
                    if len(in_members) == 1:
                        operator, right = (
                            ("=" if operator == "in" else "<>"),
                            in_members[0],
                        )
                    else:
                        right = ("list", *in_members)
            if operator in ("and", "or"):
                lhs = (
                    left[1:]
                    if isinstance(left, tuple) and left[0] == operator
                    else (left,)
                )
                rhs = (
                    right[1:]
                    if isinstance(right, tuple) and right[0] == operator
                    else (right,)
                )
                left = (operator, *lhs, *rhs)
            else:
                left = (operator, left, right)


def normalize_boolean_negation(node: SQLNode) -> SQLNode:
    """Recognize MySQL's De Morgan rewrites, retaining SQL NULL semantics.

    Only logical operators and equality comparisons are rewritten. In particular,
    numeric double negation must not collapse to its non-boolean operand.
    """
    if isinstance(node, str):
        return node
    children = tuple(normalize_boolean_negation(child) for child in node[1:])
    node = (node[0], *children)
    if len(node) == 3 and node[:2] == ("unary", "not"):
        operand = node[2]
        if isinstance(operand, tuple):
            if operand[0] in ("and", "or"):
                inverse = "or" if operand[0] == "and" else "and"
                return normalize_boolean_negation(
                    (inverse, *(("unary", "not", child) for child in operand[1:]))
                )
            if len(operand) == 3 and operand[0] in ("=", "<>"):
                return ("<>" if operand[0] == "=" else "=", *operand[1:])
    if node[0] in ("and", "or"):
        flattened: list[SQLNode] = []
        for child in node[1:]:
            if isinstance(child, tuple) and child[0] == node[0]:
                flattened.extend(child[1:])
            else:
                flattened.append(child)
        return (node[0], *flattened)
    return node


def canonical_sql(value: object) -> str:
    """Normalize native rendering while retaining literals and SQL grouping."""
    pieces = re.split(r"('(?:''|\\.|[^'])*')", str(value))
    for index in range(0, len(pieces), 2):
        piece = pieces[index].lower().replace("`", "").replace("!=", "<>")
        piece = piece.replace("_utf8mb4", "").replace("_utf8mb3", "")
        pieces[index] = piece
    value = "".join(pieces)
    value = re.sub(r"\bx'([0-9a-fA-F]+)'", lambda match: "0x" + match[1].lower(), value)

    tokens = re.findall(r"'(?:''|\\.|[^'])*'|\d+\.\d+|\w+(?:\.\w+)*|<>|<=|>=|\S", value)
    parser = SQLExpression(tokens)
    try:
        expression = parser.expression()
        if parser.peek():
            raise ValueError("Unsupported SQL expression")
    except (ValueError, RecursionError):
        return repr(tokens)
    return repr(normalize_boolean_negation(expression))


def aligned(report: dict[str, object]) -> bool:
    return bool(
        report.get("migration_head")
        and report.get("database_head") == [report["migration_head"]]
        and report.get("readiness_head") in (None, report["migration_head"])
        and not report.get("missing_tables")
        and not report.get("extra_tables")
        and not report.get("native_differences")
        and report.get("alembic_check_exit") == 0
    )


def foreign_key_action(value: str | None) -> str:
    action = (value or "RESTRICT").upper()
    return "RESTRICT" if action == "NO ACTION" else action


async def native_snapshot(code: str, metadata: MetaData, url: str) -> dict[str, object]:
    from sqlalchemy import CheckConstraint, inspect, text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:

            def inspect_schema(conn: Connection) -> dict[str, object]:
                inspector = inspect(conn)
                tables = set(inspector.get_table_names())
                expected = set(metadata.tables)
                differences = []
                for table in metadata.tables.values():
                    if table.name not in tables:
                        continue
                    if inspector.get_pk_constraint(table.name)[
                        "constrained_columns"
                    ] != [column.name for column in table.primary_key.columns]:
                        differences.append({"table": table.name, "kind": "primary_key"})
                    live_keys = {}
                    for key in inspector.get_foreign_keys(table.name):
                        options = key.get("options", {})
                        schema = key.get("referred_schema")
                        live_keys[key["name"]] = (
                            tuple(key["constrained_columns"]),
                            None if schema in (None, code) else schema,
                            key["referred_table"],
                            tuple(key["referred_columns"]),
                            foreign_key_action(options.get("ondelete")),
                            foreign_key_action(options.get("onupdate")),
                        )
                    model_keys = {}
                    for model_key in table.foreign_key_constraints:
                        if not isinstance(model_key.name, str):
                            raise ValueError("Model foreign keys must be named")
                        name = conn.dialect.identifier_preparer.truncate_and_render_constraint_name(
                            model_key.name, _alembic_quote=False
                        )
                        schema = model_key.referred_table.schema
                        model_keys[name] = (
                            tuple(
                                element.parent.name for element in model_key.elements
                            ),
                            None if schema in (None, code) else schema,
                            model_key.referred_table.name,
                            tuple(
                                element.column.name for element in model_key.elements
                            ),
                            foreign_key_action(model_key.ondelete),
                            foreign_key_action(model_key.onupdate),
                        )
                    if live_keys != model_keys:
                        differences.append(
                            {"table": table.name, "kind": "foreign_keys"}
                        )
                    live_checks = {
                        item["name"]: item["sqltext"]
                        for item in inspector.get_check_constraints(table.name)
                    }
                    model_checks = {}
                    for constraint in table.constraints:
                        if isinstance(constraint, CheckConstraint):
                            if not isinstance(constraint.name, str):
                                raise ValueError(
                                    "Model check constraints must be named"
                                )
                            name = conn.dialect.identifier_preparer.truncate_and_render_constraint_name(
                                constraint.name, _alembic_quote=False
                            )
                            model_checks[name] = str(constraint.sqltext)
                    if set(live_checks) != set(model_checks):
                        differences.append({"table": table.name, "kind": "check_names"})
                    for check_name in live_checks.keys() & model_checks.keys():
                        if check_name is None:
                            continue
                        if canonical_sql(live_checks[check_name]) != canonical_sql(
                            model_checks[check_name]
                        ):
                            differences.append(
                                {
                                    "table": table.name,
                                    "kind": "check_expression",
                                    "name": check_name,
                                }
                            )
                    columns = {
                        item["name"]: item for item in inspector.get_columns(table.name)
                    }
                    for column in table.columns:
                        live = columns.get(column.name)
                        if live is None:
                            continue  # Alembic covers ordinary column differences.
                        collation = getattr(
                            column.type.dialect_impl(conn.dialect), "collation", None
                        )
                        if collation and collation != getattr(
                            live["type"], "collation", None
                        ):
                            differences.append(
                                {
                                    "table": table.name,
                                    "column": column.name,
                                    "kind": "column_collation",
                                }
                            )
                        computed = live.get("computed")
                        if (column.computed is None) != (computed is None):
                            differences.append(
                                {
                                    "table": table.name,
                                    "column": column.name,
                                    "kind": "generated_presence",
                                }
                            )
                        elif (
                            column.computed is not None
                            and computed is not None
                            and (
                                canonical_sql(column.computed.sqltext)
                                != canonical_sql(computed["sqltext"])
                                or column.computed.persisted != computed["persisted"]
                            )
                        ):
                            differences.append(
                                {
                                    "table": table.name,
                                    "column": column.name,
                                    "kind": "generated_expression_or_storage",
                                }
                            )
                    options = inspector.get_table_options(table.name)
                    options.setdefault(
                        "mysql_row_format",
                        conn.scalar(
                            text(
                                "SELECT ROW_FORMAT FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:name"
                            ),
                            {"name": table.name},
                        ),
                    )
                    for option in ("mysql_engine", "mysql_collate", "mysql_row_format"):
                        if (
                            table.kwargs.get(option)
                            and str(table.kwargs[option]).lower()
                            != str(options.get(option)).lower()
                        ):
                            differences.append(
                                {
                                    "table": table.name,
                                    "kind": "table_option",
                                    "option": option,
                                }
                            )
                revisions = (
                    list(
                        conn.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalars()
                    )
                    if "alembic_version" in tables
                    else []
                )
                return {
                    "model_tables": len(expected),
                    "database_head": revisions,
                    "missing_tables": sorted(expected - tables),
                    "extra_tables": sorted(tables - expected - {"alembic_version"}),
                    "native_differences": differences,
                }

            return await connection.run_sync(inspect_schema)
    finally:
        await engine.dispose()


def service_report(code: str) -> dict[str, object]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy.engine import make_url

    report: dict[str, object] = {"service": code, "aligned": False}
    key = code.upper() + "_DATABASE_URL"
    url = os.environ[key]
    parsed = make_url(url)
    if parsed.database != code or not parsed.drivername.startswith(
        ("mysql+", "mariadb+")
    ):
        raise ValueError("Database URL does not match the service registry")
    importlib.import_module(code + ".models")
    try:
        module = importlib.import_module(code + ".metadata")
    except ModuleNotFoundError as error:
        if error.name != code + ".metadata":
            raise
        from billing_platform.db import Base

        metadata, readiness = Base.metadata, None
    else:
        metadata, readiness = (
            module.service_metadata(),
            getattr(module, "MIGRATION_HEAD", None),
        )
    folder = ROOT / "dbs" / code
    config = Config(str(folder / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    report.update(
        migration_head=heads[0] if len(heads) == 1 else None, readiness_head=readiness
    )
    report.update(asyncio.run(native_snapshot(code, metadata, url)))
    process = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "check"],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=180,
    )
    report["alembic_check_exit"] = process.returncode
    report["aligned"] = aligned(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=SERVICES)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        try:
            report = service_report(args.service)
        except Exception as error:
            report = {
                "service": args.service,
                "aligned": False,
                "error": type(error).__name__,
            }
        print(json.dumps(report))
        return 0 if report["aligned"] else 1
    registry = json.loads(
        (ROOT / "start/win/conf/services.json").read_text(encoding="utf-8-sig")
    )["services"]
    selected = (args.service,) if args.service else SERVICES
    reports = []
    for code in selected:
        try:
            entries = [entry for entry in registry if entry["code"] == code]
            if (
                len(entries) != 1
                or entries[0]["project"] != "apis/" + code
                or entries[0]["alembic"] != "dbs/" + code + "/alembic.ini"
                or entries[0]["db"] != code
                or entries[0]["env_prefix"] != code.upper() + "_"
            ):
                raise ValueError("Service registry mismatch")
            executable = (
                ROOT
                / "apis"
                / code
                / ".venv"
                / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            )
            environment = os.environ.copy()
            environment[code.upper() + "_DATABASE_URL"] = database_environment(
                ROOT / "start/win/env" / (code + ".env"), code.upper() + "_DATABASE_URL"
            )
            process = subprocess.run(
                [
                    str(executable),
                    str(Path(__file__).resolve()),
                    "--child",
                    "--service",
                    code,
                ],
                cwd=ROOT / "dbs" / code,
                env=environment,
                capture_output=True,
                text=True,
                timeout=240,
            )
            report = json.loads(process.stdout)
        except Exception as error:
            report = {"service": code, "aligned": False, "error": type(error).__name__}
        reports.append(report)
        print(json.dumps(report))
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / (code + "-summary.json")).write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
    return 0 if all(report["aligned"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
